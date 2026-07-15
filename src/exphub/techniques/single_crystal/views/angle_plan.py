"""View module for angle plan."""

import logging

import numpy as np
import plotly.graph_objects as go
import trame
from nova.trame.view.components import InputField, RemoteFileInput
from nova.trame.view.layouts import GridLayout, HBoxLayout, VBoxLayout
from trame.widgets import html, plotly
from trame.widgets import vuetify3 as vuetify

from ..view_models.steering import SingleCrystalSteeringViewModel

logger = logging.getLogger(__name__)


class AnglePlanView:
    """View class for angle plan."""

    def __init__(self, view_model: SingleCrystalSteeringViewModel) -> None:
        self.view_model = view_model
        # self.view_model.angleplan_bind.connect("model.angleplan")
        self.view_model.angleplan_bind.connect("model_angleplan")
        self.view_model.eiccontrol_bind.connect("model_eiccontrol")
        self.view_model.angleplan_updatefigure_coverage_bind.connect(self.update_figure_coverage)
        self.is_editing = False
        self.fig_c = go.Figure()
        vertices = np.array(
            [
                [0, 0, 0],
                [1, 0, 0],
                [1, 1, 0],
                [0, 1, 0],
                [0, 0, 1],
                [1, 0, 1],
                [1, 1, 1],
                [0, 1, 1],
            ]
        )

        # Define faces
        faces = np.array(
            [
                [4, 0, 1, 2, 3],  # bottom
                [4, 4, 5, 6, 7],  # top
                [4, 0, 1, 5, 4],  # front
                [4, 1, 2, 6, 5],  # right
                [4, 2, 3, 7, 6],  # back
                [4, 3, 0, 4, 7],  # left
            ]
        )

        # Create a 3D mesh figure
        fig = go.Figure(
            data=[
                go.Mesh3d(
                    x=vertices[:, 0],
                    y=vertices[:, 1],
                    z=vertices[:, 2],
                    i=faces[:, 1],
                    j=faces[:, 2],
                    k=faces[:, 3],
                    color="lightblue",
                    opacity=0.50,
                )
            ]
        )

        # Update layout for better visualization
        fig.update_layout(
            scene={"xaxis_title": "X Axis", "yaxis_title": "Y Axis", "zaxis_title": "Z Axis", "aspectmode": "data"},
            title="3D Polyhedron Visualization",
        )
        self.fig_c = fig

        self.create_ui()

    def update_figure_converage(self, fig: go.Figure) -> None:
        pass

    def create_ui(self) -> None:
        # with vuetify.VRow():
        trame_server = trame.app.get_server()

        @trame_server.controller.trigger("edit_run")
        def edit_run(run_id: int) -> None:
            # state.is_editing = True
            # book = next((b for b in state.books if b["id"] == book_id), None)
            # if book:
            #    state.record = book.copy()
            #    state.dialog = True
            logger.debug("%s %s", "view id", run_id)
            self.view_model.edit_run(run_id)

        @trame_server.controller.trigger("remove_run")
        def remove_run(run_id: int) -> None:
            # state.books = [b for b in state.books if b["id"] != book_id]
            logger.debug("%s %s", "view id", run_id)
            self.view_model.remove_run(run_id)

        @trame_server.controller.trigger("save_run")
        def save_run() -> None:
            # state.books = [b for b in state.books if b["id"] != book_id]
            # self.view_model.save_run()
            self.view_model.save_run()

        with GridLayout(columns=2, gap="0.5em"):
            InputField(v_model="model_angleplan.plan_name")  # , type="button", label="Upload")
            InputField(v_model="model_angleplan.plan_type", type="select", items="model_angleplan.plan_type_list")

        with HBoxLayout(gap="0.5em"):
            RemoteFileInput(
                v_model="model_angleplan.plan_file",
                base_paths=[
                    "/HFIR",
                    "/SNS",
                ],
                # base_paths=["/HFIR", "/SNS", "/home/zx5/1-todo/6-hardware/"],
                extensions=[".csv"],
            )
            vuetify.VBtn("Upload Strategy", click=self.view_model.upload_strategy, style="align-self: center;")

        # vuetify.VCardTitle("CrystalPlan Table")

        with HBoxLayout(gap="0.5em", valign="center"):
            vuetify.VCardTitle("Experiment Run Strategy")
            InputField(
                v_model="model_angleplan.goniometer_type",
                items="model_angleplan.goniometer_type_options",
                type="select",
                label="Goniometer",
                density="compact",
                hide_details=True,
                style="max-width: 240px;",
            )
        with VBoxLayout(classes="border-lg border-primary mb-1", stretch=True):
            with vuetify.VDataTable(
                classes="flex-1-1",
                headers=("model_angleplan.angle_list_headers", []),  # TODO trame syntax,
                items=("model_angleplan.angle_list", []),
            ):
                with vuetify.Template(
                    raw_attrs=['v-slot:item.actions="{ item }"']
                ):  # TODO 'item' predefined by vuetify
                    with html.Div(classes="d-flex justify-end"):
                        with vuetify.VBtn(icon=True, size="small", click="trigger('edit_run', [item.id])"):
                            # with vuetify.VBtn(icon=True, size="small", click="trigger('edit_run', [item.id])"):
                            vuetify.VIcon("mdi-pencil")
                        with vuetify.VBtn(icon=True, size="small", click="trigger('remove_run', [item.id])"):
                            # with vuetify.VBtn(icon=True, size="small", click="trigger('delete_run', [item.id])"):
                            vuetify.VIcon("mdi-delete")

        with vuetify.VDialog(
            v_model="model_angleplan.runedit_dialog", max_width="500px"
        ):  # only v_modle and inputfield-items auto wrap string to js,
            with vuetify.VCard():
                vuetify.VCardTitle(
                    "{{ model_angleplan.is_editing_run ? 'Edit' : 'Add' }} a Run"  # todo handle bar syntax
                )
                vuetify.VCardSubtitle("{{ model_angleplan.is_editing_run ? 'Update' : 'Create' }} run strategy")
                with vuetify.VCardText():
                    vuetify.VTextField(
                        v_model="model_angleplan.run_record['title']",
                        label="Title",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                    )
                    vuetify.VTextField(
                        v_model="model_angleplan.run_record.comment",
                        label="Comment",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                    )
                    vuetify.VSelect(
                        v_model="model_angleplan.run_record.step_type",
                        items=("model_angleplan.step_type_options", []),
                        label="Step Type",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                    )
                    # Angle fields: phi only when ambient (cryo stage has no phi motor)
                    vuetify.VTextField(
                        v_model="model_angleplan.run_record.phi",
                        label="phi",
                        type="number",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                        v_if="model_angleplan.goniometer_type === 'Ambient goniometer'",
                    )
                    vuetify.VTextField(
                        v_model="model_angleplan.run_record.omega",
                        label="omega",
                        type="number",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                    )
                    # Angle-only termination fields
                    vuetify.VSelect(
                        v_model="model_angleplan.run_record.wait_for",
                        items=("model_angleplan.wait_for_list", []),
                        label="Wait For",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                        v_if="model_angleplan.run_record.step_type === 'angle'",
                    )
                    vuetify.VTextField(
                        v_model="model_angleplan.run_record.value",
                        label="Value",
                        type="number",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                        v_if="model_angleplan.run_record.step_type === 'angle'",
                    )
                    # Ramp-only fields
                    vuetify.VTextField(
                        v_model="model_angleplan.run_record.ramp_start",
                        label="Ramp Start (K)",
                        type="number",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                        v_if="model_angleplan.run_record.step_type === 'ramp'",
                    )
                    vuetify.VTextField(
                        v_model="model_angleplan.run_record.ramp_end",
                        label="Ramp End (K)",
                        type="number",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                        v_if="model_angleplan.run_record.step_type === 'ramp'",
                    )
                    vuetify.VTextField(
                        v_model="model_angleplan.run_record.ramp_rate",
                        label="Ramp Rate (K/min)",
                        type="number",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                        v_if="model_angleplan.run_record.step_type === 'ramp'",
                    )
                    vuetify.VTextField(
                        v_model="model_angleplan.run_record.ramp_soak",
                        label="Soak (s)",
                        type="number",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                        v_if="model_angleplan.run_record.step_type === 'ramp'",
                    )
                    vuetify.VTextField(
                        v_model="model_angleplan.run_record.ramp_run",
                        label="Run (0/1)",
                        type="number",
                        variant="outlined",
                        update_modelValue="flushState('model_angleplan')",
                        v_if="model_angleplan.run_record.step_type === 'ramp'",
                    )
                with vuetify.VCardActions():
                    vuetify.VBtn("Cancel", click=self.view_model.close_runedit_dialog, style="align-self: center;")
                    # #TODO: this one not working at this git version
                    # vuetify.VBtn("Cancel", click="model_angleplan.runedit_dialog = False")
                    vuetify.VSpacer()
                    vuetify.VBtn("Save", click="trigger('save_run')")
                    # vuetify.VBtn("Save", click="trigger('save_run')")

        # with GridLayout(columns=7):
        #    vuetify.VListItem(v_for="header in model_angleplan.headers", v_text="header")
        #    vuetify.VRow(
        #        v_for="(angle, index) in model_angleplan.angle_list",
        #        key="index",
        #        children=[
        #        vuetify.VRow(
        #            v_for="(key, keyindex) in angle",
        #            children=[
        #                vuetify.VTextField(
        #                v_model="key",
        #                #v_model=f"model_angleplan.angle_list[0][""Comment""]",
        #                #v_model="key",
        #                #label=f"Angle: {key}",
        #                dense=True,
        #                hide_details=True
        #                )
        #            ]
        #        )
        #        ]
        #    )

        # vuetify.VRow(v_for="header in model_angleplan.headers", v_text="header")
        logger.debug("model_angleplan.angle_list")
        logger.debug(self.view_model.model.angleplan.angle_list)
        logger.debug(len(self.view_model.model.angleplan.angle_list))

        # with vuetify.VRow( v_for="(angle, index) in model_angleplan.angle_list_pd",):
        #    InputField(v_model="model_angleplan.angle_list_pd[index].phi")
        #    InputField(v_model="model_angleplan.angle_list_pd[index].omega")

        @trame_server.controller.trigger("show_coverage")
        def show_coverage() -> None:
            # state.books = [b for b in state.books if b["id"] != book_id]
            logger.debug("view id")

            self.fig_c = self.view_model.get_figure_coverage()
            self.figure_coverage.update(self.fig_c)
            self.figure_coverage.state.flush()
            self.view_model.show_coverage()

        with HBoxLayout(gap="0.5em", halign="center"):
            vuetify.VBtn("Initialize Strategy", click=self.view_model.reset_run, style="align-self: center;")
            vuetify.VBtn(
                "Add a Run",
                prepend_icon="mdi-plus",
                click=self.view_model.add_run,
                # click="trigger('add_run')",
            )
            vuetify.VBtn("Show Coverage", click="trigger('show_coverage')", style="align-self: center;")
            # vuetify.VBtn("Show Coverage", click="trigger('show_coverage',[coverage_fig,])", style="align-self: center;")#noqa

        with HBoxLayout(gap="0.5em", valign="center"):
            RemoteFileInput(v_model="model_eiccontrol.token_file", base_paths=["/HFIR", "/SNS"])
            vuetify.VBtn("Authenticate", click=self.view_model.call_load_token)
            InputField(v_model="model_eiccontrol.is_simulation", type="checkbox")
            # vuetify.VBtn("Update Strategy", click=self.view_model.update_view, style="align-self: center;")
            # html.Div(style="height: 20px;")
            vuetify.VBtn("Submit through EIC", click=self.view_model.submit_angle_plan)
            vuetify.VChip(
                "{{ model_eiccontrol.eic_status }}",
                color="model_eiccontrol.eic_status === 'authenticated successfully' ? 'blue'"
                " : model_eiccontrol.eic_status === 'jobs submitted' ? 'green'"
                " : model_eiccontrol.eic_status === 'job submission simulated' ? 'orange'"
                " : model_eiccontrol.eic_status.startsWith('submission failed') || model_eiccontrol.eic_status.startsWith('authentication failed') ? 'red'"  # noqa: E501
                " : 'grey'",
                variant="flat",
                style="font-weight: bold;",
            )

        with vuetify.VDialog(
            v_model="model_angleplan.is_showing_coverage", max_width="500px"
        ):  # only v_modle and inputfield-items auto wrap string to js,
            with vuetify.VCard():
                vuetify.VCardTitle(
                    "Coverage"  # todo handle bar syntax
                )
                vuetify.VCardSubtitle(
                    "Visualization of coverage of reflections by the instrument with sample orientations from the "
                    "current strategy."
                )
            """
            fig_coverage=go.Figure()
            # Generate random points in 3D space
            points = np.random.rand(30, 3)

            # Compute the convex hull
            hull = ConvexHull(points)

            # Extract the vertices and simplices
            vertices = points[hull.vertices]
            simplices = hull.simplices

            # Add the polyhedron to the figure
            for simplex in simplices:
                fig_coverage.add_trace(go.Mesh3d(
                    x=points[simplex, 0],
                    y=points[simplex, 1],
                    z=points[simplex, 2],
                    color='lightblue',
                    opacity=0.50
                ))
            #fig_coverage.update_layout(
            #    title={
            #    'text': 'Prediction of Signal Noise Ratio',
            #    'x': 0.5,
            #    'xanchor': 'center'
            #    },
            #    xaxis_title='Time Steps (s)',
            #    yaxis_title=' ',
            #    xaxis=dict(range=[0, 2000]),
            #    yaxis=dict(range=[0, 100]),
            #    paper_bgcolor='rgba(10,10,10,0)',
            #    plot_bgcolor='rgba(0,0,0,0)',
            #)
            """
            with HBoxLayout(halign="left", height="40vh"):
                # vuetify.VCardTitle("Prediction of Intensity"),
                #        self.figure_intensity
                self.figure_coverage = plotly.Figure()
                self.figure_coverage.update(self.fig_c)
            with HBoxLayout(
                halign="left",
            ):
                vuetify.VBtn("Close", click=self.view_model.close_coverage, style="align-self: center;")
                vuetify.VBtn(
                    "Turn on Symmetry",
                    click=self.view_model.update_coverage_figure_with_symmetry,
                    style="align-self: center;",
                )
                vuetify.VBtn(
                    "Turn off Symmetry", click=self.view_model.update_coverage_figure, style="align-self: center;"
                )
            # with vuetify.VCardActions():
            #        vuetify.VBtn("Close", click=self.view_model.close_coverage, style="align-self: center;")
            # vuetify.VBtn("Close", click="model_angleplan.runedit_dialog = False")#TODO: this one not working at this git version#noqa
            # vuetify.VSpacer()
        #######################################################################################

        # InputField(v_model="model_eiccontrol.ipts_number")
        # InputField(v_model="model_eiccontrol.instrument_name")

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

        @trame_server.controller.trigger("abort_job")
        def abort_job(scan_id: int) -> None:
            logger.debug("%s %s", "abort_job scan_id", scan_id)
            self.view_model.abort_job(scan_id)

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
                        click="trigger('abort_job', [item.scan_id])",
                        disabled="item.status === 'done' || item.status === 'aborted' || item.status === 'failed'",
                    ):
                        vuetify.VIcon("mdi-stop-circle-outline")

    def update_figure_coverage(self, fig: go.Figure) -> None:
        self.figure_coverage.update(fig)
        self.figure_coverage.state.flush()
