"""App-shell ViewModel: the technique-agnostic window chrome.

Owns tab navigation, the beamline selector, the informational snackbar, and
the under-development / uninterruptable dialogs — everything that is *not*
specific to a particular technique. The single-crystal experiment-steering
concerns live in
``techniques/single_crystal/view_models/steering.py``.

Extracted from the former ``MainViewModel`` during the multi-technique
refactor (P2.16).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from nova.mvvm.interface import BindingInterface
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ...core.beamline import TabKey

_DEBUG = bool(os.environ.get("CRYSTALPILOT_DEBUG"))


def _trace(*args: Any) -> None:
    if _DEBUG:
        print(*args)


def _default_beamline_id() -> str:
    """Pick the active beamline's id at view-state construction time."""
    try:
        from ...core.beamline import active as _active_beamline

        return _active_beamline().id
    except Exception:
        return ""


def _active_technique_id() -> str | None:
    """Technique family of the active beamline (e.g. ``"single_crystal"``)."""
    try:
        from ...core.beamline import active as _active_beamline

        return _active_beamline().technique
    except Exception:
        return None


def _default_beamline_options() -> list[dict]:
    """Build the ``[{value, title, disabled}]`` list for the selector.

    Cross-technique options (a beamline whose ``technique`` differs from the
    active beamline's) are flagged ``disabled``: v1 gates switching across
    technique families to a restart (see MULTI_TECHNIQUE_PLAN.md P3 / decision
    #4). The selector renders disabled entries grayed-out alongside a banner.
    """
    try:
        from ...core.beamline import get as _get
        from ...core.beamline import list_ids as _list_ids

        active_tech = _active_technique_id()
        options: list[dict] = []
        for bid in _list_ids():
            spec = _get(bid)
            options.append(
                {
                    "value": bid,
                    "title": spec.display_name,
                    "disabled": active_tech is not None and spec.technique != active_tech,
                }
            )
        return options
    except Exception:
        return []


def _tab_to_int(tab: "TabKey | int | str") -> int:
    """Translate a TabKey (or its str value) to the active beamline's tab id.

    Resolution lives in the per-beamline tab layout
    (:func:`exphub.core.beamline.tab_layout.tab_key_to_int`): a merged TabKey
    maps to its combined tab's id, so agent / phase navigation to IPTS / LIVE /
    STEERING all land on the one visible tab when a beamline merges them. The
    legacy 1/2/3/5/6 ids are preserved by the default layout. Ints pass through.
    """
    from ...core.beamline.tab_layout import tab_key_to_int

    return tab_key_to_int(tab)


class AppShellViewState(BaseModel):
    """View state for the technique-agnostic application shell."""

    active_tab: int = Field(default=0)
    is_under_development: bool = Field(default=False)
    is_uninterruptable: bool = Field(default=False)
    beamline_id: str = Field(default_factory=_default_beamline_id)
    beamline_options: list[dict] = Field(default_factory=_default_beamline_options)
    beamline_switch_notice: str = Field(default="")
    beamline_switch_visible: bool = Field(default=False)
    # Always-visible banner shown beneath the selector explaining that
    # cross-technique options are grayed out until restart.
    cross_technique_banner: str = Field(default="Restart CrystalPilot to switch technique families")


