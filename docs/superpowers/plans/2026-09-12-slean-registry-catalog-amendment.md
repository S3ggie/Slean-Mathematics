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
- Catalog generation must enumerate the entire `env.constants` name set and must not call `ppExpr` per catalog row.
- Raw IDs remain `mathlib.<Lean.Name>`.
- Curated stable Slean IDs remain authoritative when a curated declaration target has the same exact Lean name as a raw catalog declaration.
- Curated core forms remain independent of declaration catalog rows.
- Catalog and cache writes must not corrupt a previously valid artifact on failure.
- Default pytest remains fast and excludes tests marked `slow`.
- The legacy 5,000-row typed sample is temporary compatibility state only and must be retired by Task 4D.

---

### Task 4A: Export the Complete Lightweight Declaration Catalog

**Files:**
- Create: `lean/SleanExperiment/ExportCatalog.lean`
- Create: `src/slean_experiment/catalog.py`
- Create generated: `experiment/registry/catalog.jsonl`
- Create: `tests/test_catalog.py`
- Preserve temporarily: `experiment/registry/mathlib.jsonl`

**Interfaces:**
- Produces `CatalogSource(kind="environment", lean_revision, mathlib_revision)`.
- Produces `CatalogEntry(id: str, lean_name: str, source: CatalogSource)`; there is no `lean_type` field.
- Produces `CatalogExportReport(success: bool, declaration_count: int, output: Path, lean_revision: str, mathlib_revision: str)`.
- Produces `export_catalog(lean_root: Path, output: Path) -> CatalogExportReport`.
- Produces `load_catalog(path: Path) -> tuple[CatalogEntry, ...]` sorted by `lean_name`.
- Task 4B consumes this catalog API.

- [ ] **Step 1: Write failing lightweight-catalog contract tests**

Create `tests/test_catalog.py` with focused tests equivalent to:

```python
from pathlib import Path
import json
import pytest

from slean_experiment.catalog import (
    CatalogEntry,
    LEAN_ENVIRONMENT_REVISION,
    MATHLIB_REVISION,
    load_catalog,
)

CATALOG = Path("experiment/registry/catalog.jsonl")


def test_catalog_rows_have_no_precomputed_type() -> None:
    row = json.loads(CATALOG.read_text().splitlines()[0])
    assert set(row) == {"id", "lean_name", "source"}
    assert "lean_type" not in row


def test_catalog_is_complete_scale_and_sorted() -> None:
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
```

Also test malformed rows, duplicate IDs/names, wrong Lean pin, wrong Mathlib pin, blank names, and atomic-write preservation through a mocked exporter failure.

- [ ] **Step 2: Run the new tests and verify the intended red state**

Run:

```bash
.venv/bin/python -m pytest tests/test_catalog.py -v
```

Expected: FAIL because the catalog module/artifact does not exist yet.

- [ ] **Step 3: Implement a names-only Lean exporter**

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

The exact Lean syntax may be adjusted for the pinned APIs, but this file must not call `ppExpr` and must emit every `env.constants` name exactly once.

- [ ] **Step 4: Implement strict Python catalog models/export**

Create `src/slean_experiment/catalog.py`. Reuse the exact existing pin constants or move the constants from `registry.py` into this module and import them back; do not duplicate divergent values.

`export_catalog()` must:

1. verify `lean_root` exists;
2. invoke `lake env lean SleanExperiment/ExportCatalog.lean` with a practical timeout;
3. parse every stdout row as `CatalogEntry`;
4. reject an empty export;
5. reject duplicate IDs or names;
6. verify lexical `lean_name` order;
7. validate exact environment pins;
8. write to a temporary file;
9. atomically replace `catalog.jsonl` only after complete validation.

Do not read curated data to decide which declarations are exported. The catalog is the full environment, independent of Slean semantics.

- [ ] **Step 5: Generate the real full catalog and verify it is cheap**

Run a single real export:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from slean_experiment.catalog import export_catalog
print(export_catalog(Path("lean"), Path("experiment/registry/catalog.jsonl")))
PY
```

Record wall time and declaration count. The output must contain substantially more than the previous 5,002 rows. If a names-only export is still unexpectedly slow, stop and diagnose before adding type work.

- [ ] **Step 6: Run Task 4A and existing fast tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_catalog.py -v
.venv/bin/python -m pytest -v
git diff --check
```

Expected: all fast tests pass. No real bulk type pretty-printing occurs.

- [ ] **Step 7: Commit Task 4A**

```bash
git add lean/SleanExperiment/ExportCatalog.lean src/slean_experiment/catalog.py experiment/registry/catalog.jsonl tests/test_catalog.py
git commit -m "feat: export full Lean declaration catalog"
```

Do not delete the old sampled `mathlib.jsonl` yet; later tasks still reference it until 4C/4D migration is complete.

---

### Task 4B: Add Targeted Type Resolution and Version-Pinned Cache

