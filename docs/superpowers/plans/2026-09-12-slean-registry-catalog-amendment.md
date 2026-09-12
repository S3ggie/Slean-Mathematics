# Slean Registry Catalog Amendment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the failed sampled bulk-typed Mathlib index with a complete lightweight declaration catalog plus deterministic lazy type resolution and a version-pinned persistent type cache.

**Architecture:** Lean exports every declaration name from the pinned imported environment without pretty-printing types. Python loads that full catalog under the existing curated semantic overlay. Exact types are resolved only for requested declarations through a separate targeted Lean query and persisted in a deterministic cache. Registry search spans curated semantics plus the full raw catalog while keeping curated identities authoritative.

**Tech Stack:** Python 3.12, Pydantic 2, Lean 4.34.0-rc2, pinned Mathlib `70f3f13433ba3d82a15a7cae679abac9128f102b`, pytest, Lake.

**Spec:** `docs/superpowers/specs/2026-09-12-slean-registry-catalog-amendment.md`

## Global Constraints

- Lean remains pinned to `v4.34.0-rc2`.
- Mathlib remains pinned to `70f3f13433ba3d82a15a7cae679abac9128f102b`.
- No LLM participates in catalog generation, type resolution, cache maintenance, registry lookup, or compilation.
- Catalog generation enumerates the entire `env.constants` name set and does not call `ppExpr` per catalog row.
- Raw IDs remain `mathlib.<Lean.Name>`.
- Curated stable Slean IDs remain authoritative when a curated declaration target has the same exact Lean name as a raw catalog declaration.
- Curated core forms remain independent of declaration catalog rows.
- Catalog and cache writes use validation before atomic replacement so failure cannot corrupt a valid artifact.
- Default pytest remains fast and excludes tests marked `slow`.
- The legacy 5,000-row typed sample is temporary compatibility state only and is deleted in Task 4D.

---

### Task 4A: Export the Complete Lightweight Declaration Catalog

**Files:**
- Create: `lean/SleanExperiment/ExportCatalog.lean`
- Create: `src/slean_experiment/catalog.py`
- Create generated: `experiment/registry/catalog.jsonl`
- Create: `tests/test_catalog.py`
- Preserve temporarily: `experiment/registry/mathlib.jsonl`

**Interfaces:**
- `CatalogSource(kind: Literal["environment"], revision: str, mathlib_revision: str)`
- `CatalogEntry(id: str, lean_name: str, source: CatalogSource)`; there is no `lean_type` field.
- `CatalogExportReport(success: bool, declaration_count: int, output: Path, lean_revision: str, mathlib_revision: str)`
- `export_catalog(lean_root: Path, output: Path) -> CatalogExportReport`
- `load_catalog(path: Path) -> tuple[CatalogEntry, ...]`

- [ ] **Step 1: Write failing catalog contract tests**

Create `tests/test_catalog.py` with these concrete tests:

```python
from pathlib import Path
import json
import pytest
from pydantic import ValidationError

from slean_experiment.catalog import (
    CatalogEntry,
    CatalogSource,
    LEAN_ENVIRONMENT_REVISION,
    MATHLIB_REVISION,
    load_catalog,
)

CATALOG = Path("experiment/registry/catalog.jsonl")


def test_catalog_rows_have_no_precomputed_type() -> None:
    row = json.loads(CATALOG.read_text().splitlines()[0])
    assert set(row) == {"id", "lean_name", "source"}
    assert "lean_type" not in row


def test_catalog_is_full_scale_unique_and_sorted() -> None:
    entries = load_catalog(CATALOG)
    names = [entry.lean_name for entry in entries]
    assert len(entries) > 5002
    assert names == sorted(names)
    assert len(names) == len(set(names))
    assert "Nat.Prime" in names
    assert "Ideal.IsPrime" in names


def test_catalog_ids_and_pins_are_exact() -> None:
    for entry in load_catalog(CATALOG):
        assert entry.id == f"mathlib.{entry.lean_name}"
        assert entry.source.revision == LEAN_ENVIRONMENT_REVISION
        assert entry.source.mathlib_revision == MATHLIB_REVISION


def test_catalog_entry_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        CatalogEntry.model_validate({
            "id": "mathlib.",
            "lean_name": " ",
            "source": {
                "kind": "environment",
                "revision": LEAN_ENVIRONMENT_REVISION,
                "mathlib_revision": MATHLIB_REVISION,
            },
        })


def test_catalog_source_rejects_wrong_pin() -> None:
    with pytest.raises(ValidationError):
        CatalogSource.model_validate({
            "kind": "environment",
            "revision": "wrong",
            "mathlib_revision": MATHLIB_REVISION,
        })
```

