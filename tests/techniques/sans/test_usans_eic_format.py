"""USANS EIC submission format tests.

Pins the instrument-scientist-specified BL-1A contract end-to-end:

  - a USANS strategy CSV carries exactly the columns
    ``Title,Comment,BL1A:Mot:Sample:X,BL1A:Mot:ARN,BL1A:CS:Scan:USANS1:Counts``,
  - rows sharing a ``BL1A:Mot:Sample:X`` value are one Sample (one physical
    sample position) and submit as **one** EIC table scan whose parameters are
    exactly ``{"run_mode": 0, "headers": [...], "rows": [...]}`` with the CSV
    cell values verbatim (strings, scientific notation preserved), and
  - a CSV in the wrong format is caught by the guidance check: missing
    required columns, blank required cells, and malformed sample positions
    block submission with errors; malformed non-group cell values are
    surfaced as warnings but allow it.

Also covers the monitor/control surface (poll / abort / stop) through the SANS
steering VM against the recording fake EIC client, and the missing-beamline
guards that used to raise ``KeyError``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

import exphub.beamlines  # noqa: F401 — registers TOPAZ + CORELLI + USANS
from exphub.core.beamline import set_active
from exphub.core.eic.control import EICControlModel
from exphub.techniques.sans.agent.eic_row_builder import SANS_EIC_ROW_BUILDER
from exphub.techniques.sans.models.root import SansMainModel
from exphub.techniques.sans.models.strategy import SansStrategyModel
from exphub.techniques.sans.view_models.steering import SansSteeringViewModel

_FIXTURE = Path(__file__).parent / "fixtures" / "usans_strategy.csv"

# The BL-1A contract, verbatim (instrument-scientist specified).
_HEADERS = ["Title", "Comment", "BL1A:Mot:Sample:X", "BL1A:Mot:ARN", "BL1A:CS:Scan:USANS1:Counts"]
_GROUP_KEY = "BL1A:Mot:Sample:X"
_ROWS = [
    ["test_01", "run1", "100.00", "1.00", "1.0E4"],
    ["test_01", "run1", "100.00", "5.00", "1.0E4"],
    ["test_01", "run1", "110.00", "1.00", "1.0E4"],
    ["test_01", "run1", "110.00", "5.00", "1.0E4"],
]
# Grouped by sample position: X=100.00 carries two analyzer-rotation steps,
# X=110.00 the other two — one EIC table scan each.
_ROWS_X100 = _ROWS[:2]
_ROWS_X110 = _ROWS[2:]


def teardown_module(_module: object) -> None:
    set_active("topaz")  # leave the process on a single-crystal beamline


class _FakeBind:
    """Records ``update_in_view`` pushes; ``connect`` is a view-side no-op."""

    def __init__(self) -> None:
        self.pushed: List[Any] = []

    def connect(self, _name: str) -> None:
        return None

    def update_in_view(self, value: Any = None) -> None:
        self.pushed.append(value)


class _FakeBinding:
    """Minimal ``BindingInterface`` stand-in for headless VM construction."""

    def new_bind(self, _model: Any = None, callback_after_update: Any = None, **_: Any) -> _FakeBind:
        return _FakeBind()


def _usans_vm(notify: Optional[List[str]] = None) -> SansSteeringViewModel:
    set_active("usans")
    notify_fn = notify.append if notify is not None else None
    binding: Any = _FakeBinding()  # duck-types the BindingInterface surface the VM uses
    return SansSteeringViewModel(SansMainModel(), binding, notify_fn=notify_fn)


def _usans_model() -> SansStrategyModel:
    model = SansStrategyModel(group_key=_GROUP_KEY, required_columns=list(_HEADERS))
    model.load_strategy(str(_FIXTURE))
    return model


# --------------------------------------------------------------------------- #
# format: CSV -> specs / groups
# --------------------------------------------------------------------------- #
def test_usans_vm_seeds_sample_x_grouping_from_spec() -> None:
    vm = _usans_vm()
    assert vm.model.strategy.group_key == _GROUP_KEY
    assert vm.model.strategy.required_columns == _HEADERS


def test_usans_csv_loads_one_sample_per_x_position() -> None:
    m = _usans_model()
    assert m.columns == _HEADERS
    assert len(m.strategy_list) == 4
    # Two Samples: rows sharing a sample-X position; the label is the position.
    assert [(g["holder"], g["label"], g["count"]) for g in m.groups] == [
        ("100.00", "100.00", 2),
        ("110.00", "110.00", 2),
    ]
    # The X group column is locked and float-typed (catalog); Title is an
    # ordinary required text column; the other PV columns are floats.
    by_key = {s["key"]: s for s in m.column_specs}
    assert by_key[_GROUP_KEY]["editable"] is False
    assert by_key[_GROUP_KEY]["required"] is True
    assert by_key[_GROUP_KEY]["type"] == "float"
    assert by_key["Title"]["editable"] is True
    assert by_key["Title"]["required"] is True
    assert by_key["Title"]["type"] == "str"
    assert by_key["BL1A:CS:Scan:USANS1:Counts"]["type"] == "float"


def test_usans_guidance_is_clean_on_wellformed_csv() -> None:
    m = _usans_model()
    result = m.guidance_check()
    assert result == {"errors": [], "warnings": []}


# --------------------------------------------------------------------------- #
# format: build_jobs / submitted payload — the exact BL-1A dict
# --------------------------------------------------------------------------- #
def test_build_jobs_emits_one_scan_per_x_position() -> None:
    m = _usans_model()
    jobs = SANS_EIC_ROW_BUILDER.build_jobs(m.strategy_list, group_key=_GROUP_KEY, columns=m.columns)
    assert len(jobs) == 2
    assert jobs[0]["headers"] == _HEADERS
    assert jobs[0]["rows"] == _ROWS_X100
    assert jobs[0]["title"] == "100.00"
    assert jobs[1]["headers"] == _HEADERS
    assert jobs[1]["rows"] == _ROWS_X110
    assert jobs[1]["title"] == "110.00"


def test_submit_sends_exact_bl1a_table_scans(fake_eic: Any) -> None:
    set_active("usans")
    m = _usans_model()
    jobs = SANS_EIC_ROW_BUILDER.build_jobs(m.strategy_list, group_key=_GROUP_KEY, columns=m.columns)

    ctrl = EICControlModel()
    ctrl.is_simulation = True
    ctrl.submit_jobs(jobs, ipts_number="IPTS-34567", instrument_name="USANS")

    assert ctrl.supported_beamline is True
    assert ctrl.beamline == "bl1a"
    submitted = fake_eic.all_submitted
    assert len(submitted) == 2
    # The wire payload is exactly the specified dict (plus the fixed run mode).
    assert submitted[0]["parms"] == {"run_mode": 0, "headers": _HEADERS, "rows": _ROWS_X100}
    assert submitted[1]["parms"] == {"run_mode": 0, "headers": _HEADERS, "rows": _ROWS_X110}
    # The description carries the first cell (the Title) of each scan.
    assert [s["desc"] for s in submitted] == ["CrystalPilot Submission test_01"] * 2
    assert [j["title"] for j in ctrl.submitted_jobs] == ["100.00", "110.00"]
    assert ctrl.eic_submission_success == [True, True]


def test_vm_submit_golden_path(fake_eic: Any) -> None:
    notifications: List[str] = []
    vm = _usans_vm(notifications)
    vm.model.iptsinfo.ipts_number = "IPTS-34567"
    vm.model.strategy.plan_file = str(_FIXTURE)
    vm.upload_strategy()
    assert vm.model.strategy.guidance_errors == []
    assert vm.model.strategy.guidance_warnings == []

    vm.model.eiccontrol.is_simulation = True
    vm.submit_strategy()
    assert vm.model.eiccontrol.eic_status == "job submission simulated"
    assert [s["parms"] for s in fake_eic.all_submitted] == [
        {"run_mode": 0, "headers": _HEADERS, "rows": _ROWS_X100},
        {"run_mode": 0, "headers": _HEADERS, "rows": _ROWS_X110},
    ]


# --------------------------------------------------------------------------- #
# format validation: wrong CSVs warn / block
# --------------------------------------------------------------------------- #
def test_missing_required_column_blocks_submission(tmp_path: Path, fake_eic: Any) -> None:
    bad = tmp_path / "missing_arn.csv"
    bad.write_text("Title,Comment,BL1A:Mot:Sample:X,BL1A:CS:Scan:USANS1:Counts\ntest_01,run1,100.00,1.0E4\n")
    notifications: List[str] = []
    vm = _usans_vm(notifications)
    vm.model.strategy.plan_file = str(bad)
    vm.upload_strategy()
    # Flagged already at upload time...
    assert any("BL1A:Mot:ARN" in e for e in vm.model.strategy.guidance_errors)
    assert any("format problem" in n for n in notifications)

    # ...and submission is refused: nothing reaches EIC.
    vm.submit_strategy()
    assert vm.model.eiccontrol.eic_status.startswith("submission blocked")
    assert fake_eic.all_submitted == []


def test_blank_title_blocks_submission(tmp_path: Path, fake_eic: Any) -> None:
    bad = tmp_path / "blank_title.csv"
    bad.write_text("Title,Comment,BL1A:Mot:Sample:X,BL1A:Mot:ARN,BL1A:CS:Scan:USANS1:Counts\n,run1,100.00,1.00,1.0E4\n")
    vm = _usans_vm()
    vm.model.strategy.plan_file = str(bad)
    vm.upload_strategy()
    assert any("'Title' is blank" in e for e in vm.model.strategy.guidance_errors)
    vm.submit_strategy()
    assert vm.model.eiccontrol.eic_status.startswith("submission blocked")
    assert fake_eic.all_submitted == []


def test_nonnumeric_sample_position_blocks(tmp_path: Path, fake_eic: Any) -> None:
    """A malformed group value (sample X) is a blocking error, not a warning.

    It would corrupt both the Sample grouping and the submitted motor position.
    """
    bad = tmp_path / "bad_x.csv"
    bad.write_text(
        "Title,Comment,BL1A:Mot:Sample:X,BL1A:Mot:ARN,BL1A:CS:Scan:USANS1:Counts\ntest_01,run1,abc,1.00,1.0E4\n"
    )
    vm = _usans_vm()
    vm.model.strategy.plan_file = str(bad)
    vm.upload_strategy()
    assert any("'abc' is not numeric" in e for e in vm.model.strategy.guidance_errors)
    vm.submit_strategy()
    assert vm.model.eiccontrol.eic_status.startswith("submission blocked")
    assert fake_eic.all_submitted == []


def test_nonnumeric_pv_value_warns_but_submits(tmp_path: Path, fake_eic: Any) -> None:
    odd = tmp_path / "bad_arn.csv"
    odd.write_text(
        "Title,Comment,BL1A:Mot:Sample:X,BL1A:Mot:ARN,BL1A:CS:Scan:USANS1:Counts\ntest_01,run1,100.00,abc,1.0E4\n"
    )
    notifications: List[str] = []
    vm = _usans_vm(notifications)
    vm.model.iptsinfo.ipts_number = "IPTS-34567"
    vm.model.strategy.plan_file = str(odd)
    vm.upload_strategy()
    assert vm.model.strategy.guidance_errors == []
    assert any("'abc' is not numeric" in w for w in vm.model.strategy.guidance_warnings)

    vm.model.eiccontrol.is_simulation = True
    vm.submit_strategy()
    # Warnings allow submission (surfaced via notify), per the guidance design.
    assert len(fake_eic.all_submitted) == 1
    assert any("warning" in n for n in notifications)


def test_blank_required_cell_blocks_submission(tmp_path: Path) -> None:
    bad = tmp_path / "blank_counts.csv"
    bad.write_text(
        "Title,Comment,BL1A:Mot:Sample:X,BL1A:Mot:ARN,BL1A:CS:Scan:USANS1:Counts\ntest_01,run1,100.00,1.00,\n"
    )
    vm = _usans_vm()
    vm.model.strategy.plan_file = str(bad)
    vm.upload_strategy()
    assert any("required column 'BL1A:CS:Scan:USANS1:Counts' is blank" in e for e in vm.model.strategy.guidance_errors)


def test_missing_group_column_reports_exactly_one_error(tmp_path: Path) -> None:
    """A CSV missing the sample-X group column yields one clear error.

    Regression guard: with the group column also listed in required_columns,
    the missing column used to be reported twice plus one misleading
    "is blank" line per row.
    """
    bad = tmp_path / "no_x.csv"
    bad.write_text(
        "Title,Comment,BL1A:Mot:ARN,BL1A:CS:Scan:USANS1:Counts\ntest_01,run1,1.00,1.0E4\ntest_01,run1,5.00,1.0E4\n"
    )
    vm = _usans_vm()
    vm.model.strategy.plan_file = str(bad)
    vm.upload_strategy()
    errors = vm.model.strategy.guidance_errors
    assert len([e for e in errors if _GROUP_KEY in e]) == 1
    assert not any("is blank" in e for e in errors)


def test_missing_title_column_reports_exactly_one_error(tmp_path: Path) -> None:
    """A CSV missing a required non-group column (Title) yields one clear error."""
    bad = tmp_path / "no_title.csv"
    bad.write_text(
        "Comment,BL1A:Mot:Sample:X,BL1A:Mot:ARN,BL1A:CS:Scan:USANS1:Counts\n"
        "run1,100.00,1.00,1.0E4\n"
        "run1,110.00,5.00,1.0E4\n"
    )
    vm = _usans_vm()
    vm.model.strategy.plan_file = str(bad)
    vm.upload_strategy()
    errors = vm.model.strategy.guidance_errors
    assert len([e for e in errors if "Title" in e]) == 1
    assert not any("is blank" in e for e in errors)


# --------------------------------------------------------------------------- #
# monitor / control
# --------------------------------------------------------------------------- #
def test_vm_poll_and_abort_lifecycle(fake_eic: Any) -> None:
    vm = _usans_vm()
    vm.model.iptsinfo.ipts_number = "IPTS-34567"
    vm.model.strategy.plan_file = str(_FIXTURE)
    vm.upload_strategy()
    vm.model.eiccontrol.is_simulation = True
    vm.submit_strategy()
    jobs = vm.model.eiccontrol.submitted_jobs
    assert [j["status"] for j in jobs] == ["submitted", "submitted"]

    # Poll: the fake reports every scan as done.
    vm.poll_job_statuses()
    assert [j["status"] for j in jobs] == ["done", "done"]
    assert all(j["is_done"] for j in jobs)
    assert fake_eic.last.status_checks == [jobs[0]["scan_id"], jobs[1]["scan_id"]]

    # Abort a single job by scan id.
    vm.model.eiccontrol.submitted_jobs[0]["status"] = "running"  # simulate a live job
    vm.abort_job(jobs[0]["scan_id"])
    assert vm.model.eiccontrol.submitted_jobs[0]["status"] == "aborted"
    assert vm.model.eiccontrol.submitted_jobs[1]["status"] == "done"  # untouched
    assert fake_eic.last.aborted == [jobs[0]["scan_id"]]


def test_vm_stop_run_aborts_current_scan(fake_eic: Any) -> None:
    vm = _usans_vm()
    vm.model.iptsinfo.ipts_number = "IPTS-34567"
    vm.model.strategy.plan_file = str(_FIXTURE)
    vm.upload_strategy()
    vm.model.eiccontrol.is_simulation = True
    vm.submit_strategy()
    current = vm.model.eiccontrol.eic_submission_scan_id
    assert current >= 0

    vm.stoprun()
    assert current in fake_eic.last.aborted


def test_unknown_instrument_is_guarded_everywhere(fake_eic: Any) -> None:
    """No EIC operation may raise on an unregistered instrument (KeyError guard)."""
    ctrl = EICControlModel()
    ctrl.submitted_jobs = [{"status": "submitted", "scan_id": 7, "is_done": False, "message": ""}]
    ctrl.stop_run("IPTS-1", "NOT_AN_INSTRUMENT")
    ctrl.poll_job_statuses("IPTS-1", "NOT_AN_INSTRUMENT")
    ctrl.abort_job(7, "IPTS-1", "NOT_AN_INSTRUMENT")
    assert ctrl.supported_beamline is False
    assert fake_eic.instances == []  # no client was ever constructed


# --------------------------------------------------------------------------- #
# editing on an X-position-keyed table
# --------------------------------------------------------------------------- #
def test_add_sample_on_x_grouping_appends_next_position() -> None:
    m = _usans_model()
    m.add_sample()
    # Numeric group column -> next integer above the existing positions, as a
    # visible placeholder the user adjusts via export/reload.
    assert [g["holder"] for g in m.groups] == ["100.00", "110.00", "111"]
    new_row = m.strategy_list[-1]
    assert new_row[_GROUP_KEY] == "111"
    assert new_row["Title"] == ""  # blank required cells block until filled in
    assert set(_HEADERS) <= {k for k in new_row if k != "id"}


def test_add_sample_on_empty_string_grouped_table_uses_placeholder() -> None:
    """A string group column (e.g. Title) seeds sample_<n>, not a number."""
    m = SansStrategyModel(group_key="Title", required_columns=list(_HEADERS))
    m.add_sample()
    assert [g["holder"] for g in m.groups] == ["sample_1"]
    assert m.strategy_list[0]["Title"] == "sample_1"


def test_export_roundtrip_preserves_bl1a_format(tmp_path: Path) -> None:
    m = _usans_model()
    out = tmp_path / "exported.csv"
    m.export_to_csv(str(out))
    m2 = SansStrategyModel(group_key=_GROUP_KEY, required_columns=list(_HEADERS))
    m2.load_strategy(str(out))
    assert m2.columns == _HEADERS
    assert [[r[k] for k in _HEADERS] for r in m2.strategy_list] == _ROWS


def test_simulation_flag_reaches_client(fake_eic: Any) -> None:
    set_active("usans")
    m = _usans_model()
    jobs = SANS_EIC_ROW_BUILDER.build_jobs(m.strategy_list, group_key=_GROUP_KEY, columns=m.columns)
    ctrl = EICControlModel()
    ctrl.is_simulation = False
    ctrl.submit_jobs(jobs, ipts_number="IPTS-34567", instrument_name="USANS")
    assert fake_eic.all_submitted[0]["simulate_only"] is False


def test_gated_submit_reports_blocked_not_success(fake_eic: Any) -> None:
    """Confirmed-but-guidance-blocked submit reports the block, submits nothing."""
    from exphub.agent.confirmation import ConfirmationGate

    vm = _usans_vm()  # empty table -> guidance blocks
    gate = ConfirmationGate()
    gate.propose("submit_strategy", vm.submit_strategy, "SANS strategy submitted to EIC.")
    result = gate.confirm()
    assert "submission blocked" in result["message"]
    assert fake_eic.all_submitted == []
