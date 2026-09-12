from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Literal, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator, model_validator


MATHLIB_REVISION = "70f3f13433ba3d82a15a7cae679abac9128f102b"
LEAN_REVISION = "v4.34.0-rc2"
LEAN_ENVIRONMENT_REVISION = "leanprover/lean4:v4.34.0-rc2"
SAMPLE_SIZE = 5000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceProvenance(StrictModel):
    kind: Literal["mathlib", "lean"]
    revision: StrictStr

    @field_validator("revision")
    @classmethod
    def nonempty_revision(cls, value: str) -> str:
        if not value:
            raise ValueError("source revision must not be empty")
        return value


class DeclarationTarget(StrictModel):
    target_kind: Literal["declaration"]
    lean_name: StrictStr

    @field_validator("lean_name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("declaration target name must not be empty")
        return value


class CoreFormTarget(StrictModel):
    target_kind: Literal["core_form"]
    core_form: Literal["forall", "exists", "implies"]


Target: TypeAlias = Annotated[Union[DeclarationTarget, CoreFormTarget], Field(discriminator="target_kind")]


class RegistryEntry(StrictModel):
    id: StrictStr
    lean_type: StrictStr
    target: Target
    constraints: list[StrictStr]
    description: StrictStr
    aliases: list[StrictStr]
    source: SourceProvenance

    @field_validator("id", "lean_type", "description")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("registry text fields must not be empty")
        return value

    @model_validator(mode="after")
    def validate_target_and_source(self) -> RegistryEntry:
        if self.target.target_kind == "core_form" and self.source.kind != "lean":
            raise ValueError("core-form targets must use Lean provenance")
        expected = LEAN_REVISION if self.source.kind == "lean" else MATHLIB_REVISION
        if self.source.revision != expected:
            raise ValueError(f"entry {self.id} does not use the pinned {self.source.kind} revision")
        return self


class RawEnvironmentSource(StrictModel):
    kind: Literal["environment"]
    revision: StrictStr
    mathlib_revision: StrictStr


class RawRegistryEntry(StrictModel):
    id: StrictStr
    lean_name: StrictStr
    lean_type: StrictStr
    source: RawEnvironmentSource

    @field_validator("id", "lean_name", "lean_type")
    @classmethod
    def nonempty_raw_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("raw registry fields must not be empty")
        return value

    @model_validator(mode="after")
    def validate_raw_id(self) -> RawRegistryEntry:
        if self.id != f"mathlib.{self.lean_name}":
            raise ValueError("raw registry ID must be mathlib.<Lean.Name>")
        if self.source.mathlib_revision != MATHLIB_REVISION:
            raise ValueError("raw registry row does not use the pinned Mathlib revision")
        if self.source.revision != LEAN_ENVIRONMENT_REVISION:
            raise ValueError("raw registry row does not use the pinned Lean environment")
        return self


class RegistryExportReport(StrictModel):
    success: bool
    declaration_count: int
    output: Path
    mathlib_revision: StrictStr
    error: StrictStr | None = None


class Registry:
    def __init__(self, entries: list[RegistryEntry], aliases: dict[str, list[str]], raw_entries: list[RawRegistryEntry] | None = None) -> None:
        by_id: dict[str, RegistryEntry] = {}
        by_lean_name: dict[str, RegistryEntry] = {}
        for entry in entries:
            if entry.id in by_id:
                raise ValueError(f"duplicate registry ID: {entry.id}")
            by_id[entry.id] = entry
            if entry.target.target_kind == "declaration":
                if entry.target.lean_name in by_lean_name:
                    raise ValueError(f"duplicate Lean target: {entry.target.lean_name}")
                by_lean_name[entry.target.lean_name] = entry

        normalized_aliases: dict[str, list[str]] = {}
        for alias, ids in aliases.items():
            key = self._normalize(alias)
            if not key:
                raise ValueError("aliases must not be empty")
            if key in normalized_aliases:
                raise ValueError(f"duplicate normalized alias: {alias}")
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate IDs for alias: {alias}")
            for entry_id in ids:
                if entry_id not in by_id:
                    raise ValueError(f"alias {alias!r} references unknown ID: {entry_id}")
            normalized_aliases[key] = list(ids)

        entry_aliases = {entry.id: {self._normalize(alias) for alias in entry.aliases} for entry in entries}
        for alias, ids in normalized_aliases.items():
            for entry_id in ids:
                if alias not in entry_aliases[entry_id]:
                    raise ValueError(f"alias {alias!r} is missing from entry {entry_id}")
        for entry_id, aliases_for_entry in entry_aliases.items():
            for alias in aliases_for_entry:
                if entry_id not in normalized_aliases.get(alias, []):
                    raise ValueError(f"entry {entry_id} alias {alias!r} is missing from aliases file")

        self.entries = tuple(sorted(entries, key=lambda entry: entry.id))
        self._by_id = by_id
        self._aliases = normalized_aliases
        self.raw_entries = tuple(sorted(raw_entries or [], key=lambda entry: entry.lean_name))
        self._raw_by_id = {entry.id: entry for entry in self.raw_entries}
        self._raw_by_name = {entry.lean_name: entry for entry in self.raw_entries}
        self._curated_by_name = {
            entry.target.lean_name: entry
            for entry in entries
            if entry.target.target_kind == "declaration"
        }

    @classmethod
    def from_files(cls, curated_path: Path, aliases_path: Path, raw_path: Path | None = None) -> Registry:
        entries = [RegistryEntry.model_validate(row) for row in json.loads(curated_path.read_text())]
        aliases = json.loads(aliases_path.read_text())
        if not isinstance(aliases, dict) or any(not isinstance(ids, list) for ids in aliases.values()):
            raise ValueError("aliases file must map strings to ID lists")
        raw_entries: list[RawRegistryEntry] = []
        if raw_path is not None:
            try:
                raw_entries = [RawRegistryEntry.model_validate(json.loads(line)) for line in raw_path.read_text().splitlines() if line.strip()]
            except (json.JSONDecodeError, ValidationError) as exc:
                raise ValueError(f"invalid raw registry index: {exc}") from exc
            if len({entry.lean_name for entry in raw_entries}) != len(raw_entries):
                raise ValueError("duplicate raw declaration name")
        return cls(entries, aliases, raw_entries)

    def get(self, id: str) -> RegistryEntry | RawRegistryEntry:
        if id in self._by_id:
            return self._by_id[id]
        if id in self._raw_by_id:
            raw = self._raw_by_id[id]
            return self._curated_by_name.get(raw.lean_name, raw)
        raise KeyError(f"unknown registry ID: {id}")

    def get_raw(self, id: str) -> RawRegistryEntry:
        try:
            return self._raw_by_id[id]
        except KeyError:
            raise KeyError(f"unknown raw registry ID: {id}") from None

    def lookup_alias(self, text: str) -> list[RegistryEntry]:
        return [self._by_id[entry_id] for entry_id in self._aliases.get(self._normalize(text), [])]

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.casefold().split())


