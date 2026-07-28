"""Code-level propose -> confirm -> execute gate for destructive agent actions.

Some technique action verbs have real, hard-to-reverse hardware effects —
aborting a running scan, submitting an angle plan to the beamline EIC. Guarding
them with prompt text alone ("confirm with the user first") is advisory: a model
can ignore it. This gate makes the safety a *code* invariant.

A verb flagged ``requires_confirmation`` can only ever :meth:`propose`; the
destructive call runs solely from :meth:`confirm`, which the pre-agent handler
chain invokes on an explicit human "yes". The model has no path from a tool call
to execution, so it cannot self-authorise — only a real user can.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class _PendingAction:
    name: str
    fn: Optional[Callable[[], Any]]
    success_message: str


class ConfirmationGate:
    """Holds at most one destructive action awaiting explicit user confirmation.

    One outstanding proposal at a time: a new :meth:`propose` replaces any prior
    pending action (the user is always confirming the most recent request).
    """

    def __init__(self) -> None:
        self._pending: Optional[_PendingAction] = None

    def has_pending(self) -> bool:
        """Whether an action is currently awaiting confirmation."""
        return self._pending is not None

    @property
    def pending_name(self) -> Optional[str]:
        """Name of the pending action, or ``None`` when nothing is pending."""
        return self._pending.name if self._pending is not None else None

    def propose(self, name: str, fn: Optional[Callable[[], Any]], success_message: str = "") -> dict:
        """Record a destructive action and return a ``confirmation_required`` result.

        Executes nothing. The returned dict is what the action tool hands back to
        the LLM so it asks the user to confirm; the real call waits for
        :meth:`confirm`.
        """
        self._pending = _PendingAction(name=name, fn=fn, success_message=success_message)
        return {
            "status": "confirmation_required",
            "action": name,
            "message": (
                f"'{name}' has a real beamline/hardware effect and needs explicit "
                "user confirmation before it runs. Ask the user to confirm — they "
                "must reply 'yes' to proceed or 'no' to cancel. Do NOT assume consent."
            ),
        }

    def confirm(self) -> dict:
        """Execute the pending action. Called only on explicit user confirmation.

        When the action returns a non-empty string, that string is the reported
        outcome — a confirmed submit that the guidance gate then blocks must
        report "submission blocked", not the canned success message. Actions
        returning ``None`` keep the declared ``success_message``.
        """
        pending = self._pending
        self._pending = None
        if pending is None:
            return {"error": "Nothing is awaiting confirmation."}
        if pending.fn is None:
            return {"error": f"{pending.name} action is not available in this session."}
        try:
            result = pending.fn()
        except Exception as exc:
            return {"error": str(exc)}
        if isinstance(result, str) and result:
            return {"status": "ok", "message": result}
        return {"status": "ok", "message": pending.success_message or f"{pending.name} completed."}

    def cancel(self) -> dict:
        """Discard the pending action without executing it."""
        name = self.pending_name
        self._pending = None
        return {"status": "cancelled", "action": name}
