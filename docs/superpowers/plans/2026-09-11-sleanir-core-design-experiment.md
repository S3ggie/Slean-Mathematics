# SleanIR Core Design Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible experiment harness that compares three candidate SleanIR representations against direct natural-language-to-Lean generation using GPT-5.6 Luna at Low reasoning effort.

**Architecture:** Keep the experiment isolated from future production Slean code. Python owns schemas, dataset ingestion, orchestration, metrics, and reporting; a pinned Lean/Mathlib project owns parsing, typechecking, and equivalence checks. A Codex CLI adapter performs high-volume Luna Low generations. For candidates A/B/C, accepted SleanIR is compiled to Lean by deterministic code only.

**Tech Stack:** Python 3.12+, Pydantic 2, pytest, Hypothesis, Typer, Lean 4, Mathlib, Lake, Codex CLI (`gpt-5.6-luna`, Low reasoning).

**Spec:** `docs/superpowers/specs/2026-09-11-sleanir-core-design-experiment.md`

## Global Constraints

- SleanIR v0 in this experiment represents mathematical **statements only**.
- Candidate D is a direct NL -> Lean control and must always be tested alongside A/B/C.
- Primary high-volume model is **GPT-5.6 Luna at Low reasoning effort through Codex**.
- Accepted SleanIR -> Lean compilation is deterministic; no LLM may reinterpret accepted IR.
- Every path returns exactly one of `formalization` or `clarification_required`.
- Clear false statements are formalized faithfully; they are never silently corrected.
- Ambiguous statements must return `clarification_required` when meaning-changing ambiguity remains.
- Existing audited Lean statements are the canonical gold targets.
- Semantic faithfulness is the primary metric.
- SleanIR must beat direct NL -> Lean by at least **5 absolute percentage points** in semantic faithfulness, unless it stays within 1 point while reducing model usage burden by roughly **30% or more**.
- Gold outputs are never included in model prompts.
- Maximum repair budget is two retries after the initial attempt.
- Dataset, prompts, schemas, registry, Lean version, Mathlib commit, evaluator version, model, and reasoning setting must be recorded for every run.

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
│   │   ├── aliases.json
│   │   └── curated.json
│   ├── stress/
│   │   └── stress.jsonl
│   └── manifests/
│       └── datasets.json
├── lean/
│   ├── lakefile.toml
│   ├── lean-toolchain
│   └── SleanExperiment/
│       ├── Basic.lean
│       └── Inspect.lean
├── src/slean_experiment/
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
│   ├── report.py
│   └── cli.py
├── tests/
│   ├── test_schemas.py
│   ├── test_registry.py
│   ├── test_compiler.py
│   ├── test_lean.py
│   ├── test_datasets.py
│   ├── test_codex_runner.py
│   ├── test_runner.py
│   ├── test_evaluator.py
│   └── test_metrics.py
└── runs/                 # gitignored generated artifacts
```

The package is intentionally named `slean_experiment`, not `slean`, so none of these experimental APIs accidentally become production contracts.

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
- Test: `tests/test_lean.py`

**Interfaces:**
- Produces: Python package `slean_experiment` and a Lake project whose exact Lean/Mathlib revisions are committed in `lean-toolchain` and `lake-manifest.json` after `lake update`.
- Produces: `LeanEnvironment(root: Path)` in Task 5 will assume `lean/` is the Lake working directory.

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
dependencies = [
  "pydantic>=2.11,<3",
  "typer>=0.16,<1",
]

[project.optional-dependencies]
test = [
  "pytest>=8.4,<9",
  "hypothesis>=6.130,<7",
]

[project.scripts]
slean-exp = "slean_experiment.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# tests/test_lean.py
from pathlib import Path


def test_lean_project_exists() -> None:
    assert Path("lean/lakefile.toml").is_file()
    assert Path("lean/lean-toolchain").is_file()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_lean.py -v`

Expected: FAIL because `lean/lakefile.toml` and `lean/lean-toolchain` do not exist.

- [ ] **Step 3: Create the minimal Lean project**

