"""Module for the factory that creates viewmodels used in the application."""

from typing import Any, Callable, Optional

from nova.mvvm.interface import BindingInterface

from ..agent.bridge import bridged_submodels
from ..core.beamline import active_technique
from .models.chat import ChatModel
from .view_models.app_shell import AppShellViewModel
from .view_models.chat import ChatViewModel


def _build_steering(model: Any, binding: BindingInterface, notify_fn: Optional[Callable[[str], None]]) -> Any:
    """Resolve and build the active technique's steering VM.

    The steering VM comes from the active technique manifest
    (``steering_vm_factory``), exactly like the root model comes from
    ``root_model_factory`` — the shell never names a technique class. A missing
    factory is a manifest wiring bug, not a fallback case: silently substituting
    another technique's VM would bind the wrong tab surface.
    """
    manifest = active_technique()
    factory = manifest.steering_vm_factory
    if factory is None:
        raise RuntimeError(
            f"Active technique {manifest.id!r} has no steering_vm_factory; "
            "every technique manifest must supply one (see techniques/*/manifest.py)."
        )
    return factory(model, binding, notify_fn=notify_fn)


def create_viewmodels(binding: BindingInterface) -> dict:
    # Root model is the active technique's composite, supplied by its manifest's
    # ``root_model_factory``; the steering VM is resolved the same way so the
    # shell never names a technique class. Both shipped techniques set the
    # factory, so a missing one is a manifest wiring bug, not a fallback case.
    root_factory = active_technique().root_model_factory
    if root_factory is None:
        raise RuntimeError(
            f"Active technique {active_technique().id!r} has no "
            "root_model_factory; every technique manifest must supply one "
            "(see techniques/*/manifest.py)."
        )
    model = root_factory()
    vm: dict = {}
    # The technique-agnostic shell owns tab navigation, the beamline
    # selector and the global snackbar; the steering VM owns the
    # technique tabs and reuses the shell snackbar via ``notify``.
    shell_vm = AppShellViewModel(binding)
    steering_vm = _build_steering(model, binding, shell_vm.notify)
    # On an inside-technique beamline switch the shell calls this hook on the
    # outgoing technique VM (cancel live-update, clear temporal buffers) before
    # the registry swaps. P3 deliverable 5.
    shell_vm.set_deactivate_hook(steering_vm.on_deactivate)
    vm["app_shell"] = shell_vm
    vm["steering"] = steering_vm

    # Chat / Agent viewmodel — shares the same technique root model so the
    # agent can read and write the same Pydantic fields the left-side tabs use.
    # Sub-model binds + action verbs resolve against the steering VM;
    # tab navigation resolves against the shell VM.
    chat_model = ChatModel()
    main_bindings = {name: getattr(steering_vm, f"{name}_bind") for name in bridged_submodels()}
    vm["chat"] = ChatViewModel(
        chat_model,
        model,
        binding,
        main_bindings,
        nav_fn=shell_vm.navigate_to_tab,
        main_vm=steering_vm,
    )

    return vm
