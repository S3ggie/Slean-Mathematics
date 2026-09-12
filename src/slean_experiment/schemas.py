from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter

from .models import (
    CandidateAFormalization,
    CandidateBFormalization,
    CandidateCFormalization,
    ClarificationRequired,
    DirectFormalization,
    Result,
)

Candidate = Literal["a", "b", "c", "direct"]

RESULT_MODELS = {
    "a": TypeAdapter(CandidateAFormalization | ClarificationRequired),
    "b": TypeAdapter(CandidateBFormalization | ClarificationRequired),
    "c": TypeAdapter(CandidateCFormalization | ClarificationRequired),
    "direct": TypeAdapter(DirectFormalization | ClarificationRequired),
}

SCHEMA_FILENAMES = {
    "a": "candidate_a.schema.json",
    "b": "candidate_b.schema.json",
    "c": "candidate_c.schema.json",
    "direct": "direct.schema.json",
}


def validate_result(candidate: Candidate, data: dict[str, object]) -> Result:
    return RESULT_MODELS[candidate].validate_python(data)


def write_json_schemas(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for candidate, adapter in RESULT_MODELS.items():
        path = output_dir / SCHEMA_FILENAMES[candidate]
        path.write_text(json.dumps(adapter.json_schema(), indent=2, sort_keys=True) + "\n")