```toml
# lean/lakefile.toml
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

Create `lean/lean-toolchain` initially by copying the exact toolchain required by the resolved Mathlib checkout, then run from `lean/`:

```bash
lake update
lake exe cache get
lake env lean --version
```

Commit the generated `lean/lake-manifest.json`. After this first successful resolution, replace `rev = "master"` in `lakefile.toml` with the exact Mathlib commit SHA recorded by the manifest, run `lake update` again, and verify the manifest is unchanged. This turns the first resolution into a permanent experiment pin.

```lean
-- lean/SleanExperiment/Basic.lean
import Mathlib

example : 2 + 2 = 4 := by norm_num
```

- [ ] **Step 4: Add ignore rules and verify both stacks**

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
cd lean && lake env lean SleanExperiment/Basic.lean
```

Expected: pytest PASS and Lean exits 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore experiment lean src tests/test_lean.py
git commit -m "chore: bootstrap SleanIR experiment harness"
```

---

### Task 2: Implement the Common Result Envelope and Candidate Schemas

**Files:**
- Create: `src/slean_experiment/models.py`
- Create: `src/slean_experiment/schemas.py`
- Create: `experiment/schemas/candidate_a.schema.json`
- Create: `experiment/schemas/candidate_b.schema.json`
- Create: `experiment/schemas/candidate_c.schema.json`
- Create: `experiment/schemas/direct.schema.json`
- Test: `tests/test_schemas.py`

**Interfaces:**
- Produces: `Candidate = Literal["a", "b", "c", "direct"]`
- Produces: `validate_result(candidate: Candidate, data: dict) -> FormalizationResult | ClarificationRequired`
- Produces: `write_json_schemas(output_dir: Path) -> None`
- All candidate expression objects include optional `source_span: {start:int,end:int}`.

- [ ] **Step 1: Write failing tests for the common outcome contract**

```python
# tests/test_schemas.py
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


def test_candidate_a_rejects_candidate_c_node() -> None:
    with pytest.raises(ValidationError):
        validate_result("a", {
            "outcome": "formalization",
            "ir": {"kind": "implies", "left": {}, "right": {}},
        })
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_schemas.py -v`

Expected: import failure because `slean_experiment.schemas` does not exist.

- [ ] **Step 3: Implement discriminated Pydantic models**

Implement shared nodes `SourceSpan`, `Var`, `LiteralExpr`, `Symbol`, `Apply`, `BinderVariable`, and `Bind`. Candidate B adds `Forall` and `Exists`. Candidate C adds `Forall`, `Exists`, `Implies`, `And`, `Or`, `Not`, `Equals`, while retaining `Bind`.

The public validator must be exactly:

```python
def validate_result(candidate: Candidate, data: dict[str, object]) -> Result:
    model = RESULT_MODELS[candidate]
    return model.model_validate(data)