def export_mathlib_registry(lean_root: Path, output: Path) -> RegistryExportReport:
    if not lean_root.is_dir():
        raise RuntimeError(f"Lean registry export failed: missing Lean root {lean_root}")
    lake = shutil.which("lake") or "/home/seggie/.elan/bin/lake"
    curated_path = lean_root.parent / "experiment" / "registry" / "curated.json"
    curated_rows = json.loads(curated_path.read_text())
    mandatory_names = [
        row["target"]["lean_name"]
        for row in curated_rows
        if row["target"]["target_kind"] == "declaration"
    ]
    command = [lake, "env", "lean", "SleanExperiment/ExportRegistry.lean"]
    try:
        completed = subprocess.run(
            command, cwd=lean_root, text=True, capture_output=True, check=False, timeout=1800,
            env={**os.environ, "SLEAN_MANDATORY_NAMES": ",".join(mandatory_names)},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Lean registry export failed: {exc}") from exc
    if completed.returncode != 0:
        raise RuntimeError(f"Lean registry export failed ({completed.returncode}): {completed.stderr.strip()}")

    try:
        rows = [RawRegistryEntry.model_validate(json.loads(line)) for line in completed.stdout.splitlines() if line.strip()]
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(f"Lean registry export produced invalid rows: {exc}") from exc
    if not rows:
        raise RuntimeError("Lean registry export produced no declarations")
    rows.sort(key=lambda row: row.lean_name)
    names = [row.lean_name for row in rows]
    if names != sorted(names) or len(names) != len(set(names)):
        raise RuntimeError("Lean registry export is not uniquely sorted")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=output.parent, prefix=f".{output.name}.", delete=False) as temporary:
        temporary_path = Path(temporary.name)
        for row in rows:
            temporary.write(json.dumps(row.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n")
    temporary_path.replace(output)
    return RegistryExportReport(success=True, declaration_count=len(rows), output=output, mathlib_revision=MATHLIB_REVISION)


def select_declaration_names(names: list[str], count: int = SAMPLE_SIZE) -> list[str]:
    """Select lowest stable FNV-1a-ranked names, independent of input iteration order."""
    def rank(name: str) -> int:
        value = 2166136261
        for character in name:
            value = (value * 16777619 + ord(character)) % (1 << 64)
        return value
    return sorted(set(names), key=lambda name: (rank(name), name))[:count]
