"""Print-gated debug tracing shared by the steering view-model modules.

Verbose tracing for ViewModel actions; off by default. Gates the debug
statements which previously spammed stdout on every UI interaction and
per-second on the live-update loop. Set ``CRYSTALPILOT_DEBUG=1`` to re-enable.
"""

import os
from typing import Any

_DEBUG = bool(os.environ.get("CRYSTALPILOT_DEBUG"))


def _trace(*args: Any) -> None:
    if _DEBUG:
        print(*args)