```

Use Pydantic discriminators on `kind` and forbid extra keys (`ConfigDict(extra="forbid")`) so malformed output fails deterministically.

- [ ] **Step 4: Export schemas and verify round-trip validation**

Add:

```python
def write_json_schemas(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, model in RESULT_MODELS.items():
        (output_dir / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        )
```

Run:

```bash
python -c 'from pathlib import Path; from slean_experiment.schemas import write_json_schemas; write_json_schemas(Path("experiment/schemas"))'
python -m pytest tests/test_schemas.py -v
```

Expected: PASS and four deterministic JSON Schema files are written.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/models.py src/slean_experiment/schemas.py experiment/schemas tests/test_schemas.py
git commit -m "feat: define SleanIR experiment schemas"
```

---

### Task 3: Build the Typed Math Registry Contract

**Files:**
- Create: `src/slean_experiment/registry.py`
- Create: `experiment/registry/curated.json`
- Create: `experiment/registry/aliases.json`
- Test: `tests/test_registry.py`

**Interfaces:**
- Produces: `RegistryEntry(id, lean_name, lean_type, constraints, description, aliases, source)`
- Produces: `Registry.load(curated_path, aliases_path) -> Registry`
- Produces: `Registry.get(id: str) -> RegistryEntry`
- Produces: `Registry.lookup_alias(text: str) -> list[RegistryEntry]`
- Compiler consumers use `lean_name` only after an exact stable ID is present in SleanIR.

- [ ] **Step 1: Write tests proving overloaded aliases remain separate meanings**

```python
# tests/test_registry.py
from pathlib import Path
from slean_experiment.registry import Registry


def test_prime_alias_returns_multiple_meanings() -> None:
    r = Registry.load(
        Path("experiment/registry/curated.json"),
        Path("experiment/registry/aliases.json"),
    )
    ids = {entry.id for entry in r.lookup_alias("prime")}
    assert "number_theory.nat_prime" in ids
    assert "algebra.prime_element" in ids
    assert "ring_theory.prime_ideal" in ids


def test_stable_id_resolves_exact_lean_target() -> None:
    r = Registry.load(Path("experiment/registry/curated.json"), Path("experiment/registry/aliases.json"))
    assert r.get("number_theory.nat_prime").lean_name == "Nat.Prime"
```

- [ ] **Step 2: Verify tests fail**

Run: `python -m pytest tests/test_registry.py -v`

Expected: FAIL because registry implementation and fixture files do not exist.

- [ ] **Step 3: Implement registry models and initial curated fixture**

The initial curated registry must include at least these stable IDs because they exercise the core compiler independently of subject matter:

```text
core.nat                  -> Nat
core.int                  -> Int
core.rat                  -> Rat
core.real                 -> Real
logic.forall              -> binder forall
logic.exists              -> binder exists
logic.implies             -> implication
logic.and                 -> And
logic.or                  -> Or
logic.not                 -> Not
logic.equals              -> Eq
arithmetic.add            -> HAdd.hAdd
arithmetic.mul            -> HMul.hMul
arithmetic.pow            -> HPow.hPow
relation.lt               -> LT.lt
relation.le               -> LE.le
number_theory.even        -> Even
number_theory.odd         -> Odd
number_theory.nat_prime   -> Nat.Prime
algebra.prime_element     -> Prime
ring_theory.prime_ideal   -> Ideal.IsPrime
```

Each JSON entry must include `lean_type`, `constraints`, `description`, aliases, and a `source` object containing the pinned Mathlib commit from Task 1.

- [ ] **Step 4: Validate aliases and duplicate IDs at load time**

`Registry.load` must reject duplicate IDs, aliases pointing to missing IDs, and entries without a Lean target. Run:

`python -m pytest tests/test_registry.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/registry.py experiment/registry tests/test_registry.py
git commit -m "feat: add typed Slean math registry contract"
```

---

### Task 4: Implement Deterministic A/B/C -> Lean Compilation

**Files:**
- Create: `src/slean_experiment/compiler.py`
- Test: `tests/test_compiler.py`

**Interfaces:**
- Consumes: validated candidate A/B/C IR and `Registry`.
- Produces: `compile_ir(candidate: Literal["a","b","c"], ir: BaseModel, registry: Registry) -> str`
- Rule: compiler may only dispatch on IR node kind and registry metadata; it must never branch on domain concepts such as `Prime`, `Continuous`, `Compact`, etc.

- [ ] **Step 1: Write cross-candidate golden tests**

Use the same theorem meaning in all three representations:

```python
def test_all_candidates_compile_even_square_implication(registry):
    outputs = {
        c: compile_ir(c, make_even_square_fixture(c), registry)
        for c in ("a", "b", "c")
    }
    assert set(outputs.values()) == {"∀ n : Nat, Even (n ^ 2) → Even n"}
```

Also test that an unknown registry ID fails with `UnknownRegistryConcept` and that source-span metadata never changes the Lean output.

- [ ] **Step 2: Run tests and confirm failure**

Run: `python -m pytest tests/test_compiler.py -v`

Expected: FAIL because compiler does not exist.

- [ ] **Step 3: Implement a precedence-aware renderer**

Implement one recursive renderer per node family, sharing generic helpers. Registry-backed `symbol` nodes render `RegistryEntry.lean_name`; `apply` renders the head plus rendered arguments; binders render typed variables and body. Candidate C's dedicated logical nodes render canonical Lean syntax.

Do not add code such as:

```python
if symbol_id == "number_theory.nat_prime": ...
```

Such a branch is a test failure against the experiment's hard gate.

- [ ] **Step 4: Add a source-level anti-special-case test**

In `tests/test_compiler.py`, read `compiler.py` and assert that curated subject IDs like `number_theory.nat_prime` and `ring_theory.prime_ideal` never appear in compiler source. Then run:

`python -m pytest tests/test_compiler.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/compiler.py tests/test_compiler.py
git commit -m "feat: add deterministic SleanIR to Lean compilers"
```

---

### Task 5: Build the Lean Typecheck and Equivalence Harness

**Files:**
- Create: `src/slean_experiment/lean.py`
- Create: `lean/SleanExperiment/Inspect.lean`
- Test: `tests/test_lean.py`

**Interfaces:**
- Produces: `LeanResult(ok: bool, stdout: str, stderr: str, elapsed_ms: int)`
- Produces: `LeanEnvironment.typecheck(statement: str, header: str = "import Mathlib") -> LeanResult`
- Produces: `LeanEnvironment.equivalent(gold: str, generated: str, header: str = "import Mathlib") -> EquivalenceResult`
- `EquivalenceResult.status` is one of `exact`, `proved_equivalent`, `not_equivalent`, `unresolved`, `type_error`.

- [ ] **Step 1: Write tests for valid, invalid, and equivalent propositions**

```python
def test_typecheck_accepts_false_but_well_typed_statement(lean_env):
    result = lean_env.typecheck("∀ n : ℕ, Even n → Odd n")
    assert result.ok


def test_typecheck_rejects_type_error(lean_env):
    result = lean_env.typecheck("Nat.Prime (1 / 2 : ℚ)")
    assert not result.ok


def test_equivalence_proves_simple_rewrite(lean_env):
    result = lean_env.equivalent("∀ n : ℕ, n + 0 = n", "∀ n : ℕ, n = n")
    assert result.status in {"exact", "proved_equivalent"}
```

The first test is important: typechecking must never be confused with truth/provability.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/test_lean.py -v`

Expected: FAIL because `LeanEnvironment` is undefined.

- [ ] **Step 3: Implement isolated temporary Lean files**

For typechecking, generate:

```lean
import Mathlib

#check (show Prop from (STATEMENT))
```

For equivalence, first compare normalized exact strings. If different, generate a theorem:

```lean
import Mathlib

example : (GOLD) ↔ (GENERATED) := by
  aesop
```

If `aesop` fails, try one fixed second proof script `by simp_all` and then return `unresolved`. Do not add an LLM to equivalence checking.

Invoke Lean with `subprocess.run(["lake", "env", "lean", temp_file], cwd="lean", timeout=60, ...)`.

- [ ] **Step 4: Run tests and confirm reproducibility metadata**

Add methods returning `lake env lean --version` and the pinned Mathlib commit read from `lake-manifest.json`. Run all Lean tests.

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/lean.py lean/SleanExperiment/Inspect.lean tests/test_lean.py
git commit -m "feat: add Lean validation and equivalence harness"
```

---

### Task 6: Normalize External NL <-> Lean Datasets

**Files:**
- Create: `src/slean_experiment/datasets.py`
- Create: `experiment/manifests/datasets.json`
- Test: `tests/test_datasets.py`

**Interfaces:**
- Produces: `BenchmarkItem(id, source, informal_statement, gold_outcome, gold_lean_statement, header, helpers, subject, license, source_revision)`
- Produces: `load_benchmark(path: Path) -> list[BenchmarkItem]`
- Produces: `ingest_all(cache_dir: Path, output: Path, lean: LeanEnvironment) -> IngestReport`
- Any gold statement that fails pinned-environment typechecking is quarantined, never silently included.

- [ ] **Step 1: Write fixture-based ingestion tests**

Tests must cover ProofNet-style fields, miniF2F-style fields, deduplication, and quarantine of an invalid gold statement. Do not require network access in unit tests; store tiny source fixtures under `tests/fixtures/`.

- [ ] **Step 2: Run tests and confirm failure**

Run: `python -m pytest tests/test_datasets.py -v`

Expected: FAIL because adapters do not exist.

- [ ] **Step 3: Implement normalized benchmark record and adapters**

`experiment/manifests/datasets.json` records exact source URL, frozen git commit/tag, license, adapter name, and enabled/disabled state. The ingestion command clones/downloads into `.cache/datasets`, extracts only statement-level information, typechecks every gold Lean statement, and writes canonical JSONL sorted by `id`.

Do not duplicate copyrighted explanatory text beyond what is needed for the benchmark's licensed statement pairs and metadata.

- [ ] **Step 4: Run ingestion on fixture data, then one real source smoke sample**

Run:

```bash
python -m pytest tests/test_datasets.py -v
slean-exp ingest --limit-per-source 5 --output runs/smoke/benchmark.jsonl
```

Expected: fixture tests PASS; every accepted real item has a pinned source revision and a gold statement that typechecks.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/datasets.py experiment/manifests tests/fixtures tests/test_datasets.py
git commit -m "feat: normalize autoformalization benchmark datasets"
```

---

### Task 7: Add the Luna Low Codex Runner and Frozen Prompts

**Files:**
- Create: `src/slean_experiment/codex_runner.py`
- Create: `src/slean_experiment/prompts.py`
- Create: `experiment/prompts/common.md`
- Create: `experiment/prompts/candidate_a.md`
- Create: `experiment/prompts/candidate_b.md`
- Create: `experiment/prompts/candidate_c.md`
- Create: `experiment/prompts/direct.md`
- Test: `tests/test_codex_runner.py`

**Interfaces:**
- Produces: `CodexConfig(model="gpt-5.6-luna", reasoning_effort="low", timeout_s=180)`
- Produces: `CodexRunner.generate(prompt: str, schema_path: Path) -> Generation`
- `Generation` records raw output, parsed JSON, wall time, exit status, and any token/usage fields exposed by Codex events.
- Model invocation must use a fresh ephemeral turn per benchmark attempt.

- [ ] **Step 1: Write a subprocess-construction test**

```python
def test_codex_command_pins_luna_low(tmp_path):
    runner = CodexRunner(CodexConfig())
    cmd = runner.build_command(tmp_path / "schema.json")
    assert "gpt-5.6-luna" in cmd
    assert 'model_reasoning_effort="low"' in cmd
    assert "--output-schema" in cmd
    assert "--ephemeral" in cmd
```

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_codex_runner.py -v`

Expected: FAIL because runner is undefined.

- [ ] **Step 3: Implement Codex invocation**

Construct the command equivalent of:

```bash
codex exec \
  --ephemeral \
  --skip-git-repo-check \
  --sandbox read-only \
  --model gpt-5.6-luna \
  --config 'model_reasoning_effort="low"' \
  --output-schema experiment/schemas/a.schema.json \
  --experimental-json
```

Pass the prompt on stdin. Parse Codex JSON event lines and extract the final agent message. Run from an empty temporary directory so project instructions, source files, and gold data are not visible to the model. Disable web/MCP access for the benchmark generation turn unless a later experiment version explicitly gives every candidate the same lookup tools.

- [ ] **Step 4: Freeze prompt contract and add a live opt-in smoke test**

`common.md` must say, in substance and explicitly:

- translate the provided statement faithfully;
- do not prove it;
- do not correct false mathematics;
- do not add assumptions;
- if meaning-changing ambiguity remains, return `clarification_required`;
- output only the requested structured result.

Candidate-specific prompt files describe only their allowed representation. `direct.md` asks for the Lean theorem proposition, not a proof.

Unit tests mock subprocess. A manually invoked live check is:

```bash
slean-exp codex-smoke --candidate direct --statement 'For every natural number n, n = n.'
```

Expected: structured `formalization`, model metadata shows Luna Low, and no gold data is present in the temporary working directory.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/codex_runner.py src/slean_experiment/prompts.py experiment/prompts tests/test_codex_runner.py
git commit -m "feat: add reproducible Luna Low benchmark runner"
```

---

### Task 8: Implement Benchmark Orchestration and the Fixed Repair Budget

**Files:**
- Create: `src/slean_experiment/runner.py`
- Modify: `src/slean_experiment/cli.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Produces: `run_item(item: BenchmarkItem, candidate: Candidate, ...) -> ItemRun`
- Produces: `run_benchmark(items, candidates=("a","b","c","direct"), max_repairs=2) -> RunManifest`
- Every attempt is append-only JSONL under `runs/<run-id>/attempts.jsonl`.

- [ ] **Step 1: Write tests for fairness and retries**

Test that all four candidates receive identical `informal_statement` and context; none receives `gold_lean_statement`; an invalid first attempt receives at most two repair attempts; a valid first attempt is never retried.

- [ ] **Step 2: Confirm tests fail**

Run: `python -m pytest tests/test_runner.py -v`

- [ ] **Step 3: Implement orchestration**

For A/B/C: validate model JSON -> compile IR -> Lean typecheck. For direct: validate model JSON -> Lean typecheck. A schema/parse/typecheck failure may trigger a repair prompt containing only the model's previous output and deterministic error text. A semantic mismatch with gold **does not** trigger repair because the generation process must not see gold-derived feedback.

- [ ] **Step 4: Add resume-safe run manifests**

Manifest includes git commit, schemas' SHA-256 hashes, prompt hashes, registry hash, dataset hash, Lean version, Mathlib commit, Codex version, model, effort, max repairs, and run timestamp. On resume, reject changes to any frozen hash.

Run: `python -m pytest tests/test_runner.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/runner.py src/slean_experiment/cli.py tests/test_runner.py
git commit -m "feat: orchestrate fair SleanIR benchmark runs"
```

---

### Task 9: Implement Semantic Evaluation and Metrics

**Files:**
- Create: `src/slean_experiment/evaluator.py`
- Create: `src/slean_experiment/metrics.py`
- Test: `tests/test_evaluator.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Produces: `evaluate(item: BenchmarkItem, run: ItemRun, lean: LeanEnvironment) -> Evaluation`
- `Evaluation.semantic_status` is `match`, `mismatch`, `unresolved`, `clarification_correct`, or `clarification_wrong`.
- Produces: `summarize(evaluations: Iterable[Evaluation]) -> BenchmarkMetrics`
- Produces: `winner(metrics_by_candidate) -> Decision` implementing the pre-registered 5-point/30%-efficiency rule.

- [ ] **Step 1: Write evaluator tests**

Cover: exact match; whitespace/alpha-renaming normalization; proved equivalence; wrong implication direction; correct ambiguous clarification; incorrect clarification on a clear statement; generated type error.

- [ ] **Step 2: Verify failure**

Run: `python -m pytest tests/test_evaluator.py tests/test_metrics.py -v`

- [ ] **Step 3: Implement layered evaluation**

Evaluation order:

1. compare gold outcome vs generated outcome;
2. for `formalization`, require generated Lean to typecheck;
3. normalized structural/exact comparison;
4. Lean definitional/proof-based equivalence harness;
5. otherwise `unresolved` for manual/deeper review rather than pretending mismatch/equivalence.

Do not use an LLM judge in the primary scorer.

- [ ] **Step 4: Implement metrics and decision rule**

Compute semantic-faithfulness rate with unresolved cases reported separately, exact-match rate, typecheck rate, first-try rate, average attempts, output bytes, IR node count for A/B/C, latency, available token usage, and failure categories.

The decision code must literally encode:

```python
if best_ir.faithfulness - direct.faithfulness >= 0.05:
    return KEEP_IR
if abs(best_ir.faithfulness - direct.faithfulness) <= 0.01 and best_ir.usage_burden <= 0.70 * direct.usage_burden:
    return KEEP_IR_EFFICIENCY
return REJECT_IR
```

Run tests; expected PASS.

- [ ] **Step 5: Commit**

```bash
git add src/slean_experiment/evaluator.py src/slean_experiment/metrics.py tests/test_evaluator.py tests/test_metrics.py
git commit -m "feat: score SleanIR semantic faithfulness"
```

---

### Task 10: Create the Slean Stress Set

**Files:**
- Create: `experiment/stress/stress.jsonl`
- Test: `tests/test_stress_set.py`

**Interfaces:**
- Stress entries use the same `BenchmarkItem` model as imported datasets.
- Ambiguous entries have `gold_outcome="clarification_required"` and a concise `ambiguity` field.
- False-but-clear entries have `gold_outcome="formalization"` and a faithful Lean proposition.

- [ ] **Step 1: Add validation test**

Test that every stress item has a unique ID; every formalization gold typechecks; every ambiguous item has no gold Lean statement; each required category is represented.

- [ ] **Step 2: Create an initial 24-item stress set**

Include at minimum these semantic traps, each paired with a nearby unambiguous/minimal-pair case where useful:

```text
1. "7 is prime."                                  -> normal convention case
2. "Let p be prime."                              -> ambiguous without type/context
3. "7 is a prime element of ℚ."                   -> clear, false
4. "7 is a prime natural number."                 -> clear, true
5. "Every even natural number is odd."            -> clear, false; do not correct
6. "If n² is even, then n is even."               -> implication direction A
7. "If n is even, then n² is even."               -> implication direction B
8. "Every continuous function on [a,b] is bounded." -> typed analysis context
9. "Every continuous function is bounded."        -> ambiguous/false depending domain
10. "There exists x with x² = 2."                 -> missing ambient type
11. "There exists a real x with x² = 2."          -> resolved type
12. "Every finite group of prime order is cyclic." -> overloaded prime in cardinality context
```

Add twelve more covering nested quantifiers, iff, set membership, prime ideals, vector spaces, topology, graph theory, probability, functions with domain/codomain, and a malformed variable-scope statement.

- [ ] **Step 3: Typecheck all non-ambiguous gold statements**

Run: `python -m pytest tests/test_stress_set.py -v`

Expected: PASS.

- [ ] **Step 4: Record provenance and source status**

Mark each stress item as `source="slean_stress_v1"`, `license="CC0-1.0"` for original authored items, and record whether it is authored or adapted from a cited public theorem statement.

- [ ] **Step 5: Commit**

```bash
git add experiment/stress tests/test_stress_set.py
git commit -m "test: add Slean semantic stress benchmark"
```

---

### Task 11: Run a Small Pilot Before Spending Luna Usage

**Files:**
- Create: `src/slean_experiment/report.py`
- Modify: `src/slean_experiment/cli.py`
- Test: `tests/test_metrics.py`
- Generated: `runs/pilot-*/`

**Interfaces:**
- CLI: `slean-exp run --benchmark PATH --candidates a,b,c,direct --limit N`
- CLI: `slean-exp evaluate --run RUN_DIR`
- CLI: `slean-exp report --run RUN_DIR`

- [ ] **Step 1: Add CLI smoke tests with a fake model runner**

Use 8 fixture items and deterministic fake outputs. Verify the generated report contains all four candidates and the pre-registered decision threshold.

- [ ] **Step 2: Run the full local test suite before any paid/quota-consuming calls**

Run:

```bash
python -m pytest -q
cd lean && lake env lean SleanExperiment/Basic.lean
```

Expected: all tests PASS.

- [ ] **Step 3: Build a 20-item pilot benchmark**

Select 10 imported gold pairs + 10 stress items, stratified so all four paths see exactly the same IDs.

Run:

```bash
slean-exp run --benchmark runs/pilot-input.jsonl --candidates a,b,c,direct --limit 20
slean-exp evaluate --run runs/<pilot-run-id>
slean-exp report --run runs/<pilot-run-id>
```

This consumes 80 initial Luna calls plus retries only where deterministic validation fails.

- [ ] **Step 4: Apply a pilot stop/go check**

Proceed to full scale only if:

- Codex actually reports `gpt-5.6-luna` with Low effort;
- all four paths complete without runner/systematic schema failures;
- gold data never appears in prompts/logged model input;
- no candidate is structurally incapable of representing multiple pilot items;
- at least one path has enough successful formalizations that the experiment is not at obvious floor.

If any fail, fix harness/schema bugs and rerun the 20-item pilot; do not spend on the full benchmark.

- [ ] **Step 5: Commit code only, not run artifacts**

```bash
git add src/slean_experiment/report.py src/slean_experiment/cli.py tests
git commit -m "feat: add pilot benchmark reporting"
```

---

### Task 12: Run the Full Benchmark, Confirmation Subset, and Produce the Architecture Decision

**Files:**
- Generated: `runs/<full-run-id>/`
- Create after results: `docs/experiments/<run-id>-sleanir-results.md`
- Create after results: `docs/decisions/0001-sleanir-v0.md`

**Interfaces:**
- Consumes the fully frozen harness from Tasks 1-11.
- Produces an evidence-backed architectural decision: adopt candidate A/B/C, design a revised candidate and rerun, or reject SleanIR in favor of direct NL -> Lean.

- [ ] **Step 1: Freeze the benchmark snapshot**

Ingest every enabled trustworthy paired dataset plus `slean_stress_v1`; write the normalized JSONL and SHA-256 hash. Commit only the manifest/hash and legal/provenance metadata if dataset redistribution terms do not permit committing the rows themselves.

- [ ] **Step 2: Run one generation per item/path with Luna Low**

Use a resumable run and hourly-safe batching rather than launching uncontrolled parallel calls. Example:

```bash
slean-exp run --benchmark runs/frozen-benchmark.jsonl --candidates a,b,c,direct --max-repairs 2 --concurrency 1
```

Increase concurrency only after observing Codex subscription limits and without changing model/effort or retry policy.

- [ ] **Step 3: Evaluate and select finalists**

Run deterministic evaluation and generate per-subject/per-structure breakdowns. Any unresolved equivalence cases are listed separately; do not let an LLM silently convert them to successes.

- [ ] **Step 4: Run confirmation repetitions**

Create a deterministic representative subset of approximately 100 items stratified by source, subject, difficulty/structure, and stress category. Rerun the best SleanIR candidate and direct control three times on that subset, subject to available subscription usage. Record variance and confidence intervals.

- [ ] **Step 5: Write and commit the decision record**

`docs/decisions/0001-sleanir-v0.md` must contain:

```text
Decision: ADOPT A | ADOPT B | ADOPT C | REVISE AND RETEST | REJECT SLEANIR
Direct semantic faithfulness: ...
Best SleanIR semantic faithfulness: ...
Absolute improvement: ...
Usage burden comparison: ...
Hard-gate failures: ...
Ambiguity accuracy: ...
False-statement faithfulness: ...
Confirmation variance: ...
Reason decision follows the pre-registered rule: ...
```

No next Slean subsystem is implemented until this decision is recorded.

Commit:

```bash
git add docs/experiments docs/decisions experiment/manifests
git commit -m "docs: record SleanIR architecture experiment results"
```

---

## Final Verification Before Declaring the Experiment Complete

Run:

```bash
python -m pytest -q
cd lean && lake build
cd ..
git status --short
```

Then verify programmatically:

```bash
slean-exp verify-run --run runs/<full-run-id>
```

`verify-run` must confirm dataset hash, prompt hashes, schema hashes, registry hash, git commit, Lean version, Mathlib commit, model ID, reasoning effort, and retry budget against the run manifest. It exits non-zero on any mismatch.

The experiment is complete only when the decision record is committed and its conclusion follows the pre-registered keep/kill criteria from the approved spec.