# SleanIR Core Design Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible experiment harness that compares three candidate SleanIR representations against direct natural-language-to-Lean generation using GPT-5.6 Luna at Low reasoning effort.

**Architecture:** Keep the experiment isolated from future production Slean code. Python owns schemas, registry search, dataset ingestion, orchestration, metrics, and reporting; a pinned Lean/Mathlib project owns declaration export, parsing, typechecking, and equivalence checks. A Codex CLI adapter performs high-volume Luna Low generations. For candidates A/B/C, accepted SleanIR is compiled to Lean by deterministic code only.

**Tech Stack:** Python 3.12+, Pydantic 2, pytest, Hypothesis, Typer, Lean 4, Mathlib, Lake, Codex CLI (`gpt-5.6-luna`, Low reasoning).

**Spec:** `docs/superpowers/specs/2026-09-11-sleanir-core-design-experiment.md`

## Global Constraints

- SleanIR v0 in this experiment represents mathematical **statements only**.
- Candidate D is a direct NL -> Lean control and must always be tested alongside A/B/C.
- Primary high-volume model is **GPT-5.6 Luna at Low reasoning effort through Codex**.
- Accepted SleanIR -> Lean compilation is deterministic; no LLM may reinterpret accepted IR.
- Every path returns exactly one of `formalization` or `clarification_required`.
- Clear false statements are formalized faithfully; they are never silently corrected.
- Ambiguous statements return `clarification_required` when meaning-changing ambiguity remains.
- Existing audited Lean statements are the canonical gold targets.
- Semantic faithfulness is the primary metric.
- SleanIR must beat direct NL -> Lean by at least **5 absolute percentage points** in semantic faithfulness, unless it stays within 1 point while reducing model usage burden by roughly **30% or more**.
- Gold outputs are never included in model prompts or repair feedback.
- Maximum repair budget is two retries after the initial attempt.
- Dataset, prompts, schemas, registry, Lean version, Mathlib commit, evaluator version, model, and reasoning setting are recorded for every run.
- A raw Mathlib registry snapshot and the same read-only lookup mechanism are available to all A/B/C/D paths; only A/B/C are required to emit registry IDs.

---

## File Structure

```text
Slean-Mathematics/
├── pyproject.toml
├── .gitignore
├── experiment/
│   ├── README.md
│   ├── schemas/
│   │   ├── candidate_a.schema.json
│   │   ├── candidate_b.schema.json
│   │   ├── candidate_c.schema.json
│   │   └── direct.schema.json
│   ├── prompts/
│   │   ├── common.md
│   │   ├── candidate_a.md
│   │   ├── candidate_b.md
│   │   ├── candidate_c.md
│   │   └── direct.md
│   ├── registry/
│   │   ├── curated.json
│   │   ├── aliases.json
│   │   └── mathlib.jsonl
│   ├── stress/
│   │   └── stress.jsonl
│   └── manifests/
│       └── datasets.json
├── lean/
│   ├── lakefile.toml
│   ├── lean-toolchain
│   ├── lake-manifest.json
│   └── SleanExperiment/
│       ├── Basic.lean
│       └── ExportRegistry.lean
├── src/slean_experiment/
│   ├── __init__.py
│   ├── cli.py
│   ├── models.py
│   ├── schemas.py
│   ├── registry.py
│   ├── compiler.py
│   ├── lean.py
│   ├── datasets.py
│   ├── codex_runner.py
│   ├── prompts.py
│   ├── runner.py
│   ├── evaluator.py
│   ├── metrics.py
│   └── report.py
├── tests/
│   ├── fixtures/
│   ├── test_schemas.py
│   ├── test_registry.py
│   ├── test_compiler.py
│   ├── test_lean.py
│   ├── test_datasets.py
│   ├── test_codex_runner.py
│   ├── test_runner.py
│   ├── test_evaluator.py
│   ├── test_metrics.py
│   └── test_stress_set.py
└── runs/                 # generated and gitignored
```

The package is intentionally named `slean_experiment`, not `slean`, so experimental APIs do not accidentally become production contracts.

---

