# Slean Math Registry Catalog Amendment

Date: 2026-09-12
Status: Approved architecture amendment; supersedes the bulk typed-index design in Section 5.4 of `2026-09-11-sleanir-core-design-experiment.md` and the corresponding Task 4 implementation assumptions.

## 1. Reason for the amendment

The original registry design assumed that Slean could cheaply import the pinned Mathlib environment, enumerate a large set of declarations, pretty-print every selected declaration type, and commit that fully typed raw index.

Real implementation disproved that assumption on the target media-server environment. Loading Mathlib and running `ppExpr` over thousands of declaration types remained CPU-bound for tens of minutes and exceeded the practical integration-test budget. Re-ranking an already exported subset cannot recover declarations that were never exported, so a sampled typed index also fails the broader architectural goal: Slean should be able to discover mathematics throughout the pinned environment without manually extending the core or depending on an alphabetically or statistically limited subset.

The registry architecture is therefore changed from **bulk typed indexing** to **full lightweight catalog + lazy type resolution/cache**.

## 2. Goals

The revised registry must:

- know that every declaration in the pinned imported Lean/Mathlib environment exists;
- assign every raw declaration a deterministic ID of the form `mathlib.<Lean.Name>`;
- preserve the curated semantic overlay and its stable Slean IDs;
- retrieve broad candidate declarations without precomputing thousands of expensive pretty-printed types;
- resolve exact declaration types only when a declaration is actually needed;
- persist resolved type information so repeated use does not repeatedly invoke Lean pretty-printing;
- remain deterministic and pinned to the experiment's Lean and Mathlib versions;
- keep ordinary tests fast;
- never introduce an LLM into registry indexing, lookup, type resolution, or compilation.

## 3. Revised architecture

The registry consists of four layers.

### 3.1 Full lightweight declaration catalog

A Lean exporter imports the pinned Mathlib environment, enumerates `env.constants`, and emits a row for **every declaration name** without calling `ppExpr` for every row.

Each catalog row minimally contains:

- raw ID: `mathlib.<Lean.Name>`;
- exact Lean declaration name;
- pinned environment provenance;
- no fabricated human description;
- no fabricated semantic aliases;
- no requirement that a pretty-printed type already exist.

The catalog is sorted deterministically by exact Lean declaration name before serialization.

The catalog should be cheap enough to regenerate whenever the pinned environment changes because enumeration and name serialization are substantially less work than pretty-printing every declaration type.

### 3.2 Curated semantic overlay

The existing curated registry remains authoritative for concepts that Slean explicitly understands semantically.

If a curated declaration target has the same exact Lean declaration name as a raw catalog declaration, model-facing identity is the curated Slean ID rather than the raw `mathlib.*` ID.

Example:

```text
raw catalog: mathlib.Nat.Prime -> Nat.Prime
curated:     number_theory.nat_prime -> Nat.Prime

model-facing canonical identity: number_theory.nat_prime
```

The raw catalog entry remains inspectable for research/debugging, but it does not become a duplicate semantic candidate.

Curated core-form entries such as `forall`, `exists`, and `implies` remain independent of declaration catalog entries.

### 3.3 Lazy declaration type resolver

When Slean needs the formal type/signature of a declaration and that type is not already present in the cache, it invokes a **targeted Lean query for that declaration only**.

The resolver must:

1. verify that the declaration exists in the full catalog;
2. invoke the pinned Lean environment with exactly that declaration name;
3. obtain the declaration's exact pretty-printed type from Lean;
4. validate that the returned name and environment pins match the request;
5. return the typed result;
6. persist the result in the type cache.

No semantic interpretation occurs during this step. The resolver answers only: "What formal type does this exact Lean declaration have in this exact pinned environment?"

A targeted batch query for a small set of already selected declarations is allowed when it is measurably more efficient than one process per declaration, provided the API remains deterministic and the batch contains only requested declarations.

### 3.4 Persistent type cache

Resolved declaration types are stored in a deterministic cache keyed by:

- exact Lean declaration name;
- Lean version;
- Mathlib revision.

A cache entry from a different Lean or Mathlib version must never be silently reused.

The cache is reproducible state, not semantic source-of-truth. Lean remains the source of truth. Corrupt, stale, malformed, or mismatched cache entries must be rejected and regenerated from the pinned environment.

The committed experiment may seed the cache with:

- curated declaration targets;
- declarations required by benchmark fixtures;
- declarations encountered during reproducible smoke tests.

It does **not** need to pre-resolve every catalog declaration.

## 4. Registry lookup and search

The registry must support deterministic discovery across the full catalog and curated overlay.

`Registry.search(query, limit)` searches at least:

- curated stable IDs;
- curated human aliases;
- curated descriptions where useful;
- exact Lean declaration names;
- raw catalog IDs;
- cached type strings when available.

