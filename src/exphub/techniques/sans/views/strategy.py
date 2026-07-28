"""SANS strategy / experiment-steering tab view — flexible, Sample-grouped table.

The SANS strategy surface. Unlike the single-crystal fixed goniometer table, the
SANS table is **column-flexible** and **grouped by the beamline's group column**
(``Title`` on USANS; legacy ``BL1A:sampleholder`` elsewhere): one expandable
panel per Sample, each showing that Sample's steps with **inline-editable**
cells (every column except the group column, which is locked). The columns,
their labels, and their editor type (enum drop-down
vs free text) come from ``model_strategy.column_specs``, which is built at upload
time — so this view renders whatever columns the uploaded CSV carried without any
hard-coded column list.

Controls:
  - **Upload Strategy** — load the CSV named in ``plan_file`` (defaults to the
    USANS example file for USANS).
  - inline cell edits — write straight into ``model_strategy.strategy_list`` via
    ``flushState``.
  - **Add step** (per Sample) / **Add Sample** / delete-step — grow/shrink the plan.
  - **Export Strategy** — write the edited table to ``export_file``.
  - EIC **Authenticate** / **Submit** — submission runs a pre-submission guidance
    check first (errors block; warnings are shown but allow submit); each Sample
    is submitted as one EIC table-scan carrying all of its steps.

Binds the strategy model under ``model_strategy`` and the shared EIC control model
under ``model_eiccontrol``.
"""

import trame
from nova.trame.view.components import InputField, RemoteFileInput
from nova.trame.view.layouts import GridLayout, HBoxLayout, VBoxLayout
from trame.widgets import html
from trame.widgets import vuetify3 as vuetify

from ..view_models.steering import SansSteeringViewModel


