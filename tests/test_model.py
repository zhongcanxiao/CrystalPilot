"""Test package for model classes."""

from exphub.app.models.main_model import MainModel


def test_main_model_defaults() -> None:
    model = MainModel()
    assert model.username == "test_name"
    assert model.password == "test_password"
