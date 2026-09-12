import json
from pathlib import Path

import pytest

from slean_experiment.registry import Registry, RawRegistryEntry, export_mathlib_registry, select_declaration_names


CURATED = Path("experiment/registry/curated.json")
ALIASES = Path("experiment/registry/aliases.json")


COMMITTED_INDEX = Path("experiment/registry/mathlib.jsonl")


def _rows(path: Path) -> list[dict[str, str]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_index_contains_large_pinned_declaration_set() -> None:
    rows = _rows(COMMITTED_INDEX)
    assert len(rows) >= 1000
    assert {row["lean_name"] for row in rows} >= {"Nat.Prime", "Ideal.IsPrime"}


def test_raw_rows_are_complete_and_deterministic() -> None:
    rows = _rows(COMMITTED_INDEX)
    names = [row["lean_name"] for row in rows]
    assert names == sorted(names)
    assert len(names) == len(set(names))
    assert all(row["id"] == f"mathlib.{row['lean_name']}" for row in rows)
    assert all(row["lean_name"].strip() and row["lean_type"].strip() for row in rows)
    assert all(row["source"] == {"kind": "environment", "revision": "leanprover/lean4:v4.34.0-rc2", "mathlib_revision": "70f3f13433ba3d82a15a7cae679abac9128f102b"} for row in rows)


def test_committed_sample_is_broadly_distributed() -> None:
    names = [row["lean_name"] for row in _rows(COMMITTED_INDEX)]
    namespaces = {name.split(".", 1)[0] for name in names}
    assert len(namespaces) >= 20
    complete = [f"{namespace}.declaration" for namespace in ("Aardvark", "Beta", "Gamma", "Omega", "Zygote")]
    selected = select_declaration_names(complete, 3)
    assert any(name.startswith("Beta.") or name.startswith("Gamma.") for name in selected)
    assert any(name.startswith("Omega.") or name.startswith("Zygote.") for name in selected)


@pytest.mark.slow
def test_running_export_twice_is_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    export_mathlib_registry(Path("lean"), first)
    export_mathlib_registry(Path("lean"), second)
    assert first.read_bytes() == second.read_bytes()


def test_curated_entries_override_raw_ids() -> None:
    registry = Registry.from_files(CURATED, ALIASES, COMMITTED_INDEX)
    assert registry.get("mathlib.Nat.Prime").id == "number_theory.nat_prime"
    assert registry.get("mathlib.Nat.Prime").target.lean_name == "Nat.Prime"
    assert registry.get_raw("mathlib.Nat.Prime").id == "mathlib.Nat.Prime"
    assert registry.get("mathlib.AbsoluteValue.listSum_le").id == "mathlib.AbsoluteValue.listSum_le"


def test_prime_alias_has_no_raw_duplicate() -> None:
    registry = Registry.from_files(CURATED, ALIASES, COMMITTED_INDEX)
    assert [entry.id for entry in registry.lookup_alias("prime")] == [
        "number_theory.nat_prime", "algebra.prime_element", "ring_theory.prime_ideal",
    ]


def test_core_forms_remain_independent_of_raw_declarations() -> None:
    registry = Registry.from_files(CURATED, ALIASES, COMMITTED_INDEX)
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


def test_selection_is_stable_and_order_independent() -> None:
    names = [f"Namespace{i}.declaration" for i in range(100)]
    assert select_declaration_names(names, 20) == select_declaration_names(list(reversed(names)), 20)
    assert select_declaration_names(names, 20) != sorted(names)[:20]


def test_raw_lean_revision_is_pinned() -> None:
    row = {
        "id": "mathlib.Test.one", "lean_name": "Test.one", "lean_type": "Nat",
        "source": {"kind": "environment", "revision": "wrong", "mathlib_revision": "70f3f13433ba3d82a15a7cae679abac9128f102b"},
    }
    with pytest.raises(ValueError):
        RawRegistryEntry.model_validate(row)