class AppShellViewModel:
    """ViewModel for the window chrome: tab strip, beamline selector, dialogs."""

    def __init__(self, binding: BindingInterface) -> None:
        self.view_state = AppShellViewState()
        # Track the last-known beamline so the view_state callback only triggers
        # a switch when the user actually picked a new option in the selector.
        self._last_beamline_id: str = self.view_state.beamline_id
        # Optional lifecycle hook invoked on the *outgoing* technique VM before
        # an inside-technique switch lands (wired by mvvm_factory to the active
        # steering VM's ``on_deactivate``). Lets the technique quiesce live
        # tasks / clear buffers before the registry swaps.
        self._deactivate_hook: Optional[Callable[[], None]] = None
        self.view_state_bind = binding.new_bind(self.view_state, callback_after_update=self.on_view_state_change)

    def set_deactivate_hook(self, hook: Callable[[], None]) -> None:
        """Register the active technique VM's ``on_deactivate`` callback.

        Called once at composition time (mvvm_factory). On an inside-technique
        beamline switch, ``switch_beamline`` invokes this hook *before* swapping
        the registry so the outgoing technique can cancel its live-update task,
        clear temporal buffers, and otherwise quiesce.
        """
        self._deactivate_hook = hook

    def on_view_state_change(self, results: Dict[str, Any]) -> None:
        """Detect user-driven changes to the shell view-state (beamline selector)."""
        if results.get("error"):
            logger.warning(f"view_state error in {results.get('errored')}")
            return
        if self.view_state.beamline_id != self._last_beamline_id:
            new_id = self.view_state.beamline_id
            self._last_beamline_id = new_id
            self.switch_beamline(new_id)

    def navigate_to_tab(self, tab: "TabKey | int") -> None:
        """Switch the active tab and push the change to the view.

        Accepts a :class:`TabKey` (preferred — the agent and the technique
        manifest speak TabKey) or a raw integer tab id (translation shim). The
        TabKey is resolved to the active beamline's tab id via ``_tab_to_int``
        (``core.beamline.tab_layout``): the default layout keeps the legacy ids
        (1=IPTS, 2=LIVE, 3=STEERING, 5=STATUS, 6=ANALYSIS), while a beamline that
        merges tabs (e.g. USANS) maps several TabKeys onto one combined tab's id.
        """
        self.view_state.active_tab = _tab_to_int(tab)
        self.view_state_bind.update_in_view(self.view_state)

    def switch_beamline(self, beamline_id: str) -> None:
        """Activate a different beamline plug-in.

        Called either directly (e.g. tests) or by ``on_view_state_change``
        when the user picks a new option in the selector. Updates the
        registry so subsequent reads of ``active().<...>`` pick up the new
        beamline's PVs/paths/presets.

        Hard-bound resources — the EPICS ``.bob`` screen connected at
        MainApp construction, the agent's RAG index, and the auto-resolved
        model-field defaults already applied to existing instances — won't
        reload mid-session. A snackbar surfaces that note.

        Cross-technique switches (a target beamline whose ``technique`` differs
        from the active one) are refused: v1 gates technique-family changes to a
        restart (MULTI_TECHNIQUE_PLAN.md decision #4). The selector already
        grays such options out; this is the defence-in-depth no-op for a
        programmatic / stale-state call. The user is told via the snackbar.
        """
        from ...core.beamline import active, get, set_active

        if not beamline_id:
            return
        try:
            target = get(beamline_id)
        except KeyError as e:
            logger.debug(f"switch_beamline: {e}")
            return

        # Refuse cross-technique switches: no-op + snackbar, and roll the
        # selector's bound id back to the active beamline so the UI doesn't
        # show a stale (disabled) selection.
        try:
            current_technique = active().technique
        except Exception:
            current_technique = None
        if current_technique is not None and target.technique != current_technique:
            self._last_beamline_id = self.view_state.beamline_id = active().id
            self.notify(
                f"Restart CrystalPilot to switch technique families "
                f"(cannot switch to {target.display_name} from a "
                f"{current_technique} beamline)."
            )
            return

        # Inside-technique switch: let the outgoing technique quiesce (cancel
        # live-update task, clear buffers) before the registry swaps.
        if self._deactivate_hook is not None:
            try:
                self._deactivate_hook()
            except Exception as e:
                logger.warning(f"switch_beamline: deactivate hook failed: {e}")

        spec = set_active(beamline_id)
        # Keep our cached id aligned so the next change_callback doesn't loop.
        self._last_beamline_id = spec.id
        self.view_state.beamline_id = spec.id
        self.view_state.beamline_switch_notice = (
            f"Switched to {spec.display_name}. Restart the app for the "
            "Instrument Status screen and EPICS subscriptions to fully reload."
        )
        self.view_state.beamline_switch_visible = True
        self._push_view_state()

    def notify(self, message: str) -> None:
        """Surface an informational message in the shell snackbar.

        Reuses the beamline-switch snackbar (rendered by TabsPanel) so a
        technique view-model can flag an event — e.g. the steering VM pausing
        the live-update loop — without owning its own snackbar widget.
        """
        self.view_state.beamline_switch_notice = message
        self.view_state.beamline_switch_visible = True
        self._push_view_state()

    def show_under_development_dialog(self) -> None:
        _trace("show_underdev")
        self._push_view_state()

    def close_under_development_dialog(self) -> None:
        _trace("hide_underdev")
        self.view_state.is_under_development = False
        self._push_view_state()

    def _push_view_state(self) -> None:
        # Best-effort: a VM method (e.g. a cross-technique refusal snackbar)
        # may fire before TabsPanel has connected the ``controls`` namespace.
        # Swallow the not-yet-connected case so the no-op switch still updates
        # the in-memory view_state without crashing the caller.
        try:
            self.view_state_bind.update_in_view(self.view_state)
        except ValueError as e:
            _trace(f"_push_view_state skipped (bind not connected): {e}")
