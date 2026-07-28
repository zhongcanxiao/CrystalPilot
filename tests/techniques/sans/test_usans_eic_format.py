"""USANS EIC submission format tests.

Pins the instrument-scientist-specified BL-1A contract end-to-end:

  - a USANS strategy CSV carries exactly the columns
    ``Title,Comment,BL1A:Mot:Sample:X,BL1A:Mot:ARN,BL1A:CS:Scan:USANS1:Counts``,
  - rows sharing a ``Title`` are one Sample and submit as **one** EIC table
    scan whose parameters are exactly
    ``{"run_mode": 0, "headers": [...], "rows": [...]}`` with the CSV cell
    values verbatim (strings, scientific notation preserved), and
  - a CSV in the wrong format is caught by the guidance check: missing
    required columns block submission with errors; malformed cell values are
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
_ROWS = [
    ["test_01", "run1", "100.00", "1.00", "1.0E4"],
    ["test_01", "run1", "100.00", "5.00", "1.0E4"],
    ["test_01", "run1", "110.00", "1.00", "1.0E4"],
    ["test_01", "run1", "110.00", "5.00", "1.0E4"],
]


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


def _title_model() -> SansStrategyModel:
    model = SansStrategyModel(group_key="Title", required_columns=list(_HEADERS))
    model.load_strategy(str(_FIXTURE))
    return model


# --------------------------------------------------------------------------- #
# format: CSV -> specs / groups
# --------------------------------------------------------------------------- #
def test_usans_vm_seeds_title_grouping_from_spec() -> None:
    vm = _usans_vm()
    assert vm.model.strategy.group_key == "Title"
    assert vm.model.strategy.required_columns == _HEADERS


def test_usans_csv_loads_one_sample_per_title() -> None:
    m = _title_model()
    assert m.columns == _HEADERS
    assert len(m.strategy_list) == 4
    # One Sample: all four rows share Title "test_01"; the label is the Title.
    assert [(g["holder"], g["label"], g["count"]) for g in m.groups] == [("test_01", "test_01", 4)]
    # The Title group column is locked and typed str; PV columns are floats.
    by_key = {s["key"]: s for s in m.column_specs}
    assert by_key["Title"]["editable"] is False
    assert by_key["Title"]["required"] is True
    assert by_key["Title"]["type"] == "str"
    assert by_key["BL1A:Mot:Sample:X"]["type"] == "float"
    assert by_key["BL1A:CS:Scan:USANS1:Counts"]["type"] == "float"


def test_usans_guidance_is_clean_on_wellformed_csv() -> None:
    m = _title_model()
    result = m.guidance_check()
    assert result == {"errors": [], "warnings": []}


# --------------------------------------------------------------------------- #
# format: build_jobs / submitted payload — the exact BL-1A dict
# --------------------------------------------------------------------------- #
def test_build_jobs_emits_exact_bl1a_headers_and_rows() -> None:
    m = _title_model()
    jobs = SANS_EIC_ROW_BUILDER.build_jobs(m.strategy_list, group_key="Title")
    assert len(jobs) == 1
    job = jobs[0]
    assert job["headers"] == _HEADERS
    assert job["rows"] == _ROWS
    assert job["title"] == "test_01"


def test_submit_sends_exact_bl1a_table_scan(fake_eic: Any) -> None:
    set_active("usans")
    m = _title_model()
    jobs = SANS_EIC_ROW_BUILDER.build_jobs(m.strategy_list, group_key="Title")

    ctrl = EICControlModel()
    ctrl.is_simulation = True
    ctrl.submit_jobs(jobs, ipts_number="IPTS-34567", instrument_name="USANS")

    assert ctrl.supported_beamline is True
    assert ctrl.beamline == "bl1a"
    submitted = fake_eic.all_submitted
    assert len(submitted) == 1
    # The wire payload is exactly the specified dict (plus the fixed run mode).
    assert submitted[0]["parms"] == {"run_mode": 0, "headers": _HEADERS, "rows": _ROWS}
    assert submitted[0]["desc"] == "CrystalPilot Submission test_01"
    assert [j["title"] for j in ctrl.submitted_jobs] == ["test_01"]
    assert ctrl.eic_submission_success == [True]


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
    assert fake_eic.all_submitted[0]["parms"] == {"run_mode": 0, "headers": _HEADERS, "rows": _ROWS}


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


def test_nonnumeric_pv_value_warns_but_submits(tmp_path: Path, fake_eic: Any) -> None:
    odd = tmp_path / "bad_x.csv"
    odd.write_text(
        "Title,Comment,BL1A:Mot:Sample:X,BL1A:Mot:ARN,BL1A:CS:Scan:USANS1:Counts\ntest_01,run1,abc,1.00,1.0E4\n"
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
    assert [j["status"] for j in jobs] == ["submitted"]

    # Poll: the fake reports every scan as done.
    vm.poll_job_statuses()
    assert [j["status"] for j in jobs] == ["done"]
    assert all(j["is_done"] for j in jobs)
    assert fake_eic.last.status_checks == [jobs[0]["scan_id"]]

    # Abort a single job by scan id.
    vm.model.eiccontrol.submitted_jobs[0]["status"] = "running"  # simulate a live job
    vm.abort_job(jobs[0]["scan_id"])
    assert vm.model.eiccontrol.submitted_jobs[0]["status"] == "aborted"
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
# editing on a Title-keyed table
# --------------------------------------------------------------------------- #
def test_add_sample_on_title_grouping_generates_unique_name() -> None:
    m = _title_model()
    m.add_sample()
    assert [g["holder"] for g in m.groups] == ["sample_1", "test_01"]
    new_row = m.strategy_list[-1]
    assert new_row["Title"] == "sample_1"
    # The new row carries every required column (blank, to be filled in).
    assert set(_HEADERS) <= {k for k in new_row if k != "id"}


def test_export_roundtrip_preserves_bl1a_format(tmp_path: Path) -> None:
    m = _title_model()
    out = tmp_path / "exported.csv"
    m.export_to_csv(str(out))
    m2 = SansStrategyModel(group_key="Title", required_columns=list(_HEADERS))
    m2.load_strategy(str(out))
    assert m2.columns == _HEADERS
    assert [[r[k] for k in _HEADERS] for r in m2.strategy_list] == _ROWS


def test_simulation_flag_reaches_client(fake_eic: Any) -> None:
    set_active("usans")
    m = _title_model()
    jobs = SANS_EIC_ROW_BUILDER.build_jobs(m.strategy_list, group_key="Title")
    ctrl = EICControlModel()
    ctrl.is_simulation = False
    ctrl.submit_jobs(jobs, ipts_number="IPTS-34567", instrument_name="USANS")
    assert fake_eic.all_submitted[0]["simulate_only"] is False
