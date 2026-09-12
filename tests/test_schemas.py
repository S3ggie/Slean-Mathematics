import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from slean_experiment.schemas import validate_result, write_json_schemas


def _advertised_node_kinds(schema_path: Path) -> set[str]:
    schema = json.loads(schema_path.read_text())
    kinds: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if "kind" in value and isinstance(value["kind"], dict):
                kind_schema = value["kind"]
                if isinstance(kind_schema.get("const"), str):
                    kinds.add(kind_schema["const"])
                if isinstance(kind_schema.get("enum"), list):
                    kinds.update(item for item in kind_schema["enum"] if isinstance(item, str))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return kinds


def test_direct_accepts_formalization() -> None:
    result = validate_result("direct", {
        "outcome": "formalization",
        "lean_statement": "∀ n : ℕ, n = n",
    })
    assert result.outcome == "formalization"


def test_all_candidates_accept_clarification() -> None:
    for candidate in ("a", "b", "c", "direct"):
        result = validate_result(candidate, {
            "outcome": "clarification_required",
            "issue": "The ambient ring is unspecified.",
        })
        assert result.outcome == "clarification_required"


def test_candidate_a_rejects_candidate_c_logic_node() -> None:
    with pytest.raises(ValidationError):
        validate_result("a", {
            "outcome": "formalization",
            "ir": {"kind": "implies", "left": {}, "right": {}},
        })


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_result("direct", {
            "outcome": "formalization",
            "lean_statement": "True",
            "metadata": {},
        })


def test_outcome_payloads_are_exclusive() -> None:
    with pytest.raises(ValidationError):
        validate_result("direct", {
            "outcome": "formalization",
            "lean_statement": "True",
            "issue": "ambiguous",
        })
    with pytest.raises(ValidationError):
        validate_result("direct", {"outcome": "formalization"})


def test_candidate_b_accepts_forall_and_exists() -> None:
    for kind in ("forall", "exists"):
        result = validate_result("b", {
            "outcome": "formalization",
            "ir": {
                "kind": kind,
                "variables": [{"name": "n", "type": {"kind": "symbol", "id": "Nat"}}],
                "body": {"kind": "symbol", "id": "True"},
            },
        })
        assert result.ir.kind == kind


@pytest.mark.parametrize("kind", ["implies", "and", "or", "not", "equals"])
def test_candidate_c_accepts_explicit_logic(kind: str) -> None:
    atom = {"kind": "symbol", "id": "P"}
    payload = {"kind": kind}
    if kind == "not":
        payload["value"] = atom
    elif kind == "equals":
        payload.update(left=atom, right=atom)
    else:
        payload.update(left=atom, right=atom)
    result = validate_result("c", {"outcome": "formalization", "ir": payload})
    assert result.ir.kind == kind


def test_candidate_a_cannot_accept_scope_explicit_nodes() -> None:
    for kind in ("forall", "exists", "implies", "equals"):
        with pytest.raises(ValidationError):
            validate_result("a", {
                "outcome": "formalization",
                "ir": {"kind": kind, "body": {}, "variables": []},
            })

    with pytest.raises(ValidationError):
        validate_result("a", {
            "outcome": "formalization",
            "ir": {
                "kind": "apply",
                "head": {"kind": "symbol", "id": "f"},
                "args": [{"kind": "implies", "left": {"kind": "symbol", "id": "P"}, "right": {"kind": "symbol", "id": "Q"}}],
            },
        })

    with pytest.raises(ValidationError):
        validate_result("b", {
            "outcome": "formalization",
            "ir": {
                "kind": "apply",
                "head": {"kind": "symbol", "id": "f"},
                "args": [{"kind": "equals", "left": {"kind": "symbol", "id": "P"}, "right": {"kind": "symbol", "id": "Q"}}],
            },
        })


def test_source_span_validates_and_recursive_nodes_validate() -> None:
    result = validate_result("a", {
        "outcome": "formalization",
        "ir": {
            "kind": "apply",
            "head": {"kind": "symbol", "id": "eq", "source_span": {"start": 0, "end": 2}},
            "args": [{"kind": "literal", "value": 2}],
        },
    })
    assert result.ir.head.source_span.end == 2

    with pytest.raises(ValidationError):
        validate_result("a", {
            "outcome": "formalization",
            "ir": {"kind": "apply", "head": {"kind": "symbol", "id": "eq"}, "args": [{}]},
        })
    with pytest.raises(ValidationError):
        validate_result("a", {
            "outcome": "formalization",
            "ir": {"kind": "symbol", "id": "eq", "source_span": {"start": 3, "end": 2}},
        })


def test_schema_export_has_exact_filenames_and_is_repeatable(tmp_path: Path) -> None:
    write_json_schemas(tmp_path)
    first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    write_json_schemas(tmp_path)
    second = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert set(first) == {
        "candidate_a.schema.json", "candidate_b.schema.json",
        "candidate_c.schema.json", "direct.schema.json",
    }
    assert first == second


def test_exported_candidate_a_schema_has_only_a_node_kinds(tmp_path: Path) -> None:
    write_json_schemas(tmp_path)
    assert _advertised_node_kinds(tmp_path / "candidate_a.schema.json") <= {
        "var", "literal", "symbol", "apply", "bind",
    }


def test_exported_candidate_b_schema_has_only_b_node_kinds(tmp_path: Path) -> None:
    write_json_schemas(tmp_path)
    assert _advertised_node_kinds(tmp_path / "candidate_b.schema.json") <= {
        "var", "literal", "symbol", "apply", "bind", "forall", "exists",
    }


def test_exported_candidate_c_schema_has_all_c_node_kinds(tmp_path: Path) -> None:
    write_json_schemas(tmp_path)
    assert _advertised_node_kinds(tmp_path / "candidate_c.schema.json") == {
        "var", "literal", "symbol", "apply", "bind", "forall", "exists",
        "implies", "and", "or", "not", "equals",
    }


def test_deeply_nested_candidate_a_and_b_structures_validate() -> None:
    nested_a = {"kind": "symbol", "id": "leaf"}
    for _ in range(4):
        nested_a = {"kind": "apply", "head": {"kind": "symbol", "id": "f"}, "args": [nested_a]}
    assert validate_result("a", {"outcome": "formalization", "ir": nested_a}).outcome == "formalization"

    nested_b = {"kind": "symbol", "id": "True"}
    for _ in range(3):
        nested_b = {
            "kind": "forall",
            "variables": [{"name": "n", "type": {"kind": "symbol", "id": "Nat"}}],
            "body": nested_b,
        }
    assert validate_result("b", {"outcome": "formalization", "ir": nested_b}).outcome == "formalization"
