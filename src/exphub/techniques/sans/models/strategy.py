"""SANS experiment-strategy model — flexible-column strategy table.

Unlike the single-crystal ``AnglePlanModel`` (which has a fixed goniometer-shaped
row), the SANS strategy table is **column-flexible**: a strategy CSV may carry an
arbitrary set of columns with arbitrary names and types. The only guaranteed
column is the **group column** (:attr:`SansStrategyModel.group_key`), whose value
groups rows into **Samples** — every row sharing a group value is one Sample's
measurement steps, submitted to EIC as one multi-row table scan.

The group column is beamline-configurable (``SansConfig.group_key``): the legacy
default is :data:`GROUP_KEY` (``BL1A:sampleholder``, an integer holder index);
USANS groups by ``Title`` (a string), so a USANS CSV like::

    Title,Comment,BL1A:Mot:Sample:X,BL1A:Mot:ARN,BL1A:CS:Scan:USANS1:Counts
    test_01,run1,100.00,1.00,1.0E4
    test_01,run1,100.00,5.00,1.0E4

is one Sample ("test_01") carrying two steps, and submits as one EIC table scan
whose ``headers``/``rows`` are the CSV verbatim.

The table is discovered at upload time:

  - :meth:`SansStrategyModel.load_strategy` reads the CSV, preserves the column
    order into :attr:`~SansStrategyModel.columns`, builds a per-column
    :data:`ColumnSpec` list (:func:`build_column_specs`), keeps every cell value
    as a string (lossless round-trip), injects a stable ``id`` per row, and
    computes the Sample groups.
  - The view renders one expandable panel per Sample and edits cells inline
    (every column except the group key).
  - :meth:`export_to_csv` writes the edited table back out in the original
    column order.

Column typing (enum / number / string) is inferred from the data and/or supplied
by :data:`COLUMN_CATALOG` — the seam for the authoritative column description the
SANS scientist will provide later. Types drive validation
(:meth:`guidance_check`) and which inline editor the view shows; values
themselves are stored verbatim as strings.
"""

from __future__ import annotations

import csv
from typing import Any, Dict, List

from pydantic import BaseModel, Field

# The one column every SANS strategy CSV must contain. Its integer value groups
# rows into Samples. Not editable in the UI.
GROUP_KEY = "BL1A:sampleholder"

# ---------------------------------------------------------------------------
# Column description seam (request item 2 — "complete description added later").
#
# COLUMN_CATALOG maps a raw CSV header -> partial ColumnSpec overrides that WIN
# over inference. Entries below are the instrument-scientist-specified USANS
# (BL-1A) strategy columns; a catalogued ``required: True`` column with a blank
# cell is a blocking guidance error (missing-column checks use the per-beamline
# ``SansConfig.required_columns`` instead, since specs only exist for columns
# the CSV actually carries). Columns absent from the catalog keep falling back
# to inference (see infer_column_spec), so non-USANS SANS CSVs still work.
# ---------------------------------------------------------------------------
COLUMN_CATALOG: Dict[str, Dict[str, Any]] = {
    "Title": {"type": "str", "label": "Title", "required": True},
    "Comment": {"type": "str", "label": "Comment"},
    "BL1A:Mot:Sample:X": {"type": "float", "label": "Sample X", "required": True},
    "BL1A:Mot:ARN": {"type": "float", "label": "Analyzer Rotation", "required": True},
    "BL1A:CS:Scan:USANS1:Counts": {"type": "float", "label": "Counts", "required": True},
}

# Columns whose name (case-insensitive) marks them as an enum, with the known
# control words. Observed values not in the list are appended so nothing a CSV
# actually contains is rejected by the dropdown. Extend as columns are specified.
_KNOWN_ENUMS: Dict[str, List[str]] = {
    "wait for": ["seconds", "Counts", "PCharge", "minutes", "hours"],
}

# A ColumnSpec is a plain dict (kept JSON-serialisable so it can cross the trame
# binding to the view). Shape:
#   {"key": str, "label": str, "type": "int"|"float"|"str"|"enum",
#    "options": List[str], "editable": bool, "required": bool}
ColumnSpec = Dict[str, Any]


def _looks_float(s: Any) -> bool:
    try:
        float(str(s))
        return True
    except (TypeError, ValueError):
        return False


def _looks_int(s: Any) -> bool:
    try:
        f = float(str(s))
        return f == int(f)
    except (TypeError, ValueError):
        return False


