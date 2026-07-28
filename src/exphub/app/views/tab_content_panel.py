"""Module for the Tab Content panel.

Manifest-driven dispatcher (P3). The panel no longer imports any technique
view directly: it resolves each of the five tab slots uniformly through the
active beamline's :class:`TabOverrides` and the active technique manifest, so
no single-crystal vocabulary leaks into this app-shell module.

Fall-through contract per slot (see ``MULTI_TECHNIQUE_PLAN.md``):

    factory = beamline.tabs.<override>                       # beamline override
           or technique.default_tabs[slot]                    # technique default (tabs 1-3)
           or technique.optional_tab_defaults[slot]           # only if opted in (tabs 4-5)
           or PlaceholderTab(message, links)                  # final fall-through

Each resolved slot is wrapped in ``VBoxLayout(v_if="controls.active_tab == N")``
so the factory runs only on first navigation to that tab. The technique tab
factories receive the single-crystal steering view-model; the under-development
dialog's OK button still resolves against the app-shell view-model.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from nova.trame.view.layouts import VBoxLayout
from trame.widgets import vuetify3 as vuetify
from trame_server import Server

from ...core.beamline import TabKey
from ...core.beamline import active as _active_beamline
from ...core.beamline import active_technique as _active_technique
from ...core.beamline.tab_layout import active_layout, label_for
from .placeholder_tab import PlaceholderTab

if TYPE_CHECKING:
    from ...core.beamline.technique import SteeringViewModel
    from ..view_models.app_shell import AppShellViewModel

logger = logging.getLogger(__name__)


class TabContentPanel:
    """View class to render content for a selected tab.

    Tabs resolve their factory from the active beamline / technique manifest;
    each technique tab factory binds to the active technique's steering VM,
    while the under-development dialog button resolves against the app-shell VM.
    """

    def __init__(
        self,
        server: Server,
        view_model: SteeringViewModel,
        shell_view_model: AppShellViewModel,
    ) -> None:
        self.view_model = view_model
        self.shell_view_model = shell_view_model
        self.server = server
        self.ctrl = server.controller
        self.create_ui()

    def _resolve_factory(self, key: TabKey) -> Any:
        """Resolve the factory for one tab slot ``key`` via the fall-through contract.

        Returns a one-argument factory callable. When no override / default /
        opted-in optional default exists, returns a closure that renders a
        :class:`PlaceholderTab` built from the beamline's per-tab message and
        links (so the dispatcher can call every slot uniformly).
        """
        beamline = _active_beamline()
        technique = _active_technique()

        override_attr = technique.tab_override_slots.get(key)
        if override_attr is not None:
            factory = getattr(beamline.tabs, override_attr, None)
            if factory is not None:
                return factory

        factory = technique.default_tabs.get(key)
        if factory is not None:
            return factory

        # Tabs 4-5 may opt into a technique-supplied "common-useful" default
        # (e.g. the single-crystal data-analysis launcher) via
        # BeamlineSpec.optional_tabs. Without opt-in the slot falls through to
        # a placeholder so a beamline never silently inherits a tab shape.
        if key in beamline.optional_tabs:
            factory = technique.optional_tab_defaults.get(key)
            if factory is not None:
                return factory

        message = beamline.placeholder_messages.get(key)
        links = beamline.placeholder_links.get(key)

        def _placeholder(_vm: Any) -> Any:
            return PlaceholderTab(message=message, external_links=links)

        return _placeholder

    def create_ui(self) -> None:
        # One VBoxLayout per tab in the active beamline's layout. A tab that
        # covers a single TabKey renders that slot's factory; a tab that covers
        # several (a merged tab, e.g. USANS' combined Setup/Steering) stacks each
        # slot's resolved view in one scrollable column, with a section header.
        for group in active_layout():
            with VBoxLayout(v_if=f"controls.active_tab == {group.id}", stretch=True):
                if len(group.covers) == 1:
                    self._resolve_factory(group.covers[0])(self.view_model)
                else:
                    with VBoxLayout(classes="overflow-y-auto", gap="1em", stretch=True):
                        for key in group.covers:
                            vuetify.VCardTitle(label_for(key))
                            self._resolve_factory(key)(self.view_model)

        with vuetify.VDialog(v_model="controls.is_under_development", max_width="500px"):
            with vuetify.VCard():
                with vuetify.VCardTitle("Under Development"):
                    vuetify.VCardText(
                        "This feature is currently under development.", classes="text-caption text-center"
                    )
                with vuetify.VCardActions():
                    vuetify.VBtn(
                        "OK", click=self.shell_view_model.close_under_development_dialog, color="primary", block=True
                    )

        with vuetify.VDialog(v_model="controls.is_uninterruptable", max_width="500px"):
            with vuetify.VCard():
                with vuetify.VCardTitle("Waiting for Algorithm"):
                    vuetify.VCardText(
                        "Algorithm is running in background, waiting for completion.",
                        classes="text-caption text-center",
                    )

    def open_data_visualization(self) -> None:
        """Open the Data Visualization tab."""
        import os

        os.system("~/run-nxv.sh")
        logger.debug("Open Data Visualization tab")

    def open_data_reduction(self) -> None:
        """Open the Data Reduction tab."""
        logger.debug("Open Data Reduction tab")

    def open_data_refinement(self) -> None:
        """Open the Data Refinement tab."""
        logger.debug("Open Data Refinement tab")