**Files:**
- Create: `lean/SleanExperiment/ResolveDeclaration.lean`
- Modify: `src/slean_experiment/catalog.py`
- Create generated/seeded: `experiment/registry/type_cache.jsonl`
- Expand: `tests/test_catalog.py`

**Interfaces:**
- Produces `ResolvedTypeEntry(lean_name: str, lean_type: str, source: CatalogSource)`.
- Produces `TypeCache(path: Path)` with `get(lean_name: str) -> ResolvedTypeEntry | None`, `put(entry: ResolvedTypeEntry) -> None`, and deterministic sorted persistence.
- Produces `DeclarationTypeResolver(lean_root: Path, catalog: tuple[CatalogEntry, ...], cache: TypeCache)`.
- Produces `DeclarationTypeResolver.resolve(lean_name: str) -> ResolvedTypeEntry`.
- `resolve()` returns a valid cache hit without launching Lean; otherwise it performs one targeted pinned-Lean resolution, validates it, caches it, and returns it.
- Task 4C may use cached types for search ranking/content but search must not eagerly resolve types.

- [ ] **Step 1: Write failing cache/resolver tests**

Add tests equivalent to:

```python
def test_cache_rejects_wrong_environment_pin(tmp_path): ...
def test_cache_is_sorted_and_deterministic(tmp_path): ...
def test_resolver_rejects_name_absent_from_catalog(...): ...
def test_cache_hit_does_not_call_subprocess(...): ...
def test_failed_resolution_does_not_corrupt_existing_cache(...): ...
```

Use mocks/fixtures for the default fast suite. Add one `@pytest.mark.slow` real integration test resolving an uncached declaration such as `Nat.Prime`, then resolving it again while proving the second read comes from cache.

- [ ] **Step 2: Run targeted tests and verify red state**

Run:

```bash
.venv/bin/python -m pytest tests/test_catalog.py -v
```

Expected: FAIL on missing resolver/cache interfaces.

- [ ] **Step 3: Implement targeted Lean resolution only**

Create `lean/SleanExperiment/ResolveDeclaration.lean` that reads exactly one requested declaration name from an environment variable such as `SLEAN_DECLARATION_NAME`, uses `env.find?`/the pinned equivalent to obtain that constant, calls `ppExpr` only for that declaration's type, and emits one compact JSON row containing `lean_name`, `lean_type`, and exact environment provenance.

If the declaration does not exist, exit nonzero with a clear error. Never fall back to fuzzy lookup.

- [ ] **Step 4: Implement deterministic cache and resolver**

`TypeCache.put()` must replace by exact `lean_name`, sort all cache rows by `lean_name`, write through a temporary file, and atomically replace the cache.

`DeclarationTypeResolver.resolve()` must:

1. require exact catalog membership;
2. return a valid exact-pin cache hit immediately;
3. invoke the targeted Lean resolver only on a miss;
4. reject wrong-name, wrong-pin, malformed, or blank-type results;
5. cache only a fully validated result.

- [ ] **Step 5: Seed only a small reproducible cache**

Seed `experiment/registry/type_cache.jsonl` with the curated declaration targets that are useful for current tests, or preserve an even smaller smoke-test set. Do not bulk-resolve the full catalog.

- [ ] **Step 6: Verify fast and slow behavior separately**

Run:

```bash
.venv/bin/python -m pytest -v
.venv/bin/python -m pytest -m slow tests/test_catalog.py -v
git diff --check
```

The default suite must remain fast. The slow smoke test should perform only targeted resolution, not thousands of `ppExpr` calls.

- [ ] **Step 7: Commit Task 4B**

```bash
git add lean/SleanExperiment/ResolveDeclaration.lean src/slean_experiment/catalog.py experiment/registry/type_cache.jsonl tests/test_catalog.py
git commit -m "feat: add lazy Lean declaration type cache"
```

---

### Task 4C: Integrate Full Catalog Search and Curated Overrides

**Files:**
- Modify: `src/slean_experiment/registry.py`
- Modify: `tests/test_registry.py`
- Modify: `tests/test_registry_export.py` or replace obsolete tests with catalog-oriented tests

**Interfaces:**
- `Registry.from_files(curated_path: Path, aliases_path: Path, catalog_path: Path | None = None, type_cache_path: Path | None = None) -> Registry`.
- `Registry.get(id: str) -> RegistryEntry | CatalogEntry`.
- `Registry.get_raw(id: str) -> CatalogEntry`.
- `Registry.search(query: str, limit: int = 20) -> list[RegistryEntry | CatalogEntry]`.
- Search reads cached types if present but never invokes the resolver and never mutates cache.
- Curated declaration targets override model-facing raw identity for the same exact Lean name.

- [ ] **Step 1: Write failing registry integration/search tests**

Cover:

