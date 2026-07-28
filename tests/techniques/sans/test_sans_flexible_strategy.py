"""SANS flexible-column strategy model tests.

Pins the column-flexible behaviour: an uploaded CSV may carry arbitrary columns;
the only guaranteed one is ``BL1A:sampleholder``, whose value groups rows into
Samples. Covers load / grouping / inference / export round-trip / row editing /
pre-submission guidance.
"""

from __future__ import annotations

from pathlib import Path

from exphub.techniques.sans.models.strategy import (
    GROUP_KEY,
    SansStrategyModel,
    build_column_specs,
    infer_column_spec,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "strategy.csv"


def _loaded() -> SansStrategyModel:
    m = SansStrategyModel()
    m.load_strategy(str(_FIXTURE))
    return m


def test_load_preserves_columns_and_skips_blank_rows() -> None:
    m = _loaded()
    assert m.columns == ["Notes", "BL1A:sampleholder", "BL1A:anlge", "Wait For", "Value"]
    # 7 data rows; the trailing blank line in the fixture is skipped.
    assert len(m.strategy_list) == 7
    # Every row got a stable id and keeps the raw (string) cell values.
    assert m.strategy_list[0]["id"] == 1
    assert m.strategy_list[5]["Value"] == "1e4"  # scientific notation preserved verbatim


def test_rows_group_by_sample_holder() -> None:
    m = _loaded()
    assert [(g["holder"], g["count"]) for g in m.groups] == [("1", 1), ("2", 5), ("3", 1)]
    assert m.groups[1]["label"] == "Sample 2"


def test_group_key_is_locked_and_typed_int() -> None:
    m = _loaded()
    spec = next(s for s in m.column_specs if s["key"] == GROUP_KEY)
    assert spec["type"] == "int"
    assert spec["editable"] is False
    assert spec["required"] is True


def test_column_type_inference() -> None:
    m = _loaded()
    by_key = {s["key"]: s for s in m.column_specs}
    assert by_key["Notes"]["type"] == "str"
    assert by_key["BL1A:anlge"]["type"] == "float"  # 0.0/5.0/.../73.9 -> float
    # "Wait For" is a known enum column; options include the observed control words.
    assert by_key["Wait For"]["type"] == "enum"
    assert "seconds" in by_key["Wait For"]["options"]
    assert "Counts" in by_key["Wait For"]["options"]


def test_infer_forces_group_key_int_regardless_of_name_position() -> None:
    spec = infer_column_spec(GROUP_KEY, ["1", "2", "3"])
    assert spec == {
        "key": GROUP_KEY,
        "label": "Sample Holder",
        "type": "int",
        "options": [],
        "editable": False,
        "required": True,
    }


def test_catalog_override_wins_over_inference() -> None:
    import exphub.techniques.sans.models.strategy as strat

    original = dict(strat.COLUMN_CATALOG)
    try:
        strat.COLUMN_CATALOG["BL1A:anlge"] = {"type": "enum", "options": ["a", "b"], "label": "Angle"}
        specs = build_column_specs(["BL1A:anlge"], [{"BL1A:anlge": "0.0"}])
        assert specs[0]["type"] == "enum"
        assert specs[0]["label"] == "Angle"
        assert specs[0]["options"] == ["a", "b"]
    finally:
        strat.COLUMN_CATALOG.clear()
        strat.COLUMN_CATALOG.update(original)


def test_export_roundtrip_is_lossless(tmp_path: Path) -> None:
    m = _loaded()
    out = tmp_path / "exported.csv"
    m.export_to_csv(str(out))

    m2 = SansStrategyModel()
    m2.load_strategy(str(out))

    def _strip(rows: list[dict]) -> list[dict]:
        return [{k: v for k, v in r.items() if k != "id"} for r in rows]

    assert m2.columns == m.columns
    assert _strip(m2.strategy_list) == _strip(m.strategy_list)


def test_add_sample_add_step_remove_step() -> None:
    m = _loaded()
    m.add_sample()  # next holder = 4
    assert [g["holder"] for g in m.groups] == ["1", "2", "3", "4"]
    m.add_step("2")  # holder 2 grows to 6 steps
    assert next(g for g in m.groups if g["holder"] == "2")["count"] == 6
    first_id = m.strategy_list[0]["id"]
    m.remove_step(first_id)
    assert all(r["id"] != first_id for r in m.strategy_list)


def test_add_sample_on_empty_model_seeds_group_key() -> None:
    m = SansStrategyModel()
    m.add_sample()
    assert GROUP_KEY in m.columns
    assert [g["holder"] for g in m.groups] == ["1"]


def test_guidance_ok_for_valid_fixture() -> None:
    m = _loaded()
    result = m.guidance_check()
    assert result["errors"] == []


def test_guidance_blocks_empty_table() -> None:
    m = SansStrategyModel()
    result = m.guidance_check()
    assert any("empty" in e.lower() for e in result["errors"])
    assert m.run_guidance() is False


def test_guidance_flags_blank_and_non_integer_holder() -> None:
    m = _loaded()
    m.strategy_list[0][GROUP_KEY] = ""  # blank holder
    m.strategy_list[1][GROUP_KEY] = "abc"  # non-integer holder
    result = m.guidance_check()
    assert any("blank" in e.lower() for e in result["errors"])
    assert any("not an integer" in e.lower() for e in result["errors"])


def test_guidance_warns_on_bad_enum_value() -> None:
    m = _loaded()
    m.strategy_list[0]["Wait For"] = "not-a-real-mode"
    result = m.guidance_check()
    assert result["errors"] == []  # still submittable
    assert any("Wait For" in w for w in result["warnings"])


def test_guidance_flags_non_integer_holder_on_load_path(tmp_path: Path) -> None:
    """A legacy CSV with a bad holder must block at load, not only after edits.

    Regression guard: the holder column's int type is contractual (the module
    documents it as an integer index), so data-driven inference must not relax
    it and silently skip the integer check for the whole table.
    """
    bad = tmp_path / "bad_holder.csv"
    bad.write_text("Notes,BL1A:sampleholder\none,abc\ntwo,2\n")
    m = SansStrategyModel()
    m.load_strategy(str(bad))
    spec = next(s for s in m.column_specs if s["key"] == GROUP_KEY)
    assert spec["type"] == "int"  # contract wins over the bad data
    result = m.guidance_check()
    assert any("'abc' is not an integer" in e for e in result["errors"])


def test_catalog_required_columns_do_not_block_legacy_tables(tmp_path: Path) -> None:
    """A legacy table reusing a catalogued column name (e.g. Title) stays valid.

    The blank-cell blocking rule is scoped to the beamline's required_columns;
    the global COLUMN_CATALOG alone must not impose USANS rules elsewhere.
    """
    legacy = tmp_path / "legacy_with_title.csv"
    legacy.write_text("BL1A:sampleholder,Title,Notes\n1,,free-form\n")
    m = SansStrategyModel()  # legacy defaults: holder grouping, no required set
    m.load_strategy(str(legacy))
    result = m.guidance_check()
    assert result["errors"] == []


def test_whitespace_holder_is_normalised_on_load(tmp_path: Path) -> None:
    """' 2' and '2' are one Sample everywhere (view filter, guidance, submit)."""
    padded = tmp_path / "padded_holder.csv"
    padded.write_text("Notes,BL1A:sampleholder\na, 2\nb,2\n")
    m = SansStrategyModel()
    m.load_strategy(str(padded))
    assert [(g["holder"], g["count"]) for g in m.groups] == [("2", 2)]
    assert all(r[GROUP_KEY] == "2" for r in m.strategy_list)
