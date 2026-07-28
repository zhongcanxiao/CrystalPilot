"""Tests for the destructive-action confirmation gate (HANDOFF item C.1).

The gate turns the agent's prompt-only safety ("confirm with the user first")
into a code invariant: a ``requires_confirmation`` verb can only ever PROPOSE
from a tool call; the destructive function runs solely from an explicit human
"yes" routed through the pre-agent handler chain. These tests pin that invariant
at every layer — the gate, the tool wrapper, the handler, and the manifest
wiring — so a refactor can't quietly let the model self-authorise.
"""

from __future__ import annotations

from exphub.agent.confirmation import ConfirmationGate
from exphub.agent.handlers import handle_action_confirm, run_handlers
from exphub.agent.tools import _make_action_tool
from exphub.core.beamline import ActionTool

# --------------------------------------------------------------------------- gate


def test_propose_records_without_executing() -> None:
    gate = ConfirmationGate()
    calls: list[int] = []
    result = gate.propose("stop_current_run", lambda: calls.append(1), "stopped")
    assert calls == []  # nothing ran
    assert gate.has_pending()
    assert gate.pending_name == "stop_current_run"
    assert result["status"] == "confirmation_required"
    assert result["action"] == "stop_current_run"


def test_confirm_executes_and_clears() -> None:
    gate = ConfirmationGate()
    calls: list[int] = []
    gate.propose("submit_angle_plan", lambda: calls.append(1), "submitted")
    result = gate.confirm()
    assert calls == [1]
    assert result == {"status": "ok", "message": "submitted"}
    assert not gate.has_pending()


def test_confirm_with_nothing_pending_is_error() -> None:
    gate = ConfirmationGate()
    result = gate.confirm()
    assert "error" in result


def test_confirm_with_unavailable_fn_is_error() -> None:
    gate = ConfirmationGate()
    gate.propose("stop_current_run", None, "stopped")
    result = gate.confirm()
    assert "error" in result
    assert not gate.has_pending()


def test_cancel_discards_without_executing() -> None:
    gate = ConfirmationGate()
    calls: list[int] = []
    gate.propose("stop_current_run", lambda: calls.append(1), "stopped")
    result = gate.cancel()
    assert calls == []
    assert result["status"] == "cancelled"
    assert not gate.has_pending()


def test_propose_replaces_prior_pending() -> None:
    gate = ConfirmationGate()
    gate.propose("a", lambda: None, "")
    gate.propose("b", lambda: None, "")
    assert gate.pending_name == "b"


def test_confirm_surfaces_fn_exception() -> None:
    gate = ConfirmationGate()

    def boom() -> None:
        raise RuntimeError("hardware offline")

    gate.propose("stop_current_run", boom, "stopped")
    result = gate.confirm()
    assert result["error"] == "hardware offline"
    assert not gate.has_pending()


# --------------------------------------------------------------------------- tool wrapper


def _spec(name: str, requires_confirmation: bool) -> ActionTool:
    return ActionTool(
        name=name,
        vm_method=name,
        description=f"{name} action",
        success_message=f"{name} done",
        requires_confirmation=requires_confirmation,
    )


def test_confirmation_tool_only_proposes() -> None:
    gate = ConfirmationGate()
    calls: list[int] = []
    tool = _make_action_tool(_spec("stop_current_run", True), lambda: calls.append(1), gate)
    out = tool.invoke({})
    assert calls == []  # the model's tool call did NOT execute the action
    assert out["status"] == "confirmation_required"
    assert gate.has_pending()


def test_non_confirmation_tool_executes_immediately() -> None:
    gate = ConfirmationGate()
    calls: list[int] = []
    tool = _make_action_tool(_spec("authenticate_eic", False), lambda: calls.append(1), gate)
    out = tool.invoke({})
    assert calls == [1]
    assert out["status"] == "ok"
    assert not gate.has_pending()


