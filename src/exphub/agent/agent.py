"""CrystalPilot conversational agent.

Builds a LangGraph graph that:
1. Receives user messages
2. Calls the LLM (with tools bound)
3. Validates tool results (set_parameter, explain, default)
4. Returns a reply string

The agent is *schema-driven*: it receives a flat property map generated from
CrystalPilot's Pydantic models to validate every ``set_parameter`` call.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal, Set

from jsonschema import ValidationError
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode

from ..techniques.single_crystal.agent.validation import (
    check_unit_cell_volume,
    dependent_fields_to_reset,
    validate_centering,
    validate_point_group,
)
from .llm import get_configured_chat_model
from .rag import BeamlineKnowledgeBase
from .state import AgentState
from .tools import make_tools, resolve_param_name
from .utils import coerce_type, pretty_name

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).parent / "prompts"


def _load_system_prompt(beamline_id: str | None = None, task: str | None = None) -> str:
    """Assemble the system prompt from (core, beamline, task) fragments.

    Falls back to the legacy single-file ``system_prompt.md`` if the composer
    can't find any fragments. See :mod:`exphub.agent.prompts.composer`.
    """
    from .prompts.composer import compose_system_prompt

    try:
        return compose_system_prompt(beamline_id=beamline_id, task=task)
    except Exception as exc:
        logger.warning("Prompt composer failed (%s) — using fallback", exc)
        return "You are an AI helper for single-crystal neutron diffraction experiments. Be concise and helpful."


# Default at import time; an Agent instance will recompute with the active
# beamline/task on construction.
SYSTEM_PROMPT = _load_system_prompt()


class Agent:
    """CrystalPilot LangGraph agent."""

    def __init__(
        self,
        schema_properties: dict[str, dict],
        snapshot_fn: Any = None,
        nav_fn: Any = None,
        mcp_tools: list | None = None,
        phase_manager: Any = None,
        write_through_fn: Any = None,
        action_fns: dict | None = None,
        action_tools: Any = None,
        confirmation_gate: Any = None,
        beamline_id: str | None = None,
        task: str | None = None,
    ) -> None:
        self.schema_properties = schema_properties
        self._answered: Set[str] = set()
        self._config_state: dict[str, Any] = {}
        self._in_config_mode = False
        self._phase_manager = phase_manager
        # Callable(field_name, value) → (ok, error_msg) that writes a
        # single field to the live Pydantic model and pushes to the
        # Trame view immediately.  Set by ChatViewModel so the agent's
        # writes are visible to subsequent tool calls within the same turn.
        self._write_through_fn = write_through_fn

        # Beamline + task identity. Used to compose the system prompt and to
        # stamp ACTIVE_BEAMLINE / ACTIVE_TASK into per-turn context.
        self._beamline_id = beamline_id
        self._task = task or "experiment_steering"
        self.system_prompt = _load_system_prompt(beamline_id=beamline_id, task=self._task)

        try:
            self._rag: BeamlineKnowledgeBase | None = BeamlineKnowledgeBase()
        except Exception as exc:
            logger.warning("RAG init failed (%s) — retrieve_docs will be unavailable", exc)
            self._rag = None

        # Stored so rebuild_schema() can reconstruct the tool set when the
        # active beamline's schema / action tools change within a technique.
        self._snapshot_fn = snapshot_fn
        self._nav_fn = nav_fn
        self._action_fns = action_fns
        self._action_tools = action_tools
        # Code-level gate for destructive verbs (propose -> user confirms ->
        # execute). When set, confirmation-required action tools only propose.
        self._confirmation_gate = confirmation_gate
        self._mcp_tools = mcp_tools or []

        self._tools = self._make_tools()
        self.graph = self._build_graph()

    def _make_tools(self) -> list:
        """Build the tool list from the stored construction inputs."""
        tools = make_tools(
            self.schema_properties,
            snapshot_fn=self._snapshot_fn,
            nav_fn=self._nav_fn,
            rag=self._rag,
            action_fns=self._action_fns,
            action_tools=self._action_tools,
            confirmation_gate=self._confirmation_gate,
        )
        if self._mcp_tools:
            tools.extend(self._mcp_tools)
            logger.info("Added %d MCP tools to agent", len(self._mcp_tools))
        return tools

    def rebuild_schema(self, schema_properties: dict[str, dict]) -> None:
        """Rebuild the agent's tools + graph against a new schema.

        Used when the active beamline (and thus the live schema / action tools)
        changes within a technique family. Cross-technique switching requires an
        app restart in v1 (see ``MULTI_TECHNIQUE_PLAN.md``); the call site in
        ``switch_beamline`` lands with the P3 selector-gating work. This method
        is the plumbing it will use.
        """
        self.schema_properties = schema_properties
        self._tools = self._make_tools()
        self.graph = self._build_graph()

    # ------------------------------------------------------------------ graph

    # Maximum number of tool-call rounds before forcing a final reply.
    MAX_TOOL_ROUNDS = 6

    def _build_graph(self) -> Any:
        """Build a ReAct-style loop: agent → tools → validator → agent.

        The loop continues as long as the LLM emits tool calls, up to
        ``MAX_TOOL_ROUNDS`` iterations.  When the LLM returns a plain
        text reply (no tool calls) or the round limit is reached, the
        graph exits.
        """
        builder = StateGraph(AgentState)
        builder.add_node("agent", self._call_model_node)
        builder.add_node("tools", ToolNode(self._tools))
        builder.add_node("validator", self._handle_tool_result_node)

        builder.set_entry_point("agent")
        builder.add_conditional_edges(
            "agent",
            self._should_continue,
            {"tools": "tools", "end": "__end__"},
        )
        builder.add_edge("tools", "validator")
        # Loop back to agent so it can inspect tool results and decide
        # whether to issue more tool calls or produce a final reply.
        builder.add_conditional_edges(
            "validator",
            self._should_loop_back,
            {"agent": "agent", "end": "__end__"},
        )
        return builder.compile()

    # ------------------------------------------------------------------ helpers

    _QUESTION_WORDS = frozenset(
        {
            "what",
            "why",
            "how",
            "when",
            "where",
            "which",
            "who",
            "explain",
            "describe",
            "tell",
            "define",
            "clarify",
            "can",
            "could",
            "does",
            "do",
            "is",
            "are",
            "should",
            "would",
        }
    )

    @staticmethod
    def _looks_like_question(text: str) -> bool:
        """Heuristic: return True if *text* looks like a knowledge question.

        Checks for question marks and common question-starting words.
        Excludes short set-value statements like "set X to Y".
        """
        text_lower = text.lower().strip()
        # Ends with question mark
        if text.rstrip().endswith("?"):
            return True
        # Starts with a question word
        first_word = text_lower.split()[0] if text_lower else ""
        if first_word in Agent._QUESTION_WORDS:
            # Exclude imperative commands like "set ...", "apply ..."
            if first_word in ("can", "could", "does", "do", "is", "are", "should", "would"):
                return True
            return True
        return False

    # ------------------------------------------------------------------ nodes

    def _call_model_node(self, state: AgentState) -> AgentState:
        msgs: list[BaseMessage] = [SystemMessage(content=self.system_prompt)]

        # Stamp current beamline + task so the LLM (and debug logs) always know
        # which beamline this conversation is steering.
        from .prompts.composer import describe_active_context

        msgs.append(SystemMessage(content=describe_active_context(beamline_id=self._beamline_id, task=self._task)))

        # Inject current phase context if a PhaseManager is available
        if self._phase_manager is not None:
            phase = self._phase_manager.current
            scoped = self._phase_manager.get_phase_fields(self.schema_properties)
            param_lines = ", ".join(f"`{k}` ({v.get('title', k)})" for k, v in scoped.items())
            msgs.append(
                SystemMessage(
                    content=(
                        f"CURRENT PHASE: {phase.tab_name} — {phase.description}. "
                        f"PHASE PARAMETERS (use these exact names with set_parameter): {param_lines}"
                    )
                )
            )
        else:
            # No phase manager — show all parameters
            param_lines = ", ".join(f"`{k}` ({v.get('title', k)})" for k, v in self.schema_properties.items())
            msgs.append(
                SystemMessage(content=f"AVAILABLE PARAMETERS (use these exact names with set_parameter): {param_lines}")
            )

        if state.get("in_config_mode"):
            cfg = state.get("config_state", {})
            msgs.append(SystemMessage(content=f"CONTEXT: Current config values: {json.dumps(cfg, default=str)}"))

        # Nudge the LLM to use retrieve_docs for question-like messages.
        # This compensates for LLMs that skip tool calls for "simple" questions.
        last_user = ""
        for m in reversed(state["messages"]):
            if isinstance(m, HumanMessage):
                content = m.content
                last_user = content.strip() if isinstance(content, str) else str(content).strip()
                break
        if last_user and self._looks_like_question(last_user) and state.get("tool_rounds", 0) == 0:
            msgs.append(
                SystemMessage(
                    content=(
                        "HINT: The user appears to be asking a knowledge question. "
                        "You MUST call `retrieve_docs` to search the knowledge base "
                        "before answering. Do NOT answer from memory alone."
                    )
                )
            )

        msgs.extend(state["messages"][-20:])

        logger.debug("[Agent] Calling LLM…")
        llm = get_configured_chat_model().bind_tools(self._tools)
        out = llm.invoke(msgs)
        tool_calls = getattr(out, "tool_calls", [])
        if tool_calls:
            logger.debug(f"[Agent] LLM → tool calls: {[tc['name'] for tc in tool_calls]}")
        else:
            content_preview = (out.content or "")[:80]
            logger.debug(f"[Agent] LLM → reply: {content_preview}")
        return {
            "messages": [out],
            "config_state": state.get("config_state", {}),
            "in_config_mode": state.get("in_config_mode", False),
            "next_to_ask": state.get("next_to_ask", ""),
            "nudge_count": state.get("nudge_count", 0),
            "tool_rounds": state.get("tool_rounds", 0),
        }

    def _handle_tool_result_node(self, state: AgentState) -> AgentState:
        """Validate tool results and update config_state.

        In the ReAct loop the tool results (ToolMessage) are already in
        the message list.  This node performs side-effects (updating
        config_state, cross-field validation) and optionally appends a
        SystemMessage note so the LLM is informed of validation
        outcomes.  The LLM will then decide whether to issue more tool
        calls or produce a final text reply.
        """
        tool_msg = state["messages"][-1]
        if not isinstance(tool_msg, ToolMessage):
            return state
        logger.debug(f"[Agent] Tool result: {tool_msg.name}")

        try:
            if isinstance(tool_msg.content, str):
                tool_output = json.loads(tool_msg.content)
            else:
                tool_output = tool_msg.content
        except (json.JSONDecodeError, TypeError):
            tool_output = tool_msg.content

        rounds = state.get("tool_rounds", 0) + 1

        # --- Dispatch to handler; each returns (note_text, updated_state_patch) ---
        note: str | None = None

        if tool_msg.name == "explain_parameter":
            note = str(tool_output)

        elif tool_msg.name == "get_default_value":
            note = self._validate_get_default(state, tool_output)

        elif tool_msg.name == "refresh_schema":
            note = self._validate_refresh_schema(state, tool_output)

        elif tool_msg.name in ("set_multiple_parameters", "apply_preset"):
            note = self._validate_set_multiple(state, tool_output)

        elif tool_msg.name == "list_presets":
            note = str(tool_output)

        elif tool_msg.name in ("set_parameter", "append_run", "edit_run", "delete_run"):
            if isinstance(tool_output, dict) and "error" in tool_output and "parameter_name" not in tool_output:
                note = f"Error: {tool_output['error']}"
            else:
                note = self._validate_set_parameter(state, tool_output)

        elif tool_msg.name == "get_parameter":
            note = self._validate_get_parameter(state, tool_output)

        elif tool_msg.name == "list_parameters":
            note = self._validate_list_parameters(state, tool_output)

        elif tool_msg.name == "get_angle_plan":
            note = self._validate_get_angle_plan(state, tool_output)

        elif tool_msg.name == "navigate_to_tab":
            note = self._validate_navigate_to_tab(state, tool_output)

        elif tool_msg.name == "retrieve_docs":
            note = self._validate_retrieve_docs(
                state,
                tool_msg.content if isinstance(tool_msg.content, str) else str(tool_msg.content),
            )

        elif tool_msg.name in (
            "submit_angle_plan",
            "authenticate_eic",
            "initialize_strategy",
            "upload_strategy",
            "stop_current_run",
        ):
            # Action tools return {"status": ...} or {"error": ...}
            if isinstance(tool_output, dict):
                if "error" in tool_output:
                    note = f"Action error: {tool_output['error']}"
                else:
                    note = tool_output.get("message", f"Action {tool_msg.name} completed.")
            else:
                note = str(tool_output)

        new_messages: list[BaseMessage] = []
        if note:
            new_messages.append(SystemMessage(content=f"[TOOL RESULT NOTE] {note}"))

        return {
            "messages": new_messages,
            "config_state": state["config_state"],
            "in_config_mode": state.get("in_config_mode", False),
            "next_to_ask": state.get("next_to_ask", ""),
            "nudge_count": state.get("nudge_count", 0),
            "tool_rounds": rounds,
        }

    @staticmethod
    def _should_continue(state: AgentState) -> Literal["tools", "end"]:
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return "end"

    def _should_loop_back(self, state: AgentState) -> Literal["agent", "end"]:
        """Decide whether to loop back to the agent after tool execution.

        Loops back so the LLM can see tool results and decide its next
        action — unless we've hit the round limit.
        """
        rounds = state.get("tool_rounds", 0)
        if rounds >= self.MAX_TOOL_ROUNDS:
            logger.warning("Hit MAX_TOOL_ROUNDS (%d), forcing exit", self.MAX_TOOL_ROUNDS)
            return "end"
        return "agent"

    # ------------------------------------------------------------------ tool validators
    # Each _validate_* method performs side-effects on config_state and
    # returns a short note string for the LLM to see in the next turn.

    def _validate_retrieve_docs(self, state: AgentState, raw_content: str) -> str:
        """Pass through the RAG answer with a directive to relay it."""
        if raw_content.startswith("No relevant") or raw_content.startswith("Knowledge base"):
            return raw_content
        return (
            "KNOWLEDGE BASE ANSWER (present this to the user — do NOT ignore it "
            "or replace it with a generic reply):\n\n" + raw_content
        )

    def _validate_navigate_to_tab(self, state: AgentState, tool_output: Any) -> str:
        if isinstance(tool_output, dict) and "error" in tool_output:
            return f"Navigation error: {tool_output['error']}"
        tab = tool_output.get("tab") if isinstance(tool_output, dict) else None
        name = tool_output.get("name", f"tab {tab}") if isinstance(tool_output, dict) else f"tab {tab}"
        return f"Switched to **{name}** tab."

    def _validate_get_parameter(self, state: AgentState, tool_output: dict) -> str:
        if not isinstance(tool_output, dict):
            return "Could not read parameter value."
        param = tool_output.get("parameter_name", "?")
        err = tool_output.get("error")
        if err:
            return f"Could not read **{param}**: {err}"
        value = tool_output.get("value")
        label = pretty_name(param, self.schema_properties)
        reply = f"Current value of **{label}** is `{value}`." if value is not None else f"**{label}** is not set."
        opts = tool_output.get("valid_options")
        if opts:
            reply += " Valid options: " + ", ".join(f"`{o}`" for o in opts) + "."
        return reply

    def _validate_refresh_schema(self, state: AgentState, tool_output: Any) -> str:
        if not isinstance(tool_output, dict):
            return str(tool_output)
        if "error" in tool_output:
            return f"Schema refresh error: {tool_output['error']}"
        fields = tool_output.get("refreshed_fields", [])
        total = tool_output.get("total_fields", 0)
        if fields:
            names = ", ".join(f"**{pretty_name(f, self.schema_properties)}**" for f in fields)
            return f"Schema refreshed — updated options for: {names}."
        return f"Schema refreshed — no option changes detected ({total} fields checked)."

    def _validate_set_multiple(self, state: AgentState, tool_output: dict) -> str:
        if not isinstance(tool_output, dict):
            return "Invalid tool output for multi-set."
        if "error" in tool_output and "validated" not in tool_output:
            return f"Error: {tool_output['error']}"

        validated = tool_output.get("validated", {})
        errors = tool_output.get("errors", {})
        preset_name = tool_output.get("preset_name")

        for key, value in validated.items():
            state["config_state"][key] = value
            self._answered.add(key)
            # Write-through to live model
            if self._write_through_fn:
                ok, wt_err = self._write_through_fn(key, value)
                if not ok:
                    errors[key] = f"write-through failed: {wt_err}"

        parts: list[str] = []
        if preset_name:
            parts.append(f"Applied preset **{preset_name}**.")
        if validated:
            fields = ", ".join(f"**{pretty_name(k, self.schema_properties)}** = `{v}`" for k, v in validated.items())
            parts.append(f"Set {len(validated)} parameter(s): {fields}.")
        if errors:
            errs = ", ".join(f"**{k}**: {v}" for k, v in errors.items())
            parts.append(f"Could not set: {errs}.")

        state["in_config_mode"] = True
        return " ".join(parts) or "No changes applied."

    def _validate_get_angle_plan(self, state: AgentState, tool_output: Any) -> str:
        if isinstance(tool_output, dict) and "error" in tool_output:
            return f"Error reading angle plan: {tool_output['error']}"
        if not isinstance(tool_output, list):
            return str(tool_output)
        if not tool_output:
            return "The angle plan table is currently empty."
        header = "| # | Title | phi | omega | Wait For | Value | Or Time |"
        sep = "|---|-------|-----|-------|----------|-------|---------|"
        rows = [
            f"| {r.get('_index', i)} | {r.get('title', '')} | {r.get('phi', 0)} "
            f"| {r.get('omega', 0)} | {r.get('wait_for', '')} | {r.get('value', 0)} | {r.get('or_time', 0)} |"
            for i, r in enumerate(tool_output)
        ]
        return "**Current Angle Plan:**\n\n" + header + "\n" + sep + "\n" + "\n".join(rows)

    def _validate_list_parameters(self, state: AgentState, tool_output: Any) -> str:
        if isinstance(tool_output, list):
            lines = [
                f"- **{p['title']}** (`{p['name']}`)"
                + (f": {p['description']}" if p.get("description") else "")
                + (f" — options: {', '.join(p['options'])}" if p.get("options") else "")
                for p in tool_output
            ]
            return "**Available parameters:**\n" + "\n".join(lines)
        return str(tool_output)

    def _validate_get_default(self, state: AgentState, tool_output: dict) -> str:
        param = tool_output["parameter_name"]
        default = tool_output["default"]
        label = pretty_name(param, self.schema_properties)
        if default is not None:
            return f"The default value for **{label}** is `{default}`."
        return f"There is no default defined for **{label}**."

    def _validate_set_parameter(self, state: AgentState, tool_output: dict) -> str:
        if not isinstance(tool_output, dict):
            return "Invalid tool output format."

        key = tool_output["parameter_name"]
        raw_value = tool_output["parameter_value"]

        key, info = resolve_param_name(key, self.schema_properties)
        if not info:
            return f"Unknown parameter '{key}'. Please check the name."

        try:
            value = coerce_type(raw_value, info)

            if info.get("enum") and isinstance(value, str):
                lc = value.strip().lower()
                match = next((c for c in info["enum"] if str(c).lower() == lc), None)
                if match is None:
                    opts = ", ".join(str(c) for c in info["enum"])
                    return f"Invalid value '{value}'. Choose from: {opts}"
                value = match

            # --- Cross-field validation (crystal system cascade) ---
            cfg = state["config_state"]

            if key == "point_group":
                err = validate_point_group(value, cfg.get("crystalsystem"))
                if err:
                    return err

            if key == "centering":
                err = validate_centering(value, cfg.get("point_group"))
                if err:
                    return err

            # Record the value
            cfg[key] = value
            self._answered.add(key)
            label = pretty_name(key, self.schema_properties)
            reply = f"Set **{label}** = `{value}`."

            # Write-through: push to the live Pydantic model immediately
            # so subsequent tool calls (e.g. refresh_schema, get_parameter)
            # see the updated value within the same turn.
            if self._write_through_fn:
                ok, wt_err = self._write_through_fn(key, value)
                if not ok:
                    reply += f" (Warning: write-through failed: {wt_err})"

            # Reset dependent fields when upstream changes
            resets = dependent_fields_to_reset(key)
            if resets:
                cleared = []
                for dep in resets:
                    if dep in cfg:
                        del cfg[dep]
                    self._answered.discard(dep)
                    cleared.append(f"**{pretty_name(dep, self.schema_properties)}**")
                if cleared:
                    reply += f" (Cleared {', '.join(cleared)} — please re-select.)"

            # Unit cell volume sanity check
            if key in ("molecular_formula", "Z", "unit_cell_volume"):
                is_error, msg = check_unit_cell_volume(cfg)
                if is_error:
                    reply += f"\n\n{msg}"

            state["in_config_mode"] = True
            return reply

        except (ValidationError, ValueError, TypeError) as err:
            return f"Invalid value for **{key}**: {err}"

    # ------------------------------------------------------------------ public API

    def invoke(
        self,
        user_text: str,
        config_state: dict | None = None,
        bridge_errors: dict[str, str] | None = None,
    ) -> tuple[str, dict]:
        """Run the agent for a single user turn.

        Parameters
        ----------
        user_text:
            The latest message from the user.
        config_state:
            Current flat config snapshot from the UI (bridge.snapshot_models).
        bridge_errors:
            Optional dict of ``{field: error_msg}`` from the *previous* turn's
            ``apply_agent_config`` call. When provided, these are prepended as a
            system note so the agent knows which writes failed and why.

        Returns
        -------
        (reply_text, updated_config_state)
        """
        cfg = dict(config_state or self._config_state)

        messages: list = []
        if bridge_errors:
            lines = "\n".join(f"- `{k}`: {v}" for k, v in bridge_errors.items())
            messages.append(
                HumanMessage(
                    content=f"[SYSTEM] The following parameter writes were rejected by the UI:\n{lines}\n"
                    "Please inform the user and suggest corrections."
                )
            )
        messages.append(HumanMessage(content=user_text))

        initial_state: AgentState = {
            "messages": messages,
            "config_state": cfg,
            "in_config_mode": self._in_config_mode,
            "next_to_ask": "",
            "nudge_count": 0,
            "tool_rounds": 0,
        }

        result = self.graph.invoke(initial_state)

        self._config_state = result.get("config_state", cfg)
        self._in_config_mode = result.get("in_config_mode", False)

        reply = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                reply = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

        return reply, self._config_state