Also add a fixture test that writes two identical names to a temporary JSONL file and asserts `load_catalog()` raises `ValueError` for duplicate declarations.

- [ ] **Step 2: Verify red state**

Run:

```bash
.venv/bin/python -m pytest tests/test_catalog.py -v
```

Expected: FAIL because the catalog module and artifact do not exist.

- [ ] **Step 3: Implement the names-only Lean exporter**

Create `lean/SleanExperiment/ExportCatalog.lean` with this behavior:

```lean
import Mathlib
import Lean

open Lean Elab Command

syntax "#slean_export_catalog" : command

elab_rules : command
  | `(#slean_export_catalog) => do
      let env ← getEnv
      let names := env.constants.toList.map (fun pair => pair.1.toString)
      let sorted := names.toArray.qsort (· < ·) |>.toList
      for name in sorted do
        let row := Json.mkObj [
          ("id", Json.str s!"mathlib.{name}"),
          ("lean_name", Json.str name),
          ("source", Json.mkObj [
            ("kind", Json.str "environment"),
            ("revision", Json.str "leanprover/lean4:v4.34.0-rc2"),
            ("mathlib_revision", Json.str "70f3f13433ba3d82a15a7cae679abac9128f102b")
          ])
        ]
        liftIO <| IO.println row.compress

#slean_export_catalog
```

Adjust only for pinned Lean API syntax if required. This exporter must not call `ppExpr`, must not sample, and must not consult curated registry data.

- [ ] **Step 4: Implement strict Python catalog models and export**

Create `src/slean_experiment/catalog.py`. Move the shared pin constants there and import them from `registry.py` so the repo has one authoritative copy.

`export_catalog()` performs exactly these checks before replacing the destination:

1. `lean_root` exists;
2. `lake env lean SleanExperiment/ExportCatalog.lean` exits 0;
3. every nonblank stdout line validates as `CatalogEntry`;
4. output is nonempty;
5. declaration IDs are unique;
6. Lean names are unique;
7. names are lexically sorted;
8. every row has exact pinned Lean/Mathlib provenance.

Write to a temporary file in the destination directory, then atomically replace the destination.

- [ ] **Step 5: Generate the real catalog once**

Run:

```bash
/usr/bin/time -f 'elapsed=%E cpu=%P maxrss=%MKB' \
.venv/bin/python - <<'PY'
from pathlib import Path
from slean_experiment.catalog import export_catalog
print(export_catalog(Path("lean"), Path("experiment/registry/catalog.jsonl")))
PY
```

Record declaration count and wall time. The catalog must contain more than 5,002 rows. If a names-only export is still unexpectedly CPU-bound for many minutes, stop and report the observed command/process rather than adding type work.

- [ ] **Step 6: Verify Task 4A**

Run:

```bash
.venv/bin/python -m pytest tests/test_catalog.py -v
.venv/bin/python -m pytest -v
git diff --check
```

Expected: all fast tests pass and no bulk type pretty-printing occurs.

- [ ] **Step 7: Commit**

```bash
git add lean/SleanExperiment/ExportCatalog.lean src/slean_experiment/catalog.py experiment/registry/catalog.jsonl tests/test_catalog.py src/slean_experiment/registry.py
git commit -m "feat: export full Lean declaration catalog"
```

Stop after Task 4A.

---

### Task 4B: Add Targeted Type Resolution and Version-Pinned Cache

**Files:**
- Create: `lean/SleanExperiment/ResolveDeclaration.lean`
- Modify: `src/slean_experiment/catalog.py`
- Create generated: `experiment/registry/type_cache.jsonl`
- Expand: `tests/test_catalog.py`

**Interfaces:**
- `ResolvedTypeEntry(lean_name: str, lean_type: str, source: CatalogSource)`
- `TypeCache(path: Path)`
- `TypeCache.get(lean_name: str) -> ResolvedTypeEntry | None`
- `TypeCache.put(entry: ResolvedTypeEntry) -> None`
- `DeclarationTypeResolver(lean_root: Path, catalog: tuple[CatalogEntry, ...], cache: TypeCache)`
- `DeclarationTypeResolver.resolve(lean_name: str) -> ResolvedTypeEntry`

- [ ] **Step 1: Write failing cache and resolver tests**

Add these concrete fast tests using temporary files and `monkeypatch`:

```python
def test_cache_rejects_wrong_environment_pin(tmp_path: Path) -> None:
    path = tmp_path / "cache.jsonl"
    path.write_text('{"lean_name":"Nat.Prime","lean_type":"Nat → Prop","source":{"kind":"environment","revision":"wrong","mathlib_revision":"70f3f13433ba3d82a15a7cae679abac9128f102b"}}\n')
    with pytest.raises(ValueError):
        TypeCache(path)


def test_resolver_rejects_name_absent_from_catalog(tmp_path: Path) -> None:
    cache = TypeCache(tmp_path / "cache.jsonl")
    resolver = DeclarationTypeResolver(Path("lean"), tuple(), cache)
    with pytest.raises(KeyError):
        resolver.resolve("Does.Not.Exist")


def test_cache_hit_skips_subprocess(monkeypatch, tmp_path: Path) -> None:
    source = CatalogSource(kind="environment", revision=LEAN_ENVIRONMENT_REVISION, mathlib_revision=MATHLIB_REVISION)
    catalog = (CatalogEntry(id="mathlib.Nat.Prime", lean_name="Nat.Prime", source=source),)
    cache = TypeCache(tmp_path / "cache.jsonl")
    cache.put(ResolvedTypeEntry(lean_name="Nat.Prime", lean_type="Nat.Prime (p : Nat) : Prop", source=source))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("subprocess should not run")))
    result = DeclarationTypeResolver(Path("lean"), catalog, cache).resolve("Nat.Prime")
    assert result.lean_type.startswith("Nat.Prime")
```

Add one test that simulates a resolver failure and asserts the preexisting cache bytes remain unchanged.

- [ ] **Step 2: Verify red state**

Run:

```bash
.venv/bin/python -m pytest tests/test_catalog.py -v
```

- [ ] **Step 3: Implement `ResolveDeclaration.lean`**

The Lean file reads one exact name from `SLEAN_DECLARATION_NAME`, looks it up exactly in the environment, calls `ppExpr` only on that declaration's type, and emits exactly one JSON object with `lean_name`, `lean_type`, and pinned environment provenance. Missing declarations exit nonzero. No fuzzy lookup and no fallback declaration is permitted.

- [ ] **Step 4: Implement deterministic cache and resolver**

`TypeCache` loads and validates all rows on construction. `put()` replaces by exact Lean name, sorts by Lean name, writes through a temporary file, and atomically replaces the cache.

`DeclarationTypeResolver.resolve()`:

1. verifies exact catalog membership;
2. returns a valid cache hit immediately;
3. invokes `lake env lean SleanExperiment/ResolveDeclaration.lean` only on a miss;
4. passes exactly one `SLEAN_DECLARATION_NAME` environment value;
5. rejects malformed JSON, wrong name, wrong pin, or blank type;
6. writes only a fully validated result to cache.

- [ ] **Step 5: Add one explicit slow real integration test**

Mark it `@pytest.mark.slow`. Use a temporary empty cache, resolve `Nat.Prime`, assert the returned type is nonempty and contains `Nat.Prime`, then construct a second resolver with the same cache and verify the cache row is reused.

- [ ] **Step 6: Verify fast and slow suites separately**

Run:

```bash
.venv/bin/python -m pytest -v
.venv/bin/python -m pytest -m slow tests/test_catalog.py -v
git diff --check
```

- [ ] **Step 7: Commit**

```bash
git add lean/SleanExperiment/ResolveDeclaration.lean src/slean_experiment/catalog.py experiment/registry/type_cache.jsonl tests/test_catalog.py
git commit -m "feat: add lazy Lean declaration type cache"
```

Stop after Task 4B.

---

### Task 4C: Integrate Full Catalog Search and Curated Overrides

**Files:**
- Modify: `src/slean_experiment/registry.py`
- Modify: `tests/test_registry.py`
- Replace obsolete sampled-export tests in: `tests/test_registry_export.py`

**Interfaces:**
- `Registry.from_files(curated_path: Path, aliases_path: Path, catalog_path: Path | None = None, type_cache_path: Path | None = None) -> Registry`
- `Registry.get(id: str) -> RegistryEntry | CatalogEntry`
- `Registry.get_raw(id: str) -> CatalogEntry`
- `Registry.search(query: str, limit: int = 20) -> list[RegistryEntry | CatalogEntry]`
- Search may read already-cached type text but never launches Lean and never mutates the cache.

- [ ] **Step 1: Write failing search/override tests**

Add explicit assertions:

```python
def test_curated_nat_prime_overrides_raw_identity(registry_with_catalog: Registry) -> None:
    assert registry_with_catalog.get("mathlib.Nat.Prime").id == "number_theory.nat_prime"
    assert registry_with_catalog.get_raw("mathlib.Nat.Prime").id == "mathlib.Nat.Prime"


def test_prime_alias_still_has_three_curated_meanings(registry_with_catalog: Registry) -> None:
    assert [entry.id for entry in registry_with_catalog.lookup_alias("prime")] == [
        "number_theory.nat_prime",
        "algebra.prime_element",
        "ring_theory.prime_ideal",
    ]


def test_exact_curated_alias_ranks_first(registry_with_catalog: Registry) -> None:
    results = registry_with_catalog.search("prime", limit=10)
    assert results[0].id in {
        "number_theory.nat_prime",
        "algebra.prime_element",
        "ring_theory.prime_ideal",
    }
    assert all(result.id != "mathlib.Nat.Prime" for result in results)


def test_uncached_raw_name_is_searchable(registry_with_catalog: Registry) -> None:
    results = registry_with_catalog.search("Polynomial.eval₂", limit=20)
    assert any(getattr(result, "lean_name", getattr(getattr(result, "target", None), "lean_name", None)) == "Polynomial.eval₂" for result in results)


def test_search_is_deterministic(registry_with_catalog: Registry) -> None:
    first = [entry.id for entry in registry_with_catalog.search("prime", limit=20)]
    second = [entry.id for entry in registry_with_catalog.search("prime", limit=20)]
    assert first == second
```

Also add a cached-type fixture containing a unique token and assert search can match that token only when the type is already cached; no resolver is invoked.

- [ ] **Step 2: Verify red state**

Run:

```bash
.venv/bin/python -m pytest tests/test_registry.py tests/test_registry_export.py -v
```

- [ ] **Step 3: Migrate registry internals to catalog entries**

Remove `SAMPLE_SIZE`, `select_declaration_names`, `export_mathlib_registry`, and the assumption that every raw declaration has `lean_type`. Import the catalog and cache models from `catalog.py`.

Construct in-memory indexes once. Preserve current curated alias validation and curated declaration/core-form target models.

- [ ] **Step 4: Implement deterministic search ranking**

Use these ordered scoring tiers:

1. exact curated alias;
2. exact curated stable ID or curated Lean name;
3. exact raw ID or raw Lean name;
4. curated alias/ID/name prefix;
5. raw ID/name prefix or conservative token match derived only from the declaration name;
6. case-insensitive substring match in curated description or already-cached type text;
7. lexical canonical ID/name tie-break.

Deduplicate by canonical model-facing identity before applying `limit`. A raw declaration with a curated override never appears as a second competing result.

- [ ] **Step 5: Verify full fast suite**

Run:

```bash
.venv/bin/python -m pytest -v
git diff --check
```

- [ ] **Step 6: Commit**

```bash
git add src/slean_experiment/registry.py tests/test_registry.py tests/test_registry_export.py
git commit -m "feat: search full Slean declaration catalog"
```

Stop after Task 4C.

---

### Task 4D: Retire the Sampled Typed Index and Close Revised Task 4

**Files:**
- Delete: `lean/SleanExperiment/ExportRegistry.lean`
- Delete: `experiment/registry/mathlib.jsonl`
- Modify: `tests/test_registry_export.py`
- Modify: `experiment/README.md`
- Verify: `experiment/registry/catalog.jsonl`
- Verify: `experiment/registry/type_cache.jsonl`

**Interfaces:**
- No new runtime API; this task completes migration and records acceptance evidence.

- [ ] **Step 1: Add a regression test forbidding legacy assumptions**

Add a test that reads production Python/Lean source files and asserts the following strings are absent from production registry/catalog implementation:

```python
for forbidden in ("SAMPLE_SIZE", "select_declaration_names", "SLEAN_MANDATORY_NAMES"):
    assert forbidden not in production_source
```

Also assert `lean/SleanExperiment/ExportRegistry.lean` and `experiment/registry/mathlib.jsonl` do not exist after migration.

- [ ] **Step 2: Delete obsolete sampled-index files and update README**

Remove the two legacy files. Update `experiment/README.md` to state that `catalog.jsonl` is the complete name catalog and `type_cache.jsonl` contains only lazily resolved signatures.

- [ ] **Step 3: Record deterministic catalog/cache evidence**

Run:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import hashlib, json
catalog = Path("experiment/registry/catalog.jsonl")
cache = Path("experiment/registry/type_cache.jsonl")
rows = [json.loads(line) for line in catalog.read_text().splitlines() if line.strip()]
names = [r["lean_name"] for r in rows]
cache_rows = [json.loads(line) for line in cache.read_text().splitlines() if line.strip()] if cache.exists() else []
print("catalog_count", len(rows))
print("namespaces", len({n.split('.', 1)[0] for n in names}))
print("first", names[0])
print("last", names[-1])
print("catalog_sha256", hashlib.sha256(catalog.read_bytes()).hexdigest())
print("cache_count", len(cache_rows))
print("cache_sha256", hashlib.sha256(cache.read_bytes()).hexdigest() if cache.exists() else "missing")
PY
```

The catalog count must be greater than 5,002.

- [ ] **Step 4: Run final fast verification**

```bash
.venv/bin/python -m pytest -v
git diff --check
```

- [ ] **Step 5: Run the narrow slow integration smoke**

```bash
.venv/bin/python -m pytest -m slow tests/test_catalog.py -v
```

This run resolves only targeted declarations and must not bulk-pretty-print the environment.

- [ ] **Step 6: Commit**

```bash
git add -A lean/SleanExperiment experiment/registry src/slean_experiment tests experiment/README.md
git commit -m "refactor: retire sampled Mathlib type index"
```

After Task 4D passes review, continue with Task 5 of `docs/superpowers/plans/2026-09-11-sleanir-core-design-experiment.md`. Task 5 compiles declaration symbols from exact Lean names and does not require a precomputed type merely to render the symbol.