def infer_column_spec(name: str, values: List[Any], group_key: str = GROUP_KEY) -> ColumnSpec:
    """Infer a :data:`ColumnSpec` for a column from its name and sample values.

    The group column is always forced to a non-editable, required column; its
    type follows its values (``int`` for holder-index grouping, ``str`` for
    Title-style grouping — blank/absent values default to ``int`` for the
    legacy holder column). A column named like a known enum becomes an enum; a
    column whose non-blank values are all numeric becomes ``int``/``float``;
    everything else is ``str``.
    """
    label = str(name)
    if name == group_key:
        nonblank = [str(v).strip() for v in values if str(v).strip() != ""]
        group_type = "int" if (not nonblank or all(_looks_int(v) for v in nonblank)) else "str"
        return {
            "key": name,
            "label": "Sample Holder" if name == GROUP_KEY else label,
            "type": group_type,
            "options": [],
            "editable": False,
            "required": True,
        }

    nonblank = [str(v).strip() for v in values if str(v).strip() != ""]

    low = name.strip().lower()
    if low in _KNOWN_ENUMS:
        options: List[str] = list(_KNOWN_ENUMS[low])
        for v in nonblank:
            if v not in options:
                options.append(v)
        return {"key": name, "label": label, "type": "enum", "options": options, "editable": True, "required": False}

    if nonblank and all(_looks_float(v) for v in nonblank):
        col_type = "int" if all(_looks_int(v) for v in nonblank) else "float"
        return {"key": name, "label": label, "type": col_type, "options": [], "editable": True, "required": False}

    return {"key": name, "label": label, "type": "str", "options": [], "editable": True, "required": False}


def build_column_specs(columns: List[str], rows: List[Dict[str, Any]], group_key: str = GROUP_KEY) -> List[ColumnSpec]:
    """Build the per-column :data:`ColumnSpec` list (catalog overrides inference).

    The group column stays locked (non-editable, required) even when a catalog
    entry covers it.
    """
    specs: List[ColumnSpec] = []
    for name in columns:
        values = [r.get(name, "") for r in rows]
        spec = infer_column_spec(name, values, group_key=group_key)
        override = COLUMN_CATALOG.get(name)
        if override:
            spec = {**spec, **override, "key": name}
            spec.setdefault("label", name)
            spec.setdefault("options", [])
            spec.setdefault("editable", name != group_key)
            spec.setdefault("required", name == group_key)
        if name == group_key:
            spec["editable"] = False
            spec["required"] = True
        specs.append(spec)
    return specs


def _holder_sort_key(holder: Any) -> tuple[int, Any]:
    """Sort holders numerically when possible, else lexicographically."""
    try:
        return (0, int(float(str(holder))))
    except (TypeError, ValueError):
        return (1, str(holder))


