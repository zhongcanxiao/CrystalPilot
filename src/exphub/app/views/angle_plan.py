from typing import List, Dict
from nova.trame.view.components import InputField,RemoteFileInput
from ..view_models.main import MainViewModel
from nova.trame.view.layouts import GridLayout, HBoxLayout
from trame.widgets import vuetify3 as vuetify

class AnglePlanView:

    def __init__(self,view_model:MainViewModel) -> None:
        self.view_model = view_model
        #self.view_model.angleplan_bind.connect("model.angleplan")
        self.view_model.angleplan_bind.connect("model_angleplan")

        self.view_model.eiccontrol_bind.connect("model_eiccontrol")
        self.create_ui()

    def create_ui(self) -> None:
        #with vuetify.VRow():
        with GridLayout(columns=2):
            RemoteFileInput(v_model="model_eiccontrol.token_file", base_paths=["/HFIR", "/SNS"])
            vuetify.VBtn("Authenticate", click=self.view_model.call_load_token)
        with GridLayout(columns=4):
            InputField(v_model="model_angleplan.plan_name")#, type="button", label="Upload")
            InputField(v_model="model_angleplan.plan_type", type="select", items="model_angleplan.plan_type_list")
            RemoteFileInput(
                    v_model="model_angleplan.plan_file",
                    base_paths=["/HFIR", "/SNS", "/home/zx5/1-todo/6-hardware/"],
                    extensions=[".csv"],
                )
            vuetify.VBtn("Upload CSV", click=self.view_model.update_view)

        '''
        with vuetify.VRow():
            with vuetify.VCol(v_for="(item, index) in model_angleplan.test_list", v_bind__key="index"):
                vuetify.VListItem(v_text="item")
        '''
        #vuetify.VDataTable(
        #    headers=[ {"text": "Header", "value": "header"} ,
        #              {"text": "value", "value": "value"} ],
        #    items=[{"header": "Title", "value": "title"}, {"header": "Comment", "value": "comment"}],
        #   )

        #with vuetify.VRow():
        vuetify.VCardTitle("Angle Plan Table")
        with GridLayout(columns=7):
            vuetify.VListItem(v_for="header in model_angleplan.headers", v_text="header")
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
 
        #vuetify.VRow(v_for="header in model_angleplan.headers", v_text="header")
        print("model_angleplan.angle_list")
        print(self.view_model.model.angleplan.angle_list)
        print(len(self.view_model.model.angleplan.angle_list))
        vuetify.VRow(
            v_for="(angle, index) in model_angleplan.angle_list",
            #key="index",
            children=[
            vuetify.VRow(
                v_for="(key, keyindex) in angle",
                children=[
                    vuetify.VTextField(
                    v_model="key",
                    #v_model=f"model_angleplan.angle_list[0][""Comment""]",
                    #v_model="key",
                    #label=f"Angle: {key}",
                    dense=True,
                    hide_details=True,
                    align="center",

                    )
                ],
                dense=True,
                align="center",
                hide_details=True,


            )
            ],

            dense=True,
            align="center",
            hide_details=True,
        )
 
        with GridLayout(columns=3):
            InputField(v_model="model_eiccontrol.is_simulation", type="checkbox")
            vuetify.VBtn("Update Angles", click=self.view_model.update_view)
            vuetify.VBtn("Submit through EIC", click=self.view_model.submit_angle_plan)



#            vuetify.VListItem(v_for="angle in model_angleplan.angle_list", v_text="header")
#            with vuetify.Template(v_for="(angle, index) in model_angleplan.angle_list", v_bind__key="angle"):
#                vuetify.VList(v_model="angle")
#                with vuetify.VRow(v_for="(value, key) in angle"):
#                    vuetify.VListItem(v_model="value")


      #  InputField(v_model="model_eiccontrol.IPTS_number")
       # InputField(v_model="model_eiccontrol.instrument_name")


        with GridLayout(columns=1):
            vuetify.VBanner(
                    v_if="model_eiccontrol.eic_submission_success",
                    text="Submission Successful.",
                    #text="Submission Successful. Scan ID: {{model_eiccontrol.eic_submission_scan_id}}, Message: {{model_eiccontrol.eic_submission_message}}",
                    color="success",
                )

        '''
        vuetify.VDataTable(
            headers=[
            {"text": "Angle", "value": "angle"},
            {"text": "Value", "value": "value"}
            ],
            items="model_angleplan.angle_list",
            item_key="index",
            hide_default_footer=True,
            children=[
            vuetify.VDataTableFooter(
                v_for="(header, index) in headers",
                key="index",
                children=[
                vuetify.VDataTableHeaders(
                    children=["{{ header.text }}"]
                )
                ]
            ),
            vuetify.VDataTableRow(
                v_for="(item, index) in model_angleplan.angle_list",

                key="index",
                children=[
                vuetify.VDataTable(
                    v_for="(key, keyindex) in angle",
                    children=["{{ key }}"]
                ),
                vuetify.VDataTable(
                    children=["{{ item.value }}"]
                )
                ]
            )
            ]
        )
        '''



        '''
        vuetify.VDataTable(
            headers=[
                {"text": "Test", "value": "test"}
            ],
            items="model_angleplan.test_list",
            item_key="index",
            hide_default_footer=True,
            children=[
                vuetify.VDataTableRow(
                    v_for="(item, index) in model_angleplan.test_list",
                    key="index",
                    children=[
                        vuetify.VDataTableCell(children=["{{ item }}"])
                    ]
                )
            ]
        )
        '''
        #vuetify.VDataTable(items="model_angleplan.data", headers="model_angleplan.columns")
        #vuetify.VBtn("Click Me!", color="primary")

        '''
        vuetify.VDataTable(
            headers=[
            {"text": "Plan Name", "value": "plan_name"},
            {"text": "Plan File", "value": "plan_file"}
            ],
            items="model_angleplan.test_list",
            item_key="index",
            hide_default_footer=True,
            children=["{{ item }}"]
        )
        '''
        #vuetify.VList(
        #    v_for="( i d ) in model_angleplan.test_list",
        #    children=[
        #        vuetify.VListItemTitle(children=[vuetify.VTextField(v_model="model_angleplan.test_list", label="Angle")])
        #    ]
        #    #v_model="model_angleplan.test_list",
        #)


        #with vuetify.VList():
        #    with vuetify.Template(v_for="item in model_angleplan.test_list", v_bind__key="item"):
        #        vuetify.VListItem(children=[InputField(v_model="item", v_on__input="item = $event")])


        #vuetify.VList(
        #    v_for="(angle, index) in model_angleplan.angle_list",
        #    children=[
        #    vuetify.VListItemTitle(children=[vuetify.VTextField(v_model="{{ angle }}")])
        #    ]
        #)
        #vuetify.VBtn("Submit through EIC", click=self.view_model.update_view)
        #vuetify.VSpacer()
        '''
        vuetify.VList(
            v_model="model_angleplan.angle_list",
            children=[
            vuetify.VListItem(
                v_for="(angle, index) in model_angleplan.angle_list",
                key="index",
                children=[
                vuetify.VListItem(
                    v_for="(key, keyindex) in angle",
                    children=[
                    vuetify.VListItemTitle(children=[
                        vuetify.VTextField(
                        v_model="model_angleplan.angle_list",
                        #v_model=f"model_angleplan.angle_list[0][""Comment""]",
                        #v_model="key",
                        #label=f"Angle: {key}",
                        dense=True,
                        hide_details=True
                        )
                    ]),
                    ]
                )
                ]
            )
            ]
        )
        '''
        pass