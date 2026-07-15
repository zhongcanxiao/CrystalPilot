"""Right-side chat panel view for CrystalPilot.

Renders an inline right panel (not an overlay drawer) containing:
- A scrollable message list (user / assistant bubbles)
- A text input bar at the bottom
- A thinking / status indicator
"""

from __future__ import annotations

import logging

from trame.widgets import client
from trame.widgets import vuetify3 as vuetify
from trame_client.widgets import html
from trame_server import Server

from ..view_models.chat import ChatViewModel

logger = logging.getLogger(__name__)

# ── CSS for chat bubbles (injected via trame client.Style) ─────────────
_CHAT_RESIZE_JS = """
window._chatResizeStart = function(event) {
    event.preventDefault();
    var pane = event.currentTarget.parentElement;
    var startX = event.clientX;
    var startWidth = pane.offsetWidth;
    function onMove(e) {
        var newWidth = startWidth - (e.clientX - startX);
        newWidth = Math.max(250, Math.min(900, newWidth));
        pane.style.flex = '0 0 ' + newWidth + 'px';
    }
    function onUp() {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
    }
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'ew-resize';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
};
"""

_CHAT_CSS = """
.chat-bubble {
    max-width: 90%;
    padding: 10px 14px;
    border-radius: 12px;
    margin: 4px 0;
    word-wrap: break-word;
    font-size: 0.85rem;
    line-height: 1.5;
    flex-shrink: 0;
}
.chat-bubble-user {
    background-color: #e0e0e0;
    color: #212121;
    align-self: flex-end;
    margin-left: 40px;
    border-bottom-right-radius: 4px;
    white-space: pre-wrap;
}
.chat-bubble-assistant {
    background-color: #e8f5e9;
    color: #212121;
    align-self: flex-start;
    margin-right: 40px;
    border-bottom-left-radius: 4px;
    overflow-x: auto;
    max-height: 500px;
    overflow-y: auto;
}
/* Markdown elements inside assistant bubbles */
.chat-bubble-assistant h2,
.chat-bubble-assistant h3,
.chat-bubble-assistant h4 {
    margin: 6px 0 4px 0;
    font-size: 0.95rem;
    font-weight: 600;
}
.chat-bubble-assistant h2 { font-size: 1.0rem; }
.chat-bubble-assistant pre {
    background: #e0e0e0;
    border-radius: 6px;
    padding: 8px 10px;
    overflow-x: auto;
    font-size: 0.8rem;
    margin: 6px 0;
    white-space: pre;
}
.chat-bubble-assistant code {
    background: #e0e0e0;
    border-radius: 3px;
    padding: 1px 4px;
    font-size: 0.8rem;
    font-family: 'Roboto Mono', monospace;
}
.chat-bubble-assistant pre code {
    background: none;
    padding: 0;
}
.chat-bubble-assistant ul,
.chat-bubble-assistant ol {
    margin: 4px 0;
    padding-left: 20px;
}
.chat-bubble-assistant li {
    margin: 2px 0;
}
.chat-bubble-assistant strong {
    font-weight: 600;
}
.chat-bubble-assistant table {
    border-collapse: collapse;
    width: 100%;
    font-size: 0.8rem;
    margin: 6px 0;
}
.chat-bubble-assistant th,
.chat-bubble-assistant td {
    border: 1px solid #c8c8c8;
    padding: 4px 8px;
}
.chat-bubble-assistant th {
    background: #d7ecd9;
    font-weight: 600;
}
.chat-bubble-assistant tr:nth-child(even) {
    background: #f5faf5;
}
.chat-messages-container {
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    flex: 1 1 0;
    min-height: 0;
    padding: 12px;
    gap: 6px;
}
.chat-input-area {
    flex: 0 0 auto;
    padding: 8px 12px;
    border-top: 1px solid #e0e0e0;
}
.chat-status-bar {
    flex: 0 0 auto;
    padding: 2px 12px;
    font-size: 0.75rem;
    color: #757575;
    font-style: italic;
    min-height: 20px;
}
.chat-resize-handle {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 5px;
    cursor: ew-resize;
    z-index: 10;
    background: transparent;
    transition: background 0.15s;
}
.chat-resize-handle:hover {
    background: rgba(0, 0, 0, 0.12);
}
"""