class SansStrategyModel(BaseModel):
    """CSV-loadable, column-flexible SANS strategy table, grouped by Sample."""

    # The mandatory grouping column. Beamline-configurable (seeded from
    # ``SansConfig.group_key`` by the steering VM): USANS groups by "Title";
    # the legacy default is the sample-holder PV.
    group_key: str = Field(default=GROUP_KEY, title="Group Key")

    # Columns the active beamline requires a strategy CSV to contain (seeded
    # from ``SansConfig.required_columns``). Missing ones are blocking guidance
    # errors. Empty means only the group column is enforced.
    required_columns: List[str] = Field(default_factory=list, title="Required Columns")

    # Raw CSV column order (excludes the injected ``id``). Drives export order and
    # the inline editor column order.
    columns: List[str] = Field(default_factory=list, title="Columns")
    # Per-column ColumnSpec dicts (see build_column_specs). Pushed to the view so
    # it knows each column's label / type / options / editability.
    column_specs: List[Dict] = Field(default_factory=list, title="Column Specs")

    # Canonical editable rows: string cell values keyed by raw column name, plus a
    # stable integer ``id``. This is the surface the inline editor writes to.
    strategy_list: List[Dict] = Field(
        default_factory=list,
        title="SANS Strategy",
        description="Flexible-column strategy rows (string cells + id), grouped by the sample-holder column.",
    )
    # Sample groups derived from strategy_list: one entry per distinct holder,
    # holder-sorted. Pushed to the view to render the expandable panels.
    groups: List[Dict] = Field(default_factory=list, title="Sample Groups")

    # Raw rows as read from the CSV, before id injection. Excluded from state pushes.
    strategy_list_read: List[Dict] = Field(
        default_factory=list,
        title="SANS Strategy (raw)",
        description="Rows as read from the uploaded CSV before normalisation.",
        exclude=True,
    )

    plan_name: str = Field(default="CrystalPilot SANS Plan", title="Strategy Name")
    plan_file: str = Field(default="", title="Strategy File", description="File path to the strategy CSV to upload.")
    export_file: str = Field(
        default="", title="Export File", description="Destination path for exporting the edited strategy CSV."
    )

    # Last pre-submission guidance result, pushed to the view for display.
    guidance_errors: List[str] = Field(default_factory=list, title="Guidance Errors")
    guidance_warnings: List[str] = Field(default_factory=list, title="Guidance Warnings")

    # ------------------------------------------------------------------ #
    # CSV load / export
    # ------------------------------------------------------------------ #
    def load_strategy(self, file_path: str) -> None:
        """Read a flexible-column SANS strategy CSV into ``strategy_list``.

        Preserves column order, skips fully blank lines, builds ``column_specs``,
        keeps every cell as a string, injects a stable ``id``, and recomputes the
        Sample groups.
        """
        with open(file_path, mode="r", newline="") as f:
            reader = csv.DictReader(f)
            columns = list(reader.fieldnames or [])
            raw_rows: List[Dict[str, Any]] = []
            for row in reader:
                if any(str(v or "").strip() for v in row.values()):
                    raw_rows.append({k: ("" if v is None else str(v)) for k, v in row.items() if k is not None})

        self.columns = columns
        self.strategy_list_read = [dict(r) for r in raw_rows]
        self.column_specs = build_column_specs(columns, raw_rows, group_key=self.group_key)

        new_list: List[Dict] = []
        for i, raw in enumerate(raw_rows):
            record: Dict[str, Any] = {"id": i + 1}
            for col in columns:
                record[col] = str(raw.get(col, "") or "")
            new_list.append(record)
        self.strategy_list = new_list
        self.recompute_groups()

    def export_to_csv(self, file_path: str) -> str:
        """Write the edited table back out in the original column order.

        The injected ``id`` is dropped; cell values are written verbatim, so a
        load → export round-trip is lossless (modulo the ``id``). Returns the
        path written.
        """
        fieldnames = list(self.columns)
        with open(file_path, mode="w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in self.strategy_list:
                writer.writerow({k: row.get(k, "") for k in fieldnames})
        return file_path

    # ------------------------------------------------------------------ #
    # grouping + row editing helpers
    # ------------------------------------------------------------------ #
    def recompute_groups(self) -> None:
        """Rebuild ``groups`` (one per distinct holder value, holder-sorted)."""
        counts: Dict[str, int] = {}
        for row in self.strategy_list:
            holder = str(row.get(self.group_key, "")).strip()
            counts[holder] = counts.get(holder, 0) + 1
        ordered = sorted(counts, key=_holder_sort_key)
        self.groups = [
            {
                "holder": holder,
                "label": self._group_label(holder),
                "count": counts[holder],
            }
            for holder in ordered
        ]

    def _group_label(self, holder: str) -> str:
        """Label a group: "Sample <n>" for holder-index grouping, else the raw value."""
        if holder == "":
            return "Sample (unassigned)"
        return f"Sample {holder}" if self.group_key == GROUP_KEY else str(holder)

    def _next_id(self) -> int:
        return max((int(r.get("id", 0)) for r in self.strategy_list), default=0) + 1

    def _ensure_schema(self) -> None:
        """Seed a minimal schema (group + required columns) if nothing is loaded yet."""
        if not self.columns:
            self.columns = [self.group_key] + [c for c in self.required_columns if c != self.group_key]
            self.column_specs = build_column_specs(self.columns, [], group_key=self.group_key)

    def blank_row(self, holder: Any = "") -> Dict[str, Any]:
        """Build a new empty row for the current columns, holder pre-filled."""
        self._ensure_schema()
        record: Dict[str, Any] = {"id": self._next_id()}
        for col in self.columns:
            record[col] = str(holder) if col == self.group_key else ""
        return record

    def add_step(self, holder: Any) -> None:
        """Append a new empty step to the Sample identified by ``holder``."""
        self.strategy_list.append(self.blank_row(holder))
        self.recompute_groups()

    def add_sample(self) -> None:
        """Append a new Sample with one empty step.

        For integer (holder-index) grouping the new group value is the next
        integer; for string grouping (e.g. Title) it is a unique ``sample_<n>``
        placeholder the user renames via export/reload.
        """
        self._ensure_schema()
        existing_raw = [str(row.get(self.group_key, "")).strip() for row in self.strategy_list]
        existing_ints: List[int] = []
        for value in existing_raw:
            try:
                existing_ints.append(int(float(value)))
            except (TypeError, ValueError):
                continue
        nonblank = [v for v in existing_raw if v != ""]
        if existing_ints or not nonblank:
            next_holder: Any = (max(existing_ints) + 1) if existing_ints else 1
        else:
            n = 1
            while f"sample_{n}" in nonblank:
                n += 1
            next_holder = f"sample_{n}"
        self.strategy_list.append(self.blank_row(next_holder))
        self.recompute_groups()

    def remove_step(self, row_id: int) -> None:
        """Delete the step with the given id and recompute groups."""
        self.strategy_list = [r for r in self.strategy_list if int(r.get("id", -1)) != int(row_id)]
        self.recompute_groups()

    # ------------------------------------------------------------------ #
    # pre-submission guidance (request item 5 — real rules TBD)
    # ------------------------------------------------------------------ #
    def guidance_check(self) -> Dict[str, List[str]]:
        """Validate the table before EIC submission.

        Returns ``{"errors": [...], "warnings": [...]}``. Errors block submission;
        warnings are surfaced but allow it. The starter rules below cover
        structural integrity of the sample-holder grouping and per-column typing;
        real scientific guidance (allowed ranges, holder occupancy, exposure
        limits, …) is TBD with the SANS scientist and drops in where marked.
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not self.strategy_list:
            errors.append("Strategy table is empty — upload a CSV or add a Sample before submitting.")
        if self.columns and self.group_key not in self.columns:
            errors.append(
                f"Required column '{self.group_key}' is missing from the strategy "
                f"(CSV columns: {', '.join(self.columns)})."
            )

        # Beamline-required columns (SansConfig.required_columns): a strategy
        # CSV in the wrong format is caught here, before anything reaches EIC.
        if self.columns:
            for col in self.required_columns:
                if col not in self.columns:
                    errors.append(f"Required column '{col}' is missing from the strategy CSV.")

        specs_by_key = {str(s.get("key")): s for s in self.column_specs}
        group_spec = specs_by_key.get(self.group_key, {})
        group_is_int = group_spec.get("type", "int" if self.group_key == GROUP_KEY else "str") == "int"

        for row in self.strategy_list:
            holder = str(row.get(self.group_key, "")).strip()
            rid = row.get("id")
            if holder == "":
                errors.append(f"Row {rid}: '{self.group_key}' is blank.")
            elif group_is_int:
                try:
                    int(float(holder))
                except (TypeError, ValueError):
                    errors.append(f"Row {rid}: '{self.group_key}' value '{holder}' is not an integer.")

        for row in self.strategy_list:
            rid = row.get("id")
            for key, spec in specs_by_key.items():
                if key == self.group_key:
                    continue
                value = str(row.get(key, "")).strip()
                if value == "":
                    if spec.get("required"):
                        errors.append(f"Row {rid}: required column '{key}' is blank.")
                    continue
                col_type = spec.get("type")
                if col_type in ("int", "float") and not _looks_float(value):
                    warnings.append(f"Row {rid} column '{key}': '{value}' is not numeric.")
                elif col_type == "enum":
                    options = [str(o) for o in spec.get("options", [])]
                    if options and value not in options:
                        warnings.append(f"Row {rid} column '{key}': '{value}' is not one of {options}.")

        # ---- ADD SCIENTIFIC GUIDANCE RULES HERE (TBD with SANS scientist) ----

        return {"errors": errors, "warnings": warnings}

    def run_guidance(self) -> bool:
        """Run :meth:`guidance_check`, store the messages for display, return ok.

        ``True`` means no blocking errors (submission may proceed); warnings may
        still be present. The messages are stored on
        :attr:`guidance_errors` / :attr:`guidance_warnings` so the view can show
        them.
        """
        result = self.guidance_check()
        self.guidance_errors = result["errors"]
        self.guidance_warnings = result["warnings"]
        return not result["errors"]
