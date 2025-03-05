"""Main Application."""

import sys


def main() -> None:
    kwargs = {}
    from .views.main import MainApp

    app = MainApp()
    for arg in sys.argv[2:]:
        try:
            key, value = arg.split("=")
            kwargs[key] = int(value)
        except Exception:
            pass
    #app.create_task(app.view_model.auto_update_cssstatus_figure())
    app.server.start(**kwargs)