### Task 1: Bootstrap the Experiment and Pin Lean/Mathlib

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `experiment/README.md`
- Create: `lean/lakefile.toml`
- Create: `lean/lean-toolchain`
- Create: `lean/SleanExperiment/Basic.lean`
- Create: `src/slean_experiment/__init__.py`
- Create: `src/slean_experiment/cli.py`
- Test: `tests/test_lean.py`

**Interfaces:**
- Produces package `slean_experiment` and Typer app `slean_experiment.cli:app`.
- Produces a Lake project whose exact Lean/Mathlib revisions are committed in `lean-toolchain`, `lakefile.toml`, and `lake-manifest.json`.
- `LeanEnvironment(root: Path)` in Task 6 assumes `lean/` is the Lake working directory.

- [ ] **Step 1: Create the Python project and failing smoke test**

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "slean-experiment"
version = "0.0.1"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.11,<3", "typer>=0.16,<1"]

[project.optional-dependencies]
test = ["pytest>=8.4,<9", "hypothesis>=6.130,<7"]

[project.scripts]
slean-exp = "slean_experiment.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# src/slean_experiment/cli.py
import typer

app = typer.Typer(no_args_is_help=True)

@app.command()
def version() -> None:
    typer.echo("slean-experiment 0.0.1")
```

```python
# tests/test_lean.py
from pathlib import Path

def test_lean_project_exists() -> None:
    assert Path("lean/lakefile.toml").is_file()
    assert Path("lean/lean-toolchain").is_file()
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python -m pytest tests/test_lean.py -v`

Expected: FAIL because the Lean files do not yet exist.

- [ ] **Step 3: Resolve and freeze one exact Mathlib snapshot**

Create `lean/lakefile.toml`:

```toml
name = "SleanExperiment"
version = "0.1.0"
defaultTargets = ["SleanExperiment"]

[[require]]
name = "mathlib"
git = "https://github.com/leanprover-community/mathlib4.git"
rev = "master"

[[lean_lib]]
name = "SleanExperiment"
```

Bootstrap the toolchain from Mathlib master only for the initial resolution:

```bash
curl -fsSL https://raw.githubusercontent.com/leanprover-community/mathlib4/master/lean-toolchain > lean/lean-toolchain
cd lean
lake update
MATHLIB_SHA="$(python - <<'PY'
import json
m=json.load(open('lake-manifest.json'))
print(next(p['rev'] for p in m['packages'] if p['name']=='mathlib'))
PY
)"
sed -i "s/rev = \"master\"/rev = \"$MATHLIB_SHA\"/" lakefile.toml
curl -fsSL "https://raw.githubusercontent.com/leanprover-community/mathlib4/$MATHLIB_SHA/lean-toolchain" > lean-toolchain
lake update
lake exe cache get
lake env lean --version
cd ..
```

After this task, `master` must not remain in `lean/lakefile.toml`.

Create:

```lean
-- lean/SleanExperiment/Basic.lean
import Mathlib

example : 2 + 2 = 4 := by norm_num
```

- [ ] **Step 4: Verify both stacks and ignore generated state**

```gitignore
.venv/
.pytest_cache/
__pycache__/
*.pyc
runs/
.cache/
lean/.lake/
```

Run:

```bash
python -m pip install -e '.[test]'
python -m pytest tests/test_lean.py -v
cd lean && lake env lean SleanExperiment/Basic.lean && cd ..
slean-exp version
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore experiment/README.md lean src/slean_experiment/__init__.py src/slean_experiment/cli.py tests/test_lean.py
git commit -m "chore: bootstrap SleanIR experiment harness"
```

---

### Task 2: Implement the Common Result Envelope and A/B/C/D Schemas

**Files:**
- Create: `src/slean_experiment/models.py`
- Create: `src/slean_experiment/schemas.py`
- Create generated: `experiment/schemas/candidate_a.schema.json`
- Create generated: `experiment/schemas/candidate_b.schema.json`
- Create generated: `experiment/schemas/candidate_c.schema.json`
- Create generated: `experiment/schemas/direct.schema.json`
- Test: `tests/test_schemas.py`

**Interfaces:**
- `Candidate = Literal["a", "b", "c", "direct"]`
- `validate_result(candidate: Candidate, data: dict[str, object]) -> Result`
- `write_json_schemas(output_dir: Path) -> None`
- `ArtifactMetadata(schema_version, registry_version, lean_version, mathlib_commit, source_statement_id)` is attached by the runner after generation; it is not model-generated.
- Every IR node may carry optional `source_span: {start:int,end:int}`.

- [ ] **Step 1: Write failing contract tests**

```python
import pytest
from pydantic import ValidationError
from slean_experiment.schemas import validate_result


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
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/test_schemas.py -v`

- [ ] **Step 3: Implement strict discriminated models**

Shared node kinds: `var`, `literal`, `symbol`, `apply`, `bind`. Candidate B adds dedicated `forall` and `exists`. Candidate C adds `forall`, `exists`, `implies`, `and`, `or`, `not`, `equals`, while retaining generic `bind`. Use `ConfigDict(extra="forbid")` everywhere.

Public validator:

```python
def validate_result(candidate: Candidate, data: dict[str, object]) -> Result:
    return RESULT_MODELS[candidate].model_validate(data)