```python
def test_curated_nat_prime_overrides_raw_catalog_identity(): ...
def test_raw_catalog_entry_remains_inspectable(): ...
def test_prime_alias_has_exactly_three_curated_meanings(): ...
def test_search_exact_curated_alias_ranks_first(): ...
def test_search_exact_lean_name_finds_raw_or_curated_canonical_entry(): ...
def test_search_is_deterministic(): ...
def test_search_can_find_uncached_catalog_entry_by_name(): ...
def test_search_uses_cached_type_text_without_resolving_uncached_types(): ...
def test_core_forms_are_not_shadowed_by_catalog(): ...
```

Search ranking must be deterministic. Use this precedence unless an equally explicit implementation is simpler and tests preserve the same intent:

1. exact curated alias;
2. exact curated stable ID or exact curated Lean name;
3. exact raw ID or exact raw Lean name;
4. curated ID/name/alias prefix;
5. raw ID/name prefix or conservative declaration-name token match;
6. weaker case-insensitive substring/type-cache match;
7. lexical canonical ID/name tie-break.

Do not create semantic aliases from raw declaration names.

- [ ] **Step 2: Run registry tests and verify red state**

Run:

```bash
.venv/bin/python -m pytest tests/test_registry.py tests/test_registry_export.py -v
```

- [ ] **Step 3: Migrate registry internals from sampled typed rows to catalog entries**

Remove `SAMPLE_SIZE`, `select_declaration_names`, the bulk export function, and `RawRegistryEntry` assumptions that every raw declaration has `lean_type`.

Import `CatalogEntry`, catalog loading, and optional cached type data from `catalog.py`.

Do not put subprocess/type-resolution behavior in `Registry.search()`.

- [ ] **Step 4: Implement deterministic `Registry.search()`**

Normalize queries with the existing whitespace/casefold policy. Build in-memory indexes once during registry construction. Return curated canonical entries when a raw declaration has a curated override; never return both as competing model-facing results.

- [ ] **Step 5: Run full fast suite**

Run:

```bash
.venv/bin/python -m pytest -v
git diff --check
```

Expected: all Task 1-4C fast tests pass with no bulk Lean export.

- [ ] **Step 6: Commit Task 4C**

```bash
git add src/slean_experiment/registry.py tests/test_registry.py tests/test_registry_export.py
git commit -m "feat: search full Slean declaration catalog"
```

---

### Task 4D: Retire the Sampled Typed Index and Verify the Revised Architecture

**Files:**
- Delete: `lean/SleanExperiment/ExportRegistry.lean`
- Delete: `experiment/registry/mathlib.jsonl`
- Modify/remove obsolete sampling tests: `tests/test_registry_export.py`
- Modify if needed: `experiment/README.md`
- Verify generated: `experiment/registry/catalog.jsonl`
- Verify generated: `experiment/registry/type_cache.jsonl`

**Interfaces:**
- No new runtime API. This task closes the migration and establishes the revised Task 4 acceptance evidence.

- [ ] **Step 1: Add a regression test forbidding legacy sampled-index assumptions**

Ensure tests fail if production registry code references `SAMPLE_SIZE`, `select_declaration_names`, `ExportRegistry.lean`, or requires every catalog row to contain `lean_type`.

- [ ] **Step 2: Delete the obsolete exporter and sampled typed artifact**

Remove `lean/SleanExperiment/ExportRegistry.lean` and `experiment/registry/mathlib.jsonl`. Update tests/docs to refer only to `catalog.jsonl` plus `type_cache.jsonl`.

- [ ] **Step 3: Verify the complete committed catalog**

Programmatically report:

- total declaration count;
- distinct top-level namespaces;
- lexically first and last declaration names;
- SHA-256 of `catalog.jsonl`;
- cached resolved-type count;
- SHA-256 of `type_cache.jsonl`.

The declaration count must be greater than 5,002 and correspond to the full names emitted by the pinned environment, not a sample.

- [ ] **Step 4: Run final fast verification**

Run:

```bash
.venv/bin/python -m pytest -v
git diff --check
```

Expected: all fast tests pass quickly and no bulk type pretty-printing occurs.

- [ ] **Step 5: Run one explicit real integration smoke**

Run only the narrow slow tests:

```bash
.venv/bin/python -m pytest -m slow tests/test_catalog.py -v
```

This must verify a real uncached targeted declaration type lookup and subsequent cache-hit behavior. It must not perform full-environment type pretty-printing.

- [ ] **Step 6: Commit Task 4D**

```bash
git add -A lean/SleanExperiment experiment/registry src/slean_experiment tests experiment/README.md
git commit -m "refactor: retire sampled Mathlib type index"
```

After this commit, revised Task 4 is complete. Continue with Task 5 of `docs/superpowers/plans/2026-09-11-sleanir-core-design-experiment.md`; Task 5's compiler should consume exact declaration names from curated entries or catalog entries and must not require a precomputed type merely to render a symbol.
