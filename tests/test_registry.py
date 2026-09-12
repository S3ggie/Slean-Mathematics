import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from slean_experiment.registry import Registry


CURATED = Path("experiment/registry/curated.json")
ALIASES = Path("experiment/registry/aliases.json")


@pytest.fixture
def registry() -> Registry:
    return Registry.from_files(CURATED, ALIASES)


def test_prime_alias_keeps_distinct_meanings(registry: Registry) -> None:
    ids = {e.id for e in registry.lookup_alias("prime")}
    assert "number_theory.nat_prime" in ids
    assert "algebra.prime_element" in ids
    assert "ring_theory.prime_ideal" in ids


def test_get_exact_entry(registry: Registry) -> None:
    entry = registry.get("number_theory.nat_prime")
    assert entry.lean_name == "Nat.Prime"
    assert entry.lean_type


def test_alias_lookup_normalizes_case_and_whitespace(registry: Registry) -> None:
    assert [e.id for e in registry.lookup_alias("  PrImE  ")] == [
        "number_theory.nat_prime", "algebra.prime_element", "ring_theory.prime_ideal",
    ]


def test_unknown_alias_is_empty_and_unknown_id_is_explicit(registry: Registry) -> None:
    assert registry.lookup_alias("not-a-concept") == []
    with pytest.raises(KeyError):
        registry.get("missing.id")


def test_prime_concepts_retain_distinct_types_and_constraints(registry: Registry) -> None:
    entries = {e.id: e for e in registry.lookup_alias("prime")}
    assert len({e.lean_type for e in entries.values()}) == 3
    assert len({json.dumps(e.constraints, sort_keys=True) for e in entries.values()}) == 3


def _write_overlay(tmp_path: Path, entries: list[dict[str, object]], aliases: dict[str, list[str]] | None = None) -> tuple[Path, Path]:
    curated = tmp_path / "curated.json"
    alias_file = tmp_path / "aliases.json"
    curated.write_text(json.dumps(entries))
    alias_file.write_text(json.dumps(aliases if aliases is not None else {}))
    return curated, alias_file


def _valid_entry(**overrides: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "id": "test.one",
        "lean_name": "Test.one",
        "lean_type": "Nat",
        "constraints": [],
        "description": "A test entry.",
        "aliases": ["test"],
        "source": {"kind": "mathlib", "revision": "70f3f13433ba3d82a15a7cae679abac9128f102b"},
    }
    entry.update(overrides)
    return entry


@pytest.mark.parametrize("entries", [
    [_valid_entry(), _valid_entry()],
    [_valid_entry(), _valid_entry(id="test.two", lean_name="Test.one")],
])
def test_duplicate_ids_or_lean_targets_are_rejected(tmp_path: Path, entries: list[dict[str, object]]) -> None:
    curated, aliases = _write_overlay(tmp_path, entries)
    with pytest.raises((ValueError, ValidationError)):
        Registry.from_files(curated, aliases)


def test_missing_alias_target_is_rejected(tmp_path: Path) -> None:
    curated, aliases = _write_overlay(tmp_path, [_valid_entry()], {"unknown": ["missing.id"]})
    with pytest.raises((ValueError, ValidationError)):
        Registry.from_files(curated, aliases)


def test_missing_source_revision_is_rejected(tmp_path: Path) -> None:
    curated, aliases = _write_overlay(tmp_path, [_valid_entry(source={"kind": "mathlib"})])
    with pytest.raises((ValueError, ValidationError)):
        Registry.from_files(curated, aliases)


@pytest.mark.parametrize("field, value", [
    ("id", ""), ("lean_name", ""), ("description", ""), ("source", {}),
])
def test_malformed_required_entry_fields_are_rejected(tmp_path: Path, field: str, value: object) -> None:
    curated, aliases = _write_overlay(tmp_path, [_valid_entry(**{field: value})])
    with pytest.raises((ValueError, ValidationError)):
        Registry.from_files(curated, aliases)


def test_registry_loading_is_deterministic(registry: Registry) -> None:
    assert [e.id for e in registry.entries] == sorted(e.id for e in registry.entries)