```

- [ ] **Step 4: Export deterministic schemas using the planned filenames**

```python
SCHEMA_FILENAMES = {
    "a": "candidate_a.schema.json",
    "b": "candidate_b.schema.json",
    "c": "candidate_c.schema.json",
    "direct": "direct.schema.json",
}

def write_json_schemas(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for candidate, model in RESULT_MODELS.items():
        path = output_dir / SCHEMA_FILENAMES[candidate]
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n")
```

Run schema export twice and assert `sha256sum experiment/schemas/*.json` is unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/models.py src/slean_experiment/schemas.py experiment/schemas tests/test_schemas.py
git commit -m "feat: define SleanIR experiment schemas"
```

---

### Task 3: Build the Typed Registry Contract and Curated Overlay

**Files:**
- Create: `src/slean_experiment/registry.py`
- Create: `experiment/registry/curated.json`
- Create: `experiment/registry/aliases.json`
- Test: `tests/test_registry.py`

**Interfaces:**
- `RegistryEntry(id, lean_name, lean_type, constraints, description, aliases, source)`
- `Registry.get(id: str) -> RegistryEntry`
- `Registry.lookup_alias(text: str) -> list[RegistryEntry]`
- Curated entries override raw Mathlib-index entries with the same `lean_name`; the canonical ID exposed to models is the curated ID when one exists.

- [ ] **Step 1: Test overloaded aliases**

```python
def test_prime_alias_keeps_distinct_meanings(registry):
    ids = {e.id for e in registry.lookup_alias("prime")}
    assert "number_theory.nat_prime" in ids
    assert "algebra.prime_element" in ids
    assert "ring_theory.prime_ideal" in ids
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_registry.py -v`

- [ ] **Step 3: Implement curated entries**

At minimum include canonical IDs for `Nat`, `Int`, `Rat`, `Real`, forall/exists/implies/and/or/not/equality, add/multiply/power, `<`, `≤`, `Even`, `Odd`, `Nat.Prime`, `Prime`, and `Ideal.IsPrime`. Every entry contains exact Lean name, type string, context constraints, human description, aliases, and pinned Mathlib source revision.

- [ ] **Step 4: Enforce registry invariants**

Reject duplicate IDs, duplicate canonical Lean targets, aliases referencing missing IDs, or entries missing source revision. Run registry tests; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/registry.py experiment/registry/curated.json experiment/registry/aliases.json tests/test_registry.py
git commit -m "feat: add typed Slean registry overlay"
```

---

### Task 4: Auto-Index the Pinned Mathlib Environment

**Files:**
- Create: `lean/SleanExperiment/ExportRegistry.lean`
- Modify: `src/slean_experiment/registry.py`
- Create generated: `experiment/registry/mathlib.jsonl`
- Test: `tests/test_registry.py`

**Interfaces:**
- `export_mathlib_registry(lean_root: Path, output: Path) -> RegistryExportReport`
- Raw IDs use `mathlib.<Lean.Name>` unless a curated canonical ID overrides that Lean declaration.
- Each raw row contains `id`, `lean_name`, `lean_type`, and pinned Mathlib revision. Human aliases for raw entries are conservative tokens derived from the declaration name; curated aliases remain authoritative.

- [ ] **Step 1: Add index tests**

Assert the exported index contains `Nat.Prime`, `Ideal.IsPrime`, and at least 1,000 declarations; each has a non-empty type; a curated entry replaces the raw ID for `Nat.Prime` in search results.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_registry.py -v`

- [ ] **Step 3: Implement the Lean exporter**

Use a command elaborator that queries `getEnv`; Lean's environment exposes `env.constants`. The exporter prints one compact JSON object per constant. Core shape:

```lean
import Mathlib
import Lean

open Lean Elab Command Meta

syntax "#slean_export_registry" : command

elab_rules : command
  | `(#slean_export_registry) => do
      let env ← getEnv
      for (name, ci) in env.constants do
        let ty ← liftTermElabM do ppExpr ci.type
        let row := Json.mkObj [
          ("lean_name", name.toString),
          ("lean_type", ty.pretty)
        ]
        liftIO <| IO.println row.compress

#slean_export_registry
```

If the exact pretty-printer API differs in the pinned Lean version, use the pinned version's equivalent `ppExpr`/`Format.pretty`; do not change the output contract.

- [ ] **Step 4: Merge raw index + curated overlay and expose deterministic search**

Implement:

```python
def search(self, query: str, limit: int = 20) -> list[RegistryEntry]:
    """Case-insensitive token search across canonical id, Lean name, aliases, and type."""
```

Sort by exact alias match, prefix/name match, then lexical stable ID so repeated searches are deterministic. Export `experiment/registry/mathlib.jsonl` against the pinned Mathlib commit.

- [ ] **Step 5: Commit**

```bash
git add lean/SleanExperiment/ExportRegistry.lean src/slean_experiment/registry.py experiment/registry/mathlib.jsonl tests/test_registry.py
git commit -m "feat: index pinned Mathlib declarations"
```

---

### Task 5: Implement Deterministic A/B/C -> Lean Compilation

**Files:**
- Create: `src/slean_experiment/compiler.py`
- Test: `tests/test_compiler.py`

**Interfaces:**
- `compile_ir(candidate: Literal["a","b","c"], ir: BaseModel, registry: Registry) -> str`
- Compiler dispatches only on IR node kind and registry metadata; subject concepts never get hardcoded branches.

- [ ] **Step 1: Write cross-candidate golden tests**

All three fixtures for “for every natural n, if n² is even then n is even” must compile to the same canonical Lean proposition:

```python
assert set(outputs.values()) == {"∀ n : Nat, Even (n ^ 2) → Even n"}
```

Also test unknown IDs fail and adding/removing `source_span` never changes Lean output.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_compiler.py -v`

- [ ] **Step 3: Implement precedence-aware generic rendering**

`symbol` resolves through `Registry.get`; `apply` renders a head and arguments; binders render typed variables and body; C's dedicated logical nodes render canonical Lean syntax. No semantic simplification or theorem lookup happens here.

- [ ] **Step 4: Add anti-special-case regression test**

Read `compiler.py` and assert strings such as `number_theory.nat_prime`, `Ideal.IsPrime`, `Continuous`, and `Compact` do not occur in compiler source. Run compiler tests; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/compiler.py tests/test_compiler.py
git commit -m "feat: add deterministic SleanIR compilers"
```

---

### Task 6: Build the Lean Typecheck and Equivalence Harness

**Files:**
- Create: `src/slean_experiment/lean.py`
- Expand: `tests/test_lean.py`

**Interfaces:**
- `LeanEnvironment.typecheck(statement: str, header: str = "import Mathlib") -> LeanResult`
- `LeanEnvironment.equivalent(gold: str, generated: str, header: str = "import Mathlib") -> EquivalenceResult`
- `EquivalenceResult.status`: `exact | proved_equivalent | not_equivalent | unresolved | type_error`.

- [ ] **Step 1: Add tests distinguishing well-typed from true**

```python
def test_false_proposition_can_still_typecheck(lean_env):
    assert lean_env.typecheck("∀ n : ℕ, Even n → Odd n").ok


def test_obvious_type_error_fails(lean_env):
    assert not lean_env.typecheck("Nat.Prime (1 / 2 : ℚ)").ok
```

Also test a simple pair that automation proves equivalent.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_lean.py -v`

- [ ] **Step 3: Implement isolated temporary Lean checks**

Typecheck file body:

```lean
import Mathlib
#check (show Prop from (STATEMENT))
```

Equivalence file body:

```lean
import Mathlib
example : (GOLD) ↔ (GENERATED) := by aesop
```

If `aesop` fails, retry exactly once with `by simp_all`; otherwise return `unresolved`. Invoke `lake env lean` with a 60-second subprocess timeout. Never use an LLM in primary equivalence scoring.

- [ ] **Step 4: Expose reproducibility metadata**

Return exact `lake env lean --version` and Mathlib revision from `lake-manifest.json`; tests assert non-empty values.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/lean.py tests/test_lean.py
git commit -m "feat: add Lean validation and equivalence harness"
```

---

### Task 7: Normalize External NL <-> Lean Datasets

**Files:**
- Create: `src/slean_experiment/datasets.py`
- Create: `experiment/manifests/datasets.json`
- Create: `tests/fixtures/proofnet_sample.jsonl`
- Create: `tests/fixtures/minif2f_sample.json`
- Test: `tests/test_datasets.py`

**Interfaces:**
- `BenchmarkItem(id, source, informal_statement, gold_outcome, gold_lean_statement, header, helpers, subject, license, source_revision, ambiguity)`
- `ingest_all(cache_dir: Path, output: Path, lean: LeanEnvironment) -> IngestReport`
- Gold statements that fail the pinned Lean environment are quarantined.

- [ ] **Step 1: Write fixture tests**

Cover ProofNet-style import, miniF2F-style import, duplicate removal, source revision preservation, and quarantine of an invalid gold Lean statement.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_datasets.py -v`

- [ ] **Step 3: Implement manifest-driven ingestion**

`datasets.json` contains exact source URL, frozen commit/tag, license, adapter name, and enabled flag. Download into `.cache/datasets`; output normalized JSONL sorted by item ID. Preserve imports/headers/helper declarations required by each gold statement.

- [ ] **Step 4: Run fixture tests and a five-item real-source smoke ingest**

```bash
python -m pytest tests/test_datasets.py -v
slean-exp ingest --limit-per-source 5 --output runs/ingest-smoke.jsonl
```

Expected: every accepted item has frozen provenance and a gold statement that typechecks.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/datasets.py experiment/manifests tests/fixtures tests/test_datasets.py
git commit -m "feat: normalize autoformalization datasets"
```

---

### Task 8: Add Frozen Prompts and the Luna Low Codex Runner

**Files:**
- Create: `src/slean_experiment/codex_runner.py`
- Create: `src/slean_experiment/prompts.py`
- Create: `experiment/prompts/common.md`
- Create: `experiment/prompts/candidate_a.md`
- Create: `experiment/prompts/candidate_b.md`
- Create: `experiment/prompts/candidate_c.md`
- Create: `experiment/prompts/direct.md`
- Modify: `src/slean_experiment/cli.py`
- Test: `tests/test_codex_runner.py`

**Interfaces:**
- `CodexConfig(model="gpt-5.6-luna", reasoning_effort="low", timeout_s=180)`
- `CodexRunner.generate(prompt: str, schema_path: Path, lookup_bundle: Path) -> Generation`
- `Generation` records raw final output, parsed JSON, wall time, exit code, model/effort metadata where exposed, and token/usage data where exposed.

- [ ] **Step 1: Test command construction**

Assert the command contains `gpt-5.6-luna`, `model_reasoning_effort="low"`, `--output-schema`, `--ephemeral`, and a read-only sandbox.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_codex_runner.py -v`

- [ ] **Step 3: Implement one fresh Codex turn per attempt**

Construct a command equivalent to:

```bash
codex exec \
  --ephemeral \
  --skip-git-repo-check \
  --sandbox read-only \
  --model gpt-5.6-luna \
  --config 'model_reasoning_effort="low"' \
  --output-schema /ABSOLUTE/PATH/TO/CANDIDATE.schema.json \
  --experimental-json
```

Feed prompt on stdin and parse JSON event lines. Run from a temporary directory containing only a copy of the frozen read-only `registry_lookup.jsonl` generated from Task 4 plus a short `LOOKUP.md` explaining that `rg -i 'term' registry_lookup.jsonl` may be used. No benchmark gold statement is copied into that directory.

The same lookup bundle is available to direct candidate D so registry/Mathlib lookup access is fair.

- [ ] **Step 4: Freeze prompt behavior and add live smoke CLI**

`common.md` explicitly instructs: translate faithfully; do not prove; do not correct false statements; do not add assumptions; request clarification for unresolved meaning-changing ambiguity; output only the requested schema. Candidate files describe only the representation difference.

Add:

```bash
slean-exp codex-smoke --candidate direct --statement 'For every natural number n, n = n.'
```

Unit tests mock subprocess; live smoke is opt-in. Verify runtime metadata confirms Luna Low before proceeding.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/codex_runner.py src/slean_experiment/prompts.py src/slean_experiment/cli.py experiment/prompts tests/test_codex_runner.py
git commit -m "feat: add Luna Low formalization runner"
```

---

### Task 9: Implement Fair Orchestration, Repairs, Resume, and Run Verification

**Files:**
- Create: `src/slean_experiment/runner.py`
- Modify: `src/slean_experiment/cli.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- `run_item(item, candidate, max_repairs=2) -> ItemRun`
- `run_benchmark(items, candidates=("a","b","c","direct"), max_repairs=2) -> RunManifest`
- `verify_run(run_dir: Path) -> VerificationReport`
- Attempts are append-only JSONL under the generated run directory.

- [ ] **Step 1: Test fairness and fixed retry budget**

Assert all four candidates receive identical source statement/context; no prompt contains `gold_lean_statement`; a valid first attempt is not retried; an invalid attempt gets at most two repairs.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_runner.py -v`

- [ ] **Step 3: Implement execution pipeline**

A/B/C: model JSON -> schema validation -> metadata attachment -> deterministic compile -> Lean typecheck. Direct: model JSON -> Lean typecheck. Repair prompts may contain only previous model output and deterministic schema/Lean type error. Semantic comparison to gold happens **after** generation and never produces repair feedback.

- [ ] **Step 4: Add immutable run manifest + resume checks**

Record git commit, dataset hash, prompt hashes, schema hashes, registry hash, Lean version, Mathlib commit, Codex version, model, effort, retry budget, and timestamp. `slean-exp verify-run --run PATH` exits non-zero if any frozen input differs.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/runner.py src/slean_experiment/cli.py tests/test_runner.py
git commit -m "feat: orchestrate reproducible SleanIR benchmark runs"
```

---

### Task 10: Implement Semantic Evaluation, Metrics, and the Pre-Registered Decision Rule

**Files:**
- Create: `src/slean_experiment/evaluator.py`
- Create: `src/slean_experiment/metrics.py`
- Test: `tests/test_evaluator.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- `evaluate(item, run, lean) -> Evaluation`
- `Evaluation.semantic_status`: `match | mismatch | unresolved | clarification_correct | clarification_wrong`
- `summarize(evaluations) -> BenchmarkMetrics`
- `winner(metrics_by_candidate) -> Decision`

- [ ] **Step 1: Test exact, equivalent, wrong-direction, ambiguous, and type-error cases**

Include a reversed implication case and a correct `clarification_required` case.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_evaluator.py tests/test_metrics.py -v`

- [ ] **Step 3: Implement layered evaluation**

Order: outcome correctness -> generated Lean typecheck -> normalized exact/structural comparison -> Lean equivalence attempt -> unresolved. Primary scorer does not use LLM-as-judge.

- [ ] **Step 4: Implement metrics and literal keep/kill rule**

```python
if best_ir.faithfulness - direct.faithfulness >= 0.05:
    return Decision.KEEP_IR
if abs(best_ir.faithfulness - direct.faithfulness) <= 0.01 and best_ir.usage_burden <= 0.70 * direct.usage_burden:
    return Decision.KEEP_IR_EFFICIENCY
return Decision.REJECT_IR
```

Also report exact-match rate, canonicality distance, typecheck rate, first-try rate, attempts, latency, available token usage, output bytes, IR node count, ambiguity accuracy, false-statement faithfulness, and error categories.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/evaluator.py src/slean_experiment/metrics.py tests/test_evaluator.py tests/test_metrics.py
git commit -m "feat: score SleanIR semantic faithfulness"
```

---

### Task 11: Create the Exact 24-Item Slean Stress Set

**Files:**
- Create: `experiment/stress/stress.jsonl`
- Test: `tests/test_stress_set.py`

**Interfaces:**
- Uses `BenchmarkItem`.
- Ambiguous entries: `gold_outcome="clarification_required"`, no gold Lean statement, non-empty `ambiguity`.
- Clear false entries: `gold_outcome="formalization"` with a faithful Lean proposition.

- [ ] **Step 1: Add validation tests**

Assert unique IDs, all formalization golds typecheck, ambiguous items omit gold Lean, and all listed stress categories are present.

- [ ] **Step 2: Author exactly these 24 semantic cases**

```text
01 "7 is prime."
02 "Let p be prime."
03 "7 is a prime element of ℚ."
04 "7 is a prime natural number."
05 "Every even natural number is odd."
06 "If n² is even, then n is even."
07 "If n is even, then n² is even."
08 "Every continuous real-valued function on [a,b] is bounded."
09 "Every continuous function is bounded."
10 "There exists x such that x² = 2."
11 "There exists a real number x such that x² = 2."
12 "Every finite group of prime order is cyclic."
13 "For every real x there exists a real y such that y > x."
14 "There exists a real y such that for every real x, y > x."
15 "An integer n is even if and only if there exists an integer k with n = 2k."
16 "If A is a subset of B and B is a subset of C, then A is a subset of C."
17 "P is a prime ideal of the commutative ring R."
18 "Let V be a finite-dimensional vector space over a field F; V has a basis."
19 "Every compact subset of a Hausdorff topological space is closed."
20 "Every finite tree with at least two vertices has at least two leaves."
21 "For independent events A and B, P(A ∩ B) = P(A)P(B)."
22 "Every differentiable real function is continuous."
23 "Every group is abelian."
24 "For every x, y = x + 1."  (intentionally malformed: y is unbound)
```

Items 01 and 10 are Normal-vs-Exact interpretation stressors: in Exact evaluation they require clarification; a later Normal-policy experiment may score conventional inference separately. Item 24 requires clarification/error rather than inventing a binder.

- [ ] **Step 3: Write faithful Lean targets for all clear cases and typecheck**

For context-dependent cases, include explicit header variables/typeclasses in the benchmark item rather than weakening/changing the English meaning. Run `python -m pytest tests/test_stress_set.py -v` until all formalization golds typecheck.

- [ ] **Step 4: Record provenance**

Original authored stress rows use `source="slean_stress_v1"` and `license="CC0-1.0"`. If wording is copied/adapted from an external source, record source URL/license and do not label it CC0 unless permitted.

- [ ] **Step 5: Commit**

```bash
git add experiment/stress/stress.jsonl tests/test_stress_set.py
git commit -m "test: add Slean semantic stress set"
```

---

### Task 12: Add Reporting and Run a 20-Item Pilot Before Spending Significant Luna Usage

**Files:**
- Create: `src/slean_experiment/report.py`
- Modify: `src/slean_experiment/cli.py`
- Test: `tests/test_metrics.py`
- Generated: `runs/pilot-*`

**Interfaces:**
- `slean-exp run --benchmark PATH --candidates a,b,c,direct --limit N`
- `slean-exp evaluate --run PATH`
- `slean-exp report --run PATH`

- [ ] **Step 1: CLI smoke test with fake model runner**

Use eight fixture items; generated report must show all four paths, primary metric, ambiguity metric, and pre-registered threshold.

- [ ] **Step 2: Run all local tests before any quota-consuming calls**

```bash
python -m pytest -q
cd lean && lake build && cd ..
```

Expected: PASS.

- [ ] **Step 3: Build and run a 20-item pilot**

Create `runs/pilot-input.jsonl` from ten imported items and ten stress items. Run:

```bash
slean-exp run --benchmark runs/pilot-input.jsonl --candidates a,b,c,direct --limit 20
PILOT_DIR="$(find runs -maxdepth 1 -type d -name 'run-*' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
slean-exp evaluate --run "$PILOT_DIR"
slean-exp report --run "$PILOT_DIR"
```

This is 80 initial Luna calls plus only deterministic-validation repair calls.

- [ ] **Step 4: Apply stop/go gates**

Proceed only if runtime evidence confirms Luna Low, all four paths complete without systematic harness/schema failure, prompts contain no gold outputs, no SleanIR candidate is structurally incapable of multiple pilot items, and at least one path is well above obvious floor. Otherwise fix the harness/schema and repeat only the 20-item pilot.

- [ ] **Step 5: Commit code, not generated run artifacts**

```bash
git add src/slean_experiment/report.py src/slean_experiment/cli.py tests
git commit -m "feat: add SleanIR pilot reporting"
```

---

### Task 13: Run the Full Benchmark, Confirmation Subset, and Record the Architecture Decision

**Files:**
- Generated: `runs/run-*`
- Create after results: `docs/experiments/sleanir-v0-results.md`
- Create after results: `docs/decisions/0001-sleanir-v0.md`

**Interfaces:**
- Produces final decision: `ADOPT A | ADOPT B | ADOPT C | REVISE AND RETEST | REJECT SLEANIR`.

- [ ] **Step 1: Freeze the full benchmark snapshot**

Ingest all enabled trustworthy paired datasets plus `slean_stress_v1`. Write benchmark SHA-256 and provenance manifest. If source licenses prevent redistribution, commit only manifest/hash and regeneration instructions, not restricted rows.

- [ ] **Step 2: Run one generation per item/path with Luna Low**

```bash
slean-exp run --benchmark runs/frozen-benchmark.jsonl --candidates a,b,c,direct --max-repairs 2 --concurrency 1
```

Use resumable batches. Raise concurrency only after observing subscription limits; changing concurrency must not change model, effort, prompts, retry rules, or dataset.

- [ ] **Step 3: Evaluate and rank**

Generate overall, per-source, per-subject, per-structure, ambiguity, and false-statement metrics. Keep unresolved equivalence cases separate; do not convert them to matches through an LLM judge.

- [ ] **Step 4: Run confirmation repetitions**

Create a deterministic ~100-item subset stratified by source, subject, statement structure, and stress category. Rerun the best SleanIR path and direct control three times if subscription usage permits. Record variance and confidence intervals; if usage does not permit all repetitions, report the incomplete confirmation rather than changing the primary run.

- [ ] **Step 5: Write the result and decision documents**

`docs/decisions/0001-sleanir-v0.md` must contain concrete values for: direct semantic faithfulness; best IR faithfulness; absolute improvement; usage burden comparison; hard-gate failures; ambiguity accuracy; false-statement faithfulness; confirmation variance; and the exact reason the pre-registered rule yields the chosen decision.

Commit:

```bash
git add docs/experiments/sleanir-v0-results.md docs/decisions/0001-sleanir-v0.md experiment/manifests
git commit -m "docs: record SleanIR architecture experiment results"
```

No proof-layer or production SleanIR implementation starts before this decision is committed.

---

## Final Verification Before Declaring the Experiment Complete

Run:

```bash
python -m pytest -q
cd lean && lake build && cd ..
slean-exp verify-run --run "$(find runs -maxdepth 1 -type d -name 'run-*' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
git status --short
```

The final `verify-run` must confirm dataset hash, prompt hashes, schema hashes, registry hash, git commit, Lean version, Mathlib commit, model ID, reasoning effort, and retry budget against the run manifest. It exits non-zero on any mismatch.

The experiment is complete only when the decision record is committed and its conclusion follows the approved keep/kill criteria.