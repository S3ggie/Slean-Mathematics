from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


MATHLIB_REVISION = "70f3f13433ba3d82a15a7cae679abac9128f102b"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceProvenance(StrictModel):
    kind: Literal["mathlib"]
    revision: StrictStr

    @field_validator("revision")
    @classmethod
    def nonempty_revision(cls, value: str) -> str:
        if not value:
            raise ValueError("source revision must not be empty")
        return value


class RegistryEntry(StrictModel):
    id: StrictStr
    lean_name: StrictStr
    lean_type: StrictStr
    constraints: list[StrictStr]
    description: StrictStr
    aliases: list[StrictStr]
    source: SourceProvenance

    @field_validator("id", "lean_name", "description")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("registry text fields must not be empty")
        return value


class Registry:
    def __init__(self, entries: list[RegistryEntry], aliases: dict[str, list[str]]) -> None:
        by_id: dict[str, RegistryEntry] = {}
        by_lean_name: dict[str, RegistryEntry] = {}
        for entry in entries:
            if entry.id in by_id:
                raise ValueError(f"duplicate registry ID: {entry.id}")
            if entry.lean_name in by_lean_name:
                raise ValueError(f"duplicate Lean target: {entry.lean_name}")
            if entry.source.revision != MATHLIB_REVISION:
                raise ValueError(f"entry {entry.id} is not from the pinned Mathlib revision")
            by_id[entry.id] = entry
            by_lean_name[entry.lean_name] = entry

        normalized_aliases: dict[str, list[str]] = {}
        for alias, ids in aliases.items():
            key = self._normalize(alias)
            if not key:
                raise ValueError("aliases must not be empty")
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

    @classmethod
    def from_files(cls, curated_path: Path, aliases_path: Path) -> Registry:
        entries = [RegistryEntry.model_validate(row) for row in json.loads(curated_path.read_text())]
        aliases = json.loads(aliases_path.read_text())
        if not isinstance(aliases, dict) or any(not isinstance(ids, list) for ids in aliases.values()):
            raise ValueError("aliases file must map strings to ID lists")
        return cls(entries, aliases)

    def get(self, id: str) -> RegistryEntry:
        try:
            return self._by_id[id]
        except KeyError:
            raise KeyError(f"unknown registry ID: {id}") from None

    def lookup_alias(self, text: str) -> list[RegistryEntry]:
        return [self._by_id[entry_id] for entry_id in self._aliases.get(self._normalize(text), [])]

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.casefold().split())