class ChatPaneView:
    """Builds the right-side inline chat panel UI for the NeuDiff Agent."""

    def __init__(self, server: Server, chat_vm: ChatViewModel) -> None:
        self.server = server
        self.chat_vm = chat_vm
        self.ctrl = server.controller

        # Register the submit trigger. trame automatically awaits async trigger
        # handlers (protocol.py: `if inspect.isawaitable(result): await result`).
        self.ctrl.trigger("chat_submit")(self._on_submit)

        # Connect the chat binding to a trame reactive namespace
        self.chat_vm.chat_bind.connect("chat")

        self.create_ui()

    # ------------------------------------------------------------------ UI

    def create_ui(self) -> None:
        # Inject CSS via trame's client.Style (safe, doesn't use v-html)
        client.Style(_CHAT_CSS)
        client.Script(_CHAT_RESIZE_JS)

        # Inline right panel — shown/hidden via v-show so it squeezes the
        # sibling tab-content div rather than overlaying it.
        with html.Div(
            v_show="chat.drawer_open",
            style=(
                "flex: 0 0 400px; display: flex; flex-direction: column; "
                "border-left: 1px solid rgba(0,0,0,0.12); background: white; "
                "overflow: hidden; position: relative;"
            ),
        ):
            # ── Resize handle (drag left edge to resize) ──
            html.Div(
                classes="chat-resize-handle",
                mousedown="window._chatResizeStart($event)",
            )
            # ── Header ──
            with vuetify.VToolbar(density="compact", color="primary"):
                vuetify.VToolbarTitle("NeuDiff Agent", style="font-size: 0.95rem;")
                vuetify.VSpacer()
                vuetify.VBtn(
                    icon="mdi-close",
                    variant="text",
                    click=self.chat_vm.toggle_drawer,
                )

            # ── Messages area ──
            with html.Div(classes="chat-messages-container", ref="chatMessages"):
                with html.Template(v_for="(msg, idx) in chat.messages", __properties=[("key", ":key")], key="idx"):
                    # User bubble: plain text, light grey, right-aligned
                    html.Div(
                        "{{ msg.content }}",
                        v_if="msg.role === 'user'",
                        classes="chat-bubble chat-bubble-user",
                    )
                    # Assistant bubble: rendered markdown, light green, left-aligned
                    html.Div(
                        v_if="msg.role === 'assistant'",
                        v_html="msg.html || msg.content",
                        classes="chat-bubble chat-bubble-assistant",
                    )

                # Thinking indicator
                with html.Div(
                    v_show="chat.is_thinking",
                    classes="chat-bubble chat-bubble-assistant",
                    style="font-style: italic; opacity: 0.7;",
                ):
                    html.Span("Thinking ...")

            # ── Status bar (debug / processing step) ──
            with html.Div(classes="chat-status-bar"):
                html.Span("{{ chat.agent_status }}")

            # ── Input area ──
            with html.Div(classes="chat-input-area"):
                with vuetify.VRow(no_gutters=True, align="center", style="gap: 4px;"):
                    with vuetify.VCol():
                        vuetify.VTextField(
                            v_model="chat.user_input",
                            placeholder="Ask NeuDiff Agent…",
                            variant="outlined",
                            density="compact",
                            hide_details=True,
                            # keyup fires AFTER the v-model state is updated;
                            # keydown can race with the state sync.
                            **{"@keyup.enter": "trigger('chat_submit', [chat.user_input])"},
                        )
                    vuetify.VBtn(
                        icon="mdi-send",
                        color="primary",
                        variant="tonal",
                        size="small",
                        click="trigger('chat_submit', [chat.user_input])",
                    )

        # Field-update snackbar (shown briefly when the agent writes parameters)
        with vuetify.VSnackbar(
            v_model="chat.update_snackbar_visible",
            timeout=3000,
            color="success",
            location="bottom left",
        ):
            html.Span("{{ chat.last_update_summary }}")

    # ------------------------------------------------------------------ handler

    async def _on_submit(self, text: str = "") -> None:
        """Trigger handler — trame awaits async trigger results automatically."""
        logger.debug(f"[ChatPane] _on_submit called, text='{text}'")
        # Fallback: if the trigger arg arrived empty (state-sync race), read the
        # current value from the Python model (which the state.change callback
        # keeps in sync from v-model updates).
        if not text or not text.strip():
            text = self.chat_vm.chat_model.user_input
            logger.debug(f"[ChatPane] fallback to model user_input='{text}'")
        if not text or not text.strip():
            logger.debug("[ChatPane] text is empty, ignoring submit")
            return
        await self.chat_vm.handle_submit(text.strip())
