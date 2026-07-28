"""Framework-agnostic EIC control model.

Holds the EIC authentication / submission / polling / abort plumbing shared
by every technique. It is *technique-agnostic*: it submits pre-built
table-scan jobs (``headers`` + ``row`` + display metadata) produced by a
per-technique row builder. The single-crystal row builder lives in
``exphub.techniques.single_crystal.agent.eic_row_builder``; P3a.2 will
formalize the seam as an ``EICRowBuilder`` protocol on the
``TechniqueManifest``.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..beamline import active as _active_beamline
from ..beamline import get as _get_beamline
from ..beamline import list_ids as _beamline_ids
from .eic_client import EICClient

logger = logging.getLogger(__name__)


def _default_beamline_code() -> str:
    try:
        return _active_beamline().eic.beamline_code
    except Exception:
        return ""


def _default_beamline_database() -> Dict[str, str]:
    """Mantid instrument name → EIC beamline code, across all registered beamlines.

    Technique-neutral (reads :attr:`BeamlineSpec.mantid_instrument_name`, not a
    single-crystal-specific path) and resilient: each beamline is resolved
    independently so one mis-configured or other-technique beamline can't blank
    the whole map — a bug that previously left *every* technique unable to submit.
    """
    db: Dict[str, str] = {}
    for bid in _beamline_ids():
        try:
            spec = _get_beamline(bid)
            name = spec.mantid_instrument_name
            if name:
                db[name] = spec.eic.beamline_code
        except Exception:
            continue
    return db


def _default_beamline_server_urls() -> Dict[str, str]:
    """Mantid instrument name → explicit EIC server URL, where a spec sets one.

    Only non-empty ``EICSpec.server_url`` values appear here; an absent entry
    means "let the EIC client derive the URL from the beamline code" (the
    normal case). Same per-entry resilience as the beamline-code map.
    """
    urls: Dict[str, str] = {}
    for bid in _beamline_ids():
        try:
            spec = _get_beamline(bid)
            name = spec.mantid_instrument_name
            url = spec.eic.server_url
            if name and url:
                urls[name] = url
        except Exception:
            continue
    return urls


class SubmittedJob(BaseModel):
    """A single submitted EIC job."""

    index: int = 0
    title: str = ""
    scan_id: int = -1
    phi: float = 0.0
    omega: float = 0.0
    status: str = "pending"
    is_done: bool = False
    message: str = ""


class EICControlModel(BaseModel):
    """Model for EIC Control."""

    class Config:
        """Pydantic config options."""

        arbitrary_types_allowed = True  # Allow arbitrary types like EICClient

    username: str = Field(
        default="test_name",
        min_length=1,
        title="User Name",
        description="Please provide the name of the user",
        examples=["user"],
    )
    token: str = Field(default="test_password", title="IPTS token")
    token_file: str = Field(default="", title="IPTS token")

    is_simulation: bool = Field(default=True, title="Simulation")
    beamline: str = Field(
        default_factory=_default_beamline_code,
        title="Beamline",
        description="Name of the beamline",
    )
    beamline_database: Dict = Field(
        default_factory=_default_beamline_database,
        title="Beamline Database",
    )
    # Explicit per-instrument EIC server URLs (only instruments whose spec sets
    # EICSpec.server_url); everything else lets the client derive the URL.
    beamline_server_urls: Dict = Field(
        default_factory=_default_beamline_server_urls,
        title="Beamline Server URLs",
    )

    eic_submission_success: List[bool] = Field(default=[False], title="EIC Submission Success")
    eic_submission_message: List[str] = Field(default=["No message"], title="EIC Submission Message")
    eic_submission_scan_id: int = Field(default=-1, title="EIC Submission Scan ID")
    eic_submission_status: str = Field(default="No status", title="EIC Submission Status")
    eic_status: str = Field(default="not authenticated", title="EIC Status")

    eic_auto_stop_strategy: str = Field(default="By Uncertainty", title="Auto Steering Strategy")
    eic_auto_stop_strategy_options: List[str] = Field(
        default=["By Uncertainty", "By SNR", "No Auto Stop"], title="EIC Auto Stop Strategy"
    )
    eic_auto_stop_uncertainty_threshold: float = Field(default=0.1, title="Threshold")
    eic_auto_stop_snr_threshold: float = Field(default=10.0, title="Threshold SNR")

    eic_submission_scan_id_list: List[int] = Field(default=[-1], title="EIC Submission Scan ID List")
    current_scan_idx: int = Field(default=0, title="Current Scan Index")

    correct_run_format: bool = Field(default=True, title="Correct Run Format")
    supported_beamline: bool = Field(default=True, title="Supported Beamline")

    submitted_jobs: List[Dict] = Field(default=[], title="Submitted Jobs")
    submitted_jobs_headers: List[Dict] = Field(
        default=[
            {"title": "#", "key": "index", "sortable": False, "width": "50px"},
            {"title": "Title", "key": "title", "sortable": False},
            {"title": "Scan ID", "key": "scan_id", "sortable": False},
            {"title": "Phi", "key": "phi", "sortable": False},
            {"title": "Omega", "key": "omega", "sortable": False},
            {"title": "Status", "key": "status", "sortable": False},
            {"title": "Message", "key": "message", "sortable": False},
            {"title": "Actions", "key": "actions", "sortable": False},
        ],
        title="Submitted Jobs Headers",
    )

    def load_token(self, file_path: str) -> None:
        # The token is a credential — never print or log its value.
        with open(file_path, mode="r") as tokenfile:
            self.token = tokenfile.read()

    def _make_client(self, instrument_name: str, ipts_number: str) -> Optional[EICClient]:
        """Resolve the instrument to an EIC client, or ``None`` if unsupported.

        Central guard for every EIC operation: an instrument missing from the
        beamline map flips ``supported_beamline`` and returns ``None`` instead
        of raising ``KeyError`` mid-operation. When the beamline spec sets an
        explicit ``server_url`` it is passed through as ``url_base`` (otherwise
        the client derives the URL from the beamline code).
        """
        code = self.beamline_database.get(instrument_name, "")
        if not code:
            logger.warning("Instrument %r is not a registered beamline; skipping EIC operation.", instrument_name)
            self.supported_beamline = False
            return None
        self.supported_beamline = True
        self.beamline = code
        url_base = self.beamline_server_urls.get(instrument_name) or None
        return EICClient(self.token, beamline=code, ipts_number=ipts_number, url_base=url_base)

    def submit_jobs(
        self,
        jobs: List[Dict[str, Any]],
        ipts_number: str,
        instrument_name: str,
    ) -> None:
        """Submit pre-built EIC table-scan jobs.

        ``jobs`` is a list of payloads produced by a per-technique row builder.
        Each entry carries the EIC table-scan ``headers`` plus **either** a
        single ``row`` (one scan row — single-crystal) **or** a ``rows`` list
        (a multi-row table scan — SANS submits one scan per Sample holder), plus
        the display metadata the EIC Control panel renders (``title``/``phi``/
        ``omega``; ``phi``/``omega`` default to ``0.0`` for techniques without
        goniometer angles). ``rows`` is preferred when present; otherwise the
        singular ``row`` is wrapped as a one-row scan, so existing single-crystal
        callers are unaffected. The framework stays technique-agnostic — it never
        inspects column names.
        """
        eic_client = self._make_client(instrument_name, ipts_number)
        if eic_client is None:
            return
        eic_client.is_eic_enabled(print_results=True)

        desc = "CrystalPilot Submission"

        self.eic_submission_success = []
        self.eic_submission_message = []
        self.eic_submission_scan_id_list = []
        self.submitted_jobs = []
        for idx, job in enumerate(jobs):
            headers = job["headers"]
            # Prefer a multi-row payload (``rows``); fall back to the singular
            # ``row`` wrapped as a one-row scan (single-crystal callers).
            rows = job.get("rows")
            if rows is None:
                rows = [job["row"]]
            first_row = rows[0] if rows else []
            desc_sub = desc + " " + str(first_row[0]) if first_row else desc
            logger.debug("Submitting table scan: run_mode=0 headers=%s rows=%s", headers, rows)
            success, scan_id, response_data = eic_client.submit_table_scan(
                parms={"run_mode": 0, "headers": headers, "rows": rows},
                desc=desc_sub,
                simulate_only=self.is_simulation,
            )
            logger.debug("Submit result: success=%s scan_id=%s response=%s", success, scan_id, response_data)
            self.eic_submission_success.append(success)
            self.eic_submission_message.append(response_data["eic_response_message"])
            self.eic_submission_scan_id_list.append(scan_id)

            submitted = SubmittedJob(
                index=idx + 1,
                title=job.get("title", ""),
                scan_id=scan_id if scan_id is not None else -1,
                phi=job.get("phi", 0.0) or 0.0,
                omega=job.get("omega", 0.0) or 0.0,
                status="submitted" if success else "failed",
                is_done=False,
                message=response_data.get("eic_response_message", ""),
            )
            self.submitted_jobs.append(submitted.model_dump())
        self.current_scan_idx = 0
        if self.eic_submission_scan_id_list:
            self.eic_submission_scan_id = self.eic_submission_scan_id_list[self.current_scan_idx]

    def stop_run(self, ipts_number: str, instrument_name: str) -> None:
        """Abort the currently selected scan (``eic_submission_scan_id``)."""
        eic_client = self._make_client(instrument_name, ipts_number)
        if eic_client is None:
            return
        eic_client.is_eic_enabled(print_results=True)
        logger.debug(
            "Aborting scan %s (all submitted: %s)", self.eic_submission_scan_id, self.eic_submission_scan_id_list
        )
        eic_client.abort_scan(scan_id=self.eic_submission_scan_id)

    def poll_job_statuses(self, ipts_number: str, instrument_name: str) -> None:
        """Poll EIC for the current status of all submitted jobs."""
        if not self.submitted_jobs:
            return
        eic_client = self._make_client(instrument_name, ipts_number)
        if eic_client is None:
            return
        terminal_states = {"done", "aborted", "failed", "stopped"}
        for job in self.submitted_jobs:
            if job["status"] in terminal_states:
                continue
            scan_id = job["scan_id"]
            if scan_id < 0:
                continue
            try:
                success, is_done, state, response_data = eic_client.get_scan_status(scan_id=scan_id)
                if success and state is not None:
                    job["status"] = str(state).lower()
                    job["is_done"] = bool(is_done)
                elif not success:
                    job["status"] = "error"
                    job["message"] = response_data.get("eic_response_message", "status check failed")
            except Exception as e:
                job["status"] = "error"
                job["message"] = str(e)

    def abort_job(self, scan_id: int, ipts_number: str, instrument_name: str) -> None:
        """Abort a single job by scan_id."""
        eic_client = self._make_client(instrument_name, ipts_number)
        if eic_client is None:
            return
        try:
            eic_client.abort_scan(scan_id=scan_id)
            for job in self.submitted_jobs:
                if job["scan_id"] == scan_id:
                    job["status"] = "aborted"
                    job["is_done"] = True
        except Exception as e:
            for job in self.submitted_jobs:
                if job["scan_id"] == scan_id:
                    job["message"] = f"abort failed: {e}"