Ranking must be deterministic. At minimum, exact curated alias/ID/name matches outrank prefix/name-token matches, which outrank weaker lexical matches. Ties use stable lexical IDs/names.

Raw declaration names may be tokenized conservatively for search. This tokenization is only a retrieval aid; it must not create semantic aliases or claim that a declaration name uniquely captures a human mathematical meaning.

A raw declaration without a cached type is still searchable and inspectable. Type resolution happens only after retrieval when the caller actually needs formal type information.

## 5. Compiler contract

The deterministic SleanIR compiler may resolve a symbol through either:

- a curated registry entry; or
- a raw declaration catalog entry.

For declaration targets, the compiler needs the exact Lean declaration name to render the symbol. It does **not** need the pretty-printed declaration type merely to emit the name.

Type information is used by interpretation, validation, candidate filtering, diagnostics, and benchmark tooling where required. Missing cached type information must never cause the compiler to invent or guess a signature.

The compiler must continue to dispatch on IR node kind and formal target metadata only. Mathematical subject concepts must not create concept-specific branches.

## 6. Provenance and versioning

The full catalog and type cache are tied to the exact experiment environment:

- Lean: `v4.34.0-rc2`
- Mathlib: `70f3f13433ba3d82a15a7cae679abac9128f102b`

A future Lean or Mathlib upgrade creates a new catalog/cache snapshot. Existing artifacts retain their original registry/environment version and are never silently reinterpreted against a newer snapshot.

Curated entries continue to distinguish Lean-owned declarations/core forms from Mathlib-owned declarations where verified. Raw catalog rows may truthfully record that a declaration was observed in the pinned imported environment when exact ownership is not available from the exporter; ownership must never be fabricated.

## 7. Performance policy

Expensive full-environment type pretty-printing is explicitly removed from normal registry generation and normal test runs.

The following operations should be cheap enough for ordinary development:

- enumerate full declaration names;
- load/validate the catalog;
- search the catalog;
- load/validate cached resolved types;
- resolve a small requested declaration set.

Tests that launch the real pinned Lean environment may be marked as slow integration tests and excluded from the default fast test suite. The fast suite must still test selection, validation, cache invalidation, search ranking, override behavior, and failure handling with fixtures or the committed catalog.

A slow integration smoke test should verify at least one uncached targeted type lookup against the real pinned environment and then verify a cache hit does not invoke the resolver again.

## 8. Failure behavior

The registry must fail explicitly rather than silently degrade when:

- catalog provenance does not match the pinned environment;
- duplicate declaration names or raw IDs appear;
- a requested declaration is absent from the catalog;
- targeted Lean resolution fails;
- targeted Lean resolution returns a different declaration than requested;
- a resolved type is empty;
- cached provenance is stale or malformed;
- curated aliases reference missing curated IDs.

Failure must not corrupt an existing catalog or cache. Writes use temporary files plus atomic replacement where practical.

## 9. Experiment implications

This amendment does not change the A/B/C/D candidate schemas, benchmark winner criteria, ambiguity policy, false-statement policy, or Luna Low testing strategy.

It changes only how Slean obtains broad formal vocabulary from Lean/Mathlib.

The experiment should provide each candidate the same registry lookup capabilities. A candidate may retrieve raw declaration names broadly and request exact types for the small set of declarations relevant to a benchmark item. This avoids both extremes:

- an incomplete sampled vocabulary; and
- dumping an enormous fully typed Mathlib registry into the model context.

Registry lookup bundles given to Luna must remain bounded and identical in policy across A/B/C/D.

## 10. Acceptance criteria for the revised Task 4

Task 4 is complete when:

1. a deterministic full declaration-name catalog is generated from the pinned imported environment;
2. the catalog contains substantially more than the previous 5,000-row sample and represents the entire `env.constants` declaration-name set;
3. curated declarations override raw identities without duplication;
4. raw declarations remain inspectable through their raw IDs;
5. deterministic `Registry.search()` works across curated and raw catalog data;
6. a targeted resolver obtains and validates the exact type of a requested declaration from pinned Lean;
7. resolved types are cached with exact Lean/Mathlib provenance;
8. stale cache entries are rejected;
9. ordinary tests do not bulk-pretty-print Mathlib declarations;
10. at least one real uncached targeted-resolution integration test passes;
11. the existing 5,000-row sampled typed artifact is retired or migrated so it is no longer presented as the full registry source of truth;
12. no LLM participates in catalog generation, type resolution, or cache maintenance.

## 11. Superseded assumptions

The following earlier Task 4 assumptions are superseded:

- raw registry rows do **not** all need a precomputed `lean_type`;
- the registry is **not** defined by a fixed 5,000-declaration sample;
- Task 4 completion does **not** require pretty-printing thousands of declaration types in one run;
- broad mathematical coverage comes from the full lightweight catalog, while detailed formal type information is resolved lazily.

All other approved SleanIR experiment decisions remain unchanged.
