import json
from pathlib import Path

import pytest

from slean_experiment.registry import Registry, export_mathlib_registry


CURATED = Path("experiment/registry/curated.json")
ALIASES = Path("experiment/registry/aliases.json")


@pytest.fixture(scope="module")
def exported_index(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("registry") / "mathlib.jsonl"
    report = export_mathlib_registry(Path("lean"), output)
    assert report.success
    return output


def _rows(path: Path) -> list[dict[str, str]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_index_contains_large_pinned_declaration_set(exported_index: Path) -> None:
    rows = _rows(exported_index)
    assert len(rows) >= 1000
    assert {row["lean_name"] for row in rows} >= {"Nat.Prime", "Ideal.IsPrime"}


def test_raw_rows_are_complete_and_deterministic(exported_index: Path) -> None:
    rows = _rows(exported_index)
    names = [row["lean_name"] for row in rows]
    assert names == sorted(names)
    assert len(names) == len(set(names))
    assert all(row["id"] == f"mathlib.{row['lean_name']}" for row in rows)
    assert all(row["lean_name"].strip() and row["lean_type"].strip() for row in rows)
    assert all(row["source"] == {"kind": "environment", "revision": "leanprover/lean4:v4.34.0-rc2", "mathlib_revision": "70f3f13433ba3d82a15a7cae679abac9128f102b"} for row in rows)


def test_running_export_twice_is_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    export_mathlib_registry(Path("lean"), first)
    export_mathlib_registry(Path("lean"), second)
    assert first.read_bytes() == second.read_bytes()


def test_curated_entries_override_raw_ids(exported_index: Path) -> None:
    registry = Registry.from_files(CURATED, ALIASES, exported_index)
    assert registry.get("mathlib.Nat.Prime").id == "number_theory.nat_prime"
    assert registry.get("mathlib.Nat.Prime").target.lean_name == "Nat.Prime"
    assert registry.get_raw("mathlib.Nat.Prime").id == "mathlib.Nat.Prime"
    assert registry.get("mathlib.AbsoluteValue.listSum_le").id == "mathlib.AbsoluteValue.listSum_le"


def test_prime_alias_has_no_raw_duplicate(exported_index: Path) -> None:
    registry = Registry.from_files(CURATED, ALIASES, exported_index)
    assert [entry.id for entry in registry.lookup_alias("prime")] == [
        "number_theory.nat_prime", "algebra.prime_element", "ring_theory.prime_ideal",
    ]


def test_core_forms_remain_independent_of_raw_declarations(exported_index: Path) -> None:
    registry = Registry.from_files(CURATED, ALIASES, exported_index)
    assert registry.get("logic.forall").target.target_kind == "core_form"


def test_malformed_raw_rows_are_rejected(tmp_path: Path) -> None:
    raw = tmp_path / "raw.jsonl"
    raw.write_text(json.dumps({"id": "mathlib.Bad", "lean_name": "", "lean_type": "", "source": {}}) + "\n")
    with pytest.raises(ValueError):
        Registry.from_files(CURATED, ALIASES, raw)


def test_export_failure_preserves_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "mathlib.jsonl"
    output.write_text("sentinel\n")
    with pytest.raises(RuntimeError):
        export_mathlib_registry(tmp_path / "missing-lean", output)
    assert output.read_text() == "sentinel\n"
