"""Test package for application."""

from exphub.app.views.main import MainApp


def test_app() -> None:
    app = MainApp()
    assert app
