"""ViewModel for the CrystalPilot chat pane.

Manages:
- Lazy agent initialisation
- Submitting user messages to the agent
- Applying agent config changes back into the main model / trame bindings
- Snapshotting the main model state so the agent always has fresh context
- Surfacing bridge validation errors back to the agent on the next turn
"""

from __future__ import annotations

import asyncio
import logging
import threading
from functools import partial
from typing import TYPE_CHECKING, Any, Dict

from nova.mvvm.interface import BindingInterface
from pydantic import BaseModel

from ...agent.agent import Agent
from ...agent.bridge import apply_agent_config, bridged_submodels, snapshot_models, write_single_field
from ...agent.confirmation import ConfirmationGate
from ...agent.handlers import run_handlers
from ...agent.mcp_service import MCPService
from ...agent.schema_gen import enrich_schema_with_options, schema_from_model_instance
from ...agent.utils import pretty_name
from ...agent.workflow import PhaseManager
from ...core.beamline import active_technique
from ..models.chat import ChatModel
from ..views.md_render import md_to_html

if TYPE_CHECKING:
    from ...core.beamline.technique import ActionTool

logger = logging.getLogger(__name__)


class ChatViewModel:
    """ViewModel for the right-side agent chat pane."""

    def __init__(
        self,
        chat_model: ChatModel,
        main_model: BaseModel,
        binding: BindingInterface,
        main_bindings: Dict[str, Any],
        nav_fn: Any | None = None,
        main_vm: Any | None = None,
    ) -> None:
        self.chat_model = chat_model
        self.main_model = main_model
        self.main_bindings = main_bindings

        self.chat_bind = binding.new_bind(self.chat_model)

        # Agent is created lazily on first message so startup isn't blocked
        self._agent: Agent | None = None
        self._agent_lock = threading.Lock()
        self._nav_fn = nav_fn
        # Reference to MainViewModel for action tool callbacks
        self._main_vm = main_vm

        # MCP service for external tool integration (optional)
        self._mcp_service = MCPService()

        # Phase manager for experiment workflow tracking
        self._phase_manager = PhaseManager()

        # Code-level confirmation gate for destructive agent verbs (submit /
        # stop run). Shared between the agent's action tools (which only propose)
        # and the pre-agent handler chain (which executes on a user "yes").
        self._confirmation_gate = ConfirmationGate()

        # Bridge errors from the previous turn, forwarded to the next invoke()
        self._pending_bridge_errors: dict[str, str] = {}

    # ------------------------------------------------------------------ agent

    def _ensure_agent(self) -> None:
        """Create the agent on first use (idempotent, thread-safe)."""
        if self._agent is not None:
            return
        with self._agent_lock:
            if self._agent is not None:
                return
            schema_props = schema_from_model_instance(self.main_model)
            for attr in bridged_submodels():
                sub = getattr(self.main_model, attr, None)
                if sub is not None:
                    schema_props.update(schema_from_model_instance(sub))
            # Enrich schema with live option lists (instrument_list, etc.)
            live_snapshot = snapshot_models(self.main_model)
            schema_props = enrich_schema_with_options(schema_props, live_snapshot)
            # snapshot_fn lets the get_parameter / list_parameters tools read live UI state
            snapshot_fn = partial(snapshot_models, self.main_model)

            # Write-through callback: lets the agent push individual field
            # changes to the live model immediately during its turn, so
            # subsequent tool calls (e.g. refresh_schema) see fresh state.
            def _write_through(field_name: str, value: Any) -> tuple[bool, str]:
                return write_single_field(field_name, value, self.main_model, self.main_bindings)

            # UI-action tools declared by the active technique manifest. The
            # specs name a view-model method each; resolve them against the
            # live view-model so the agent can trigger "Submit through EIC" etc.
            action_tools = active_technique().action_tools
            action_fns = self._build_action_fns(action_tools)

            # Collect MCP tools if any servers are configured
            mcp_tools = self._mcp_service.get_all_tools() if self._mcp_service.is_available() else []
            self._agent = Agent(
                schema_properties=schema_props,
                snapshot_fn=snapshot_fn,
                nav_fn=self._nav_fn,
                mcp_tools=mcp_tools or None,
                phase_manager=self._phase_manager,
                write_through_fn=_write_through,
                action_fns=action_fns,
                action_tools=action_tools,
                confirmation_gate=self._confirmation_gate,
            )
            logger.info("CrystalPilot agent initialised with %d schema fields", len(schema_props))

    # ------------------------------------------------------------------ submit

    async def handle_submit(self, user_text: str) -> None:
        """Process a user message: run agent, apply config changes, update UI."""
        if not user_text.strip():
            return

        logger.debug(f"[CrystalPilot Agent] User: {user_text[:120]}")
        self.chat_model.messages.append({"role": "user", "content": user_text})
        self.chat_model.user_input = ""
        self.chat_model.is_thinking = True
        self.chat_model.agent_status = "Initialising agent…"
        self._push_chat()

        try:
            self._ensure_agent()
            # _ensure_agent() either assigns self._agent or raises, so the
            # agent is guaranteed to exist for the rest of this turn.
            assert self._agent is not None

            # Pre-agent handler chain: handle deterministic commands without LLM
            snapshot_fn = partial(snapshot_models, self.main_model)
            schema_props = self._agent.schema_properties if self._agent else {}
            run_chain = partial(
                run_handlers,
                user_text,
                snapshot_fn=snapshot_fn,
                schema_props=schema_props,
                nav_fn=self._nav_fn,
                phase_manager=self._phase_manager,
                confirmation_gate=self._confirmation_gate,
            )
            if self._confirmation_gate is not None and self._confirmation_gate.has_pending():
                # A pending destructive action means the "yes" leg executes the
                # real EIC call inside run_handlers — offload it exactly like
                # agent.invoke below so the event loop / UI stay responsive.
                handler_reply = await asyncio.get_running_loop().run_in_executor(None, run_chain)
            else:
                handler_reply = run_chain()
            if handler_reply is not None:
                logger.debug(f"[CrystalPilot Agent] Handler shortcut: {handler_reply[:80]}")
                self.chat_model.messages.append(
                    {"role": "assistant", "content": handler_reply, "html": md_to_html(handler_reply)}
                )
                self.chat_model.is_thinking = False
                self.chat_model.agent_status = ""
                self._push_chat()
                return

            current_state = snapshot_models(self.main_model)
            pending_errors = self._pending_bridge_errors or None
            self._pending_bridge_errors = {}

            self.chat_model.agent_status = "Calling LLM…"
            self._push_chat()
            logger.debug("[CrystalPilot Agent] Calling LLM (run_in_executor)…")

            # Offload the blocking LLM call to a thread-pool executor so the
            # asyncio event loop (and the Trame/Vue UI) stays responsive.
            loop = asyncio.get_running_loop()
            agent = self._agent
            reply, new_config = await loop.run_in_executor(
                None,
                lambda: agent.invoke(
                    user_text,
                    config_state=current_state,
                    bridge_errors=pending_errors,
                ),
            )

            logger.debug(f"[CrystalPilot Agent] Reply: {reply[:120]}")
            # Compare-and-swap: only write fields that the agent actually
            # changed relative to the snapshot taken at the start of the
            # turn. This prevents overwriting user edits made in the UI
            # while the agent was processing.
            diff_config = {k: v for k, v in new_config.items() if v != current_state.get(k)}
            logger.debug(f"[CrystalPilot Agent] Config diff keys: {set(diff_config) or '(none)'}")
            self.chat_model.agent_status = "Applying configuration…"
            self._push_chat()

            changed, errors = apply_agent_config(diff_config, self.main_model, self.main_bindings)
            if changed:
                logger.debug(f"[CrystalPilot Agent] Updated fields: {changed}")
                logger.info("Agent updated fields: %s", changed)
                schema_props = self._agent.schema_properties
                pretty_fields = [pretty_name(f, schema_props) for f in changed]
                self.chat_model.last_update_summary = "Updated: " + ", ".join(pretty_fields)
                self.chat_model.update_snackbar_visible = True
            if errors:
                # Surface bridge errors immediately in the reply instead
                # of deferring them to the next turn.
                logger.warning("Bridge validation errors: %s", errors)
                err_lines = "\n".join(f"- **{k}**: {v}" for k, v in errors.items())
                reply += (
                    f"\n\n**Note:** Some values were rejected by the UI:\n{err_lines}\n"
                    "Please check and correct these fields."
                )

            self.chat_model.messages.append({"role": "assistant", "content": reply, "html": md_to_html(reply)})

        except Exception as exc:
            logger.warning(f"[CrystalPilot Agent] Error: {exc}")
            logger.exception("Agent error")
            self._pending_bridge_errors = {}
            err_msg = f"Error: {exc}"
            self.chat_model.messages.append({"role": "assistant", "content": err_msg, "html": md_to_html(err_msg)})

        self.chat_model.is_thinking = False
        self.chat_model.agent_status = ""
        self._push_chat()

    # ------------------------------------------------------------------ helpers

    def _build_action_fns(self, action_tools: tuple[ActionTool, ...]) -> dict:
        """Resolve each manifest :class:`ActionTool` to a live view-model method.

        Returns ``{action_name: callable}`` for every spec whose ``vm_method``
        exists on the active view-model. Specs with no matching method are
        skipped (the generated tool then reports "not available").
        """
        fns: dict = {}
        vm = self._main_vm
        if vm is not None:
            for spec in action_tools:
                fn = getattr(vm, spec.vm_method, None)
                if callable(fn):
                    fns[spec.name] = fn
        return fns

    def toggle_drawer(self) -> None:
        self.chat_model.drawer_open = not self.chat_model.drawer_open
        self._push_chat()

    def _push_chat(self) -> None:
        self.chat_bind.update_in_view(self.chat_model)