class SansStrategyView:
    """View class for the SANS experiment-strategy tab."""

    def __init__(self, view_model: SansSteeringViewModel) -> None:
        self.view_model = view_model
        self.view_model.strategy_bind.connect("model_strategy")
        self.view_model.eiccontrol_bind.connect("model_eiccontrol")
        self.create_ui()

    def create_ui(self) -> None:
        trame_server = trame.app.get_server()

        @trame_server.controller.trigger("sans_add_step")
        def add_step(holder: object) -> None:
            self.view_model.add_step(holder)

        @trame_server.controller.trigger("sans_remove_step")
        def remove_step(row_id: int) -> None:
            self.view_model.remove_step(row_id)

        @trame_server.controller.trigger("sans_abort_job")
        def abort_job(scan_id: int) -> None:
            self.view_model.abort_job(scan_id)

        with GridLayout(columns=1, gap="0.5em"):
            InputField(v_model="model_strategy.plan_name")

        # Upload row: pick + load a strategy CSV.
        with HBoxLayout(gap="0.5em", valign="center"):
            RemoteFileInput(
                v_model="model_strategy.plan_file",
                base_paths=["/HFIR", "/SNS"],
                extensions=[".csv"],
            )
            vuetify.VBtn("Upload Strategy", click=self.view_model.upload_strategy, style="align-self: center;")

        # Export row: free-text destination path (may be a new file) + export.
        with HBoxLayout(gap="0.5em", valign="center"):
            InputField(v_model="model_strategy.export_file", label="Export file path")
            vuetify.VBtn("Export Strategy", click=self.view_model.export_strategy, style="align-self: center;")

        vuetify.VCardTitle("SANS Experiment Run Strategy — grouped by sample holder")

        # Guidance messages (populated by a submit-time guidance check).
        vuetify.VAlert(
            "Cannot submit — fix these: {{ model_strategy.guidance_errors.join('  •  ') }}",
            v_if="model_strategy.guidance_errors && model_strategy.guidance_errors.length",
            type="error",
            variant="tonal",
            density="comfortable",
            classes="mb-1",
        )
        vuetify.VAlert(
            "Warnings: {{ model_strategy.guidance_warnings.join('  •  ') }}",
            v_if="model_strategy.guidance_warnings && model_strategy.guidance_warnings.length",
            type="warning",
            variant="tonal",
            density="comfortable",
            classes="mb-1",
        )

        # Empty state: nothing loaded yet.
        vuetify.VAlert(
            "Upload a strategy CSV (it must contain a '{{ model_strategy.group_key }}' column), "
            "or click “Add Sample” to start one.",
            v_if="!model_strategy.groups || model_strategy.groups.length === 0",
            type="info",
            variant="tonal",
            density="comfortable",
            classes="mb-1",
        )

        # One expandable panel per Sample (holder group).
        with vuetify.VExpansionPanels(multiple=True, variant="accordion", classes="mb-1"):
            with vuetify.VExpansionPanel(
                v_for="(group, gi) in model_strategy.groups",
                __properties=[("key", ":key")],
                key="gi",
            ):
                vuetify.VExpansionPanelTitle("{{ group.label }} · {{ group.count }} step(s)")
                with vuetify.VExpansionPanelText():
                    # Column-label header row (aligned with the cell row below).
                    with html.Div(classes="d-flex align-center font-weight-bold text-caption mb-2"):
                        with html.Template(
                            v_for="(col, ci) in model_strategy.column_specs",
                            __properties=[("key", ":key")],
                            key="ci",
                        ):
                            html.Div("{{ col.label }}", classes="flex-1-1 px-1")
                        html.Div("", style="width: 44px;")

                    # One editable row per step belonging to this Sample.
                    with html.Template(
                        v_for="(row, ri) in model_strategy.strategy_list",
                        __properties=[("key", ":key")],
                        key="row.id",
                    ):
                        with html.Div(
                            v_if="String(row[model_strategy.group_key]) === String(group.holder)",
                            classes="d-flex align-center mb-1",
                        ):
                            with html.Template(
                                v_for="(col, ci) in model_strategy.column_specs",
                                __properties=[("key", ":key")],
                                key="ci",
                            ):
                                with html.Div(classes="flex-1-1 px-1"):
                                    # Locked group key (sample holder) — read-only.
                                    vuetify.VChip(
                                        "{{ row[col.key] }}",
                                        v_if="col.key === model_strategy.group_key",
                                        size="small",
                                        color="primary",
                                        variant="tonal",
                                    )
                                    # Enum column -> dropdown of its options.
                                    vuetify.VSelect(
                                        v_if="col.key !== model_strategy.group_key && col.type === 'enum'",
                                        v_model="row[col.key]",
                                        items=("col.options",),
                                        density="compact",
                                        variant="outlined",
                                        hide_details=True,
                                        update_modelValue="flushState('model_strategy')",
                                    )
                                    # Any other column -> free-text field.
                                    vuetify.VTextField(
                                        v_if="col.key !== model_strategy.group_key && col.type !== 'enum'",
                                        v_model="row[col.key]",
                                        density="compact",
                                        variant="outlined",
                                        hide_details=True,
                                        update_modelValue="flushState('model_strategy')",
                                    )
                            with vuetify.VBtn(
                                icon=True,
                                size="small",
                                variant="text",
                                click="trigger('sans_remove_step', [row.id])",
                            ):
                                vuetify.VIcon("mdi-delete")

                    with HBoxLayout(gap="0.5em", halign="left"):
                        vuetify.VBtn(
                            "Add step",
                            size="small",
                            prepend_icon="mdi-plus",
                            variant="tonal",
                            click="trigger('sans_add_step', [group.holder])",
                        )

        with HBoxLayout(gap="0.5em", halign="center"):
            vuetify.VBtn(
                "Add Sample",
                prepend_icon="mdi-plus",
                click=self.view_model.add_sample,
            )

        # EIC authenticate + submit row (shared pipeline; per-Sample table scans).
        with HBoxLayout(gap="0.5em", valign="center"):
            RemoteFileInput(v_model="model_eiccontrol.token_file", base_paths=["/HFIR", "/SNS"])
            vuetify.VBtn("Authenticate", click=self.view_model.call_load_token)
            InputField(v_model="model_eiccontrol.is_simulation", type="checkbox")
            vuetify.VBtn("Submit through EIC", click=self.view_model.submit_strategy)
            vuetify.VChip(
                "{{ model_eiccontrol.eic_status }}",
                color="model_eiccontrol.eic_status === 'authenticated successfully' ? 'blue'"
                " : model_eiccontrol.eic_status === 'jobs submitted' ? 'green'"
                " : model_eiccontrol.eic_status === 'job submission simulated' ? 'orange'"
                " : model_eiccontrol.eic_status.startsWith('submission failed') || model_eiccontrol.eic_status.startsWith('authentication failed') || model_eiccontrol.eic_status.startsWith('submission blocked') ? 'red'"  # noqa: E501
                " : 'grey'",
                variant="flat",
                style="font-weight: bold;",
            )

        with GridLayout(columns=4, gap="0.5em"):
            InputField(
                v_model="model_eiccontrol.eic_auto_stop_strategy",
                type="select",
                items="model_eiccontrol.eic_auto_stop_strategy_options",
            )
            InputField(v_model="model_eiccontrol.eic_auto_stop_uncertainty_threshold")
            InputField(v_model="model_eiccontrol.eic_submission_scan_id", label="Scan ID")
            vuetify.VBtn("Manual Stop Run", click=self.view_model.stoprun, style="align-self: center;")

        vuetify.VCardTitle("Submitted Jobs")
        with HBoxLayout(gap="0.5em", halign="center"):
            vuetify.VBtn(
                "Refresh Status",
                prepend_icon="mdi-refresh",
                click=self.view_model.poll_job_statuses,
            )

        with VBoxLayout(classes="border-lg border-primary mb-1", stretch=True):
            with vuetify.VDataTable(
                classes="flex-1-1",
                headers=("model_eiccontrol.submitted_jobs_headers", []),
                items=("model_eiccontrol.submitted_jobs", []),
            ):
                with vuetify.Template(raw_attrs=['v-slot:item.status="{ item }"']):
                    vuetify.VChip(
                        "{{ item.status }}",
                        color="item.status === 'done' ? 'green'"
                        " : item.status === 'running' ? 'blue'"
                        " : item.status === 'submitted' ? 'orange'"
                        " : item.status === 'aborted' ? 'grey'"
                        " : item.status === 'failed' || item.status === 'error' ? 'red'"
                        " : 'default'",
                        variant="flat",
                        size="small",
                    )
                with vuetify.Template(raw_attrs=['v-slot:item.actions="{ item }"']):
                    with vuetify.VBtn(
                        icon=True,
                        size="small",
                        click="trigger('sans_abort_job', [item.scan_id])",
                        disabled="item.status === 'done' || item.status === 'aborted' || item.status === 'failed'",
                    ):
                        vuetify.VIcon("mdi-stop-circle-outline")