def test_confirmation_tool_without_gate_falls_back_to_immediate() -> None:
    # Back-compat: no gate supplied -> behaves like the original (immediate) tool.
    calls: list[int] = []
    tool = _make_action_tool(_spec("stop_current_run", True), lambda: calls.append(1), None)
    out = tool.invoke({})
    assert calls == [1]
    assert out["status"] == "ok"


# --------------------------------------------------------------------------- handler


def test_handler_noop_without_gate_or_pending() -> None:
    assert handle_action_confirm("yes", None, {}, None, confirmation_gate=None) is None
    gate = ConfirmationGate()
    assert handle_action_confirm("yes", None, {}, None, confirmation_gate=gate) is None


def test_handler_yes_executes() -> None:
    gate = ConfirmationGate()
    calls: list[int] = []
    gate.propose("stop_current_run", lambda: calls.append(1), "Current run stopped.")
    reply = handle_action_confirm("yes", None, {}, None, confirmation_gate=gate)
    assert calls == [1]
    assert reply is not None and "stopped" in reply.lower()
    assert not gate.has_pending()


def test_handler_no_cancels() -> None:
    gate = ConfirmationGate()
    calls: list[int] = []
    gate.propose("stop_current_run", lambda: calls.append(1), "stopped")
    reply = handle_action_confirm("no", None, {}, None, confirmation_gate=gate)
    assert calls == []
    assert reply is not None and "cancel" in reply.lower()
    assert not gate.has_pending()


def test_handler_ambiguous_is_sticky() -> None:
    gate = ConfirmationGate()
    calls: list[int] = []
    gate.propose("stop_current_run", lambda: calls.append(1), "stopped")
    reply = handle_action_confirm("what is the temperature?", None, {}, None, confirmation_gate=gate)
    assert calls == []
    assert reply is not None  # re-prompt, does NOT fall through to the LLM
    assert gate.has_pending()  # still pending until the user resolves it


# --------------------------------------------------------------------------- end-to-end


def test_full_propose_then_confirm_flow() -> None:
    """LLM tool call proposes; only a later user 'yes' (via run_handlers) runs it."""
    gate = ConfirmationGate()
    calls: list[int] = []
    tool = _make_action_tool(_spec("stop_current_run", True), lambda: calls.append(1), gate)

    # Turn 1: the model calls the tool -> proposal only.
    tool.invoke({})
    assert calls == []

    # Turn 2: an unrelated message is blocked while a destructive action is pending.
    blocked = run_handlers("set temperature to 300", confirmation_gate=gate)
    assert blocked is not None and calls == []

    # Turn 3: explicit user confirmation runs it — without ever consulting the LLM.
    reply = run_handlers("yes", confirmation_gate=gate)
    assert calls == [1]
    assert reply is not None
    assert not gate.has_pending()


# --------------------------------------------------------------------------- manifest wiring


def test_destructive_verbs_require_confirmation() -> None:
    from exphub.techniques.single_crystal.manifest import SINGLE_CRYSTAL

    by_name = {t.name: t for t in SINGLE_CRYSTAL.action_tools}
    assert by_name["submit_angle_plan"].requires_confirmation is True
    assert by_name["stop_current_run"].requires_confirmation is True
    # Non-destructive verbs stay immediate.
    assert by_name["authenticate_eic"].requires_confirmation is False
    assert by_name["upload_strategy"].requires_confirmation is False


def test_sans_destructive_verbs_require_confirmation() -> None:
    """The SANS manifest gates its instrument-driving verbs like single-crystal."""
    from exphub.techniques.sans.manifest import SANS

    by_name = {t.name: t for t in SANS.action_tools}
    assert by_name["submit_strategy"].requires_confirmation is True
    assert by_name["stop_current_run"].requires_confirmation is True
    # Non-destructive verbs stay immediate.
    assert by_name["authenticate_eic"].requires_confirmation is False
    assert by_name["upload_strategy"].requires_confirmation is False
    assert by_name["export_strategy"].requires_confirmation is False
