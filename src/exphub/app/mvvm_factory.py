"""Module for the factory that creates viewmodels used in the application."""

from nova.mvvm.interface import BindingInterface

from .models.main_model import MainModel
from .view_models.main import MainViewModel


def create_viewmodels(binding: BindingInterface) -> dict:
    model = MainModel()
    vm: dict = {}
    vm["main"] = MainViewModel(model, binding)

    return vm
