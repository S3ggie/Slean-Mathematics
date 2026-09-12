# SleanIR Core Design Experiment

Date: 2026-09-11
Status: Design approved for experiment; no permanent SleanIR schema selected yet.

## 1. Purpose

Slean needs to translate a human mathematical statement into a faithful Lean theorem statement. The central research question is whether an intermediate representation (SleanIR) materially improves that translation compared with direct natural-language-to-Lean generation.

SleanIR is not assumed to be necessary. It must earn its complexity experimentally.

The experiment therefore compares three candidate SleanIR designs against a direct NL -> Lean control using the same model, statements, retry rules, Lean/Mathlib environment, and evaluation pipeline.

## 2. Scope

SleanIR v0 is limited to **mathematical statements**. It does not represent proofs, proof steps, tactics, lessons, tutoring dialogue, user accounts, curriculum, or solution generation.

The core should be designed so a future proof layer can reuse the same expression, symbol, typing, and provenance machinery rather than replacing it.

The experiment includes:

- clear true statements;
- clear false statements, which must be formalized faithfully rather than corrected;
- ambiguous statements, for which the correct behavior is to request clarification when meaning-changing ambiguity cannot be safely resolved;
- ordinary K-12 and undergraduate mathematics;
- graduate/research-level and niche mathematics;
- minimal pairs where a small wording change produces a different formal statement.

## 3. Architecture under test

### 3.1 Common pipeline

For SleanIR candidates:

`natural-language statement -> LLM -> candidate SleanIR -> deterministic validation -> deterministic compiler -> Lean`

For the control:

`natural-language statement -> LLM -> Lean`

The single semantic-generation boundary in the SleanIR architecture is **human math -> SleanIR**. Once an SleanIR document is accepted, all translation into Lean must be deterministic. No LLM may reinterpret, simplify, repair, or change the mathematical meaning between SleanIR and Lean.

A later semantic-auditor model may be evaluated as a watchdog, but it may only flag suspected problems. It may not rewrite the accepted SleanIR or be part of the deterministic compiler.

### 3.2 Common result envelope

Every path must return one of two top-level outcomes:

- `formalization` - the system believes the statement is sufficiently resolved to formalize;
- `clarification_required` - one or more unresolved meaning-changing ambiguities remain.

For A/B/C, `formalization` contains the candidate SleanIR document. For D, it contains the Lean theorem statement directly. `clarification_required` must identify the unresolved issue without guessing a formal meaning.

This common outcome contract ensures ambiguity behavior is comparable across all four paths.

### 3.3 Common artifact metadata

All candidate SleanIR documents must support metadata recording:

- SleanIR schema version;
- Slean Math Registry version;
- Lean version;
- pinned Mathlib commit/revision;
- source statement identifier;
- source provenance spans for important semantic nodes.

Provenance metadata does not alter mathematical meaning.

## 4. Candidate core designs

All candidates use stable registry IDs for mathematical concepts. Human words such as `prime` never serve as the permanent semantic identity of a concept.

### Candidate A: ultra-minimal

Expression forms:

- `var` - reference to a bound variable;
- `literal` - numeric/string-like literal supported by the formal target;
- `symbol` - stable registry concept ID;
- `apply` - apply a head expression to zero or more arguments;
- `bind` - bind one or more typed variables under a binder symbol and body.

Logical concepts such as `forall`, `exists`, `and`, `or`, `not`, `implies`, and equality are represented through registry symbols used by `apply`/`bind` rather than dedicated node kinds.

### Candidate B: small but scope-explicit

Expression forms:

- `var`;
- `literal`;
- `symbol`;
- `apply`;
- `bind` for generic binders;
- `forall` with explicitly typed bound variables and body;
- `exists` with explicitly typed bound variables and body.

Other logical operators remain registry symbols expressed through `apply`.

The purpose of B is to test whether making the most important scoping constructs explicit substantially improves model reliability without greatly increasing the core.

### Candidate C: human-shaped logic

Expression forms:

- `var`;
- `literal`;
- `symbol`;
- `apply`;
- `bind` as a generic fallback for non-logical binders such as function abstraction or future binding constructs;
- `forall`;
- `exists`;
- `implies`;
- `and`;
- `or`;
- `not`;
- `equals`.

Mathematical subject vocabulary still remains in the registry. Candidate C only promotes common logical structure into dedicated nodes while retaining a generic binder so it does not lose expressive coverage.

### Candidate D: direct NL -> Lean control

The model receives the same natural-language statement and mathematical context but outputs a Lean theorem statement directly.

Candidate D establishes whether SleanIR is useful at all.

## 5. Slean Math Registry

### 5.1 Purpose

SleanIR Core is the grammar of mathematical meaning. The Math Registry is the expandable vocabulary.

The registry must be extensible by adding concepts, not by changing compiler code for every new area of mathematics.

### 5.2 Formal identity

Every distinct mathematical meaning receives its own stable Slean registry ID. Overloaded human phrases may map to multiple candidate IDs.

For example, the human alias `prime` may retrieve multiple concepts such as natural-number primality, a prime element in an algebraic structure, and prime ideals. The stored SleanIR identity must be the resolved concept ID rather than the raw human word.

### 5.3 Registry entry requirements

A registry entry must minimally contain:

- stable Slean concept ID;
- exact Lean/Mathlib declaration or deterministic formal target;
- type/signature information;
- required mathematical context/typeclass constraints;
- human-readable description;
- human aliases used for candidate retrieval;
- provenance showing the Mathlib/Lean source and version.

Human aliases retrieve candidates only. They do not determine meaning by themselves.

### 5.4 Source of truth

Mathlib is the primary formal source of truth. The registry should automatically index usable Mathlib declarations and types wherever practical. Slean maintains the thin human-language layer above that index: stable IDs, aliases, descriptions, and Slean-specific metadata.

A Mathlib upgrade creates a new registry/version snapshot rather than silently changing the meaning of existing SleanIR artifacts.

## 6. Interpretation and ambiguity policy

Interpretation is separate from registry lookup.

### 6.1 Normal interpretation policy

Normal mode may use a strong conventional mathematical interpretation when the context makes that interpretation overwhelmingly likely. The chosen interpretation must still be recorded internally and be inspectable.

### 6.2 Exact interpretation policy

Exact mode must resolve every meaning-changing ambiguity before certification. It asks the user only about unresolved attributes that could materially alter the formal statement.

### 6.3 Typed context

Context and types are first-class inputs to concept resolution. A numeral or mathematical term does not have one universal meaning independent of its ambient type or structure.

Resolution flow:

1. identify human phrase/concept;
2. retrieve candidate registry concepts through aliases;
3. filter candidates using types and mathematical context;
4. if exactly one viable interpretation remains, use it;
5. if multiple materially plausible interpretations remain, request clarification under the applicable interpretation policy;
6. if none apply, report that the statement cannot currently be resolved.

### 6.4 False statements

A clear false statement must be formalized faithfully. Slean must not silently repair the statement into a true or provable theorem.

## 7. Provenance and traceability

Important semantic nodes should optionally carry source spans pointing to the exact region of the human statement that produced them.

Example conceptual mapping:

- `natural number n` -> typed variable `n : Nat`;
- `n^2 is even` -> assumption node;
- `then n is even` -> conclusion node.

This supports debugging, Exact mode, UI inspection, benchmark analysis, and future training-data analysis.

## 8. Dataset strategy

### 8.1 Existing data first

The benchmark should ingest all trustworthy, legally usable natural-language/Lean statement pairs practical for the experiment, preferring audited Lean 4 datasets and corrected/frozen versions over older known-misformalized variants.

Priority sources include audited/corrected ProofNet-style data, miniF2F Lean 4 data, and other public paired datasets with sufficient provenance and licensing.

The ingestion process must:

- preserve the original informal statement;
- preserve the gold Lean statement;
- preserve required imports, headers, helper definitions, and local context;
- preserve dataset/source version and license metadata;
- compile/typecheck the gold statement in the experiment's pinned environment;
- deduplicate overlapping benchmark items;
- exclude or quarantine known-bad gold formalizations.

### 8.2 Slean-specific stress set

Existing paired datasets are supplemented with a smaller curated stress set covering:

- overloaded terminology;
- ambient-type traps;
- ambiguous statements where clarification is the correct outcome;
- clear false statements;
- intentionally malformed statements;
- minimal semantic pairs such as implication reversal;
- niche mathematical subjects underrepresented in existing datasets.

Ambiguous stress items must include a gold `clarification_required` label and the ambiguity that must be resolved. False stress items must include the faithful Lean statement even though that proposition may be unprovable.

### 8.3 Subject coverage

The combined benchmark should include examples from as many major areas as reasonably available, including arithmetic, algebra, geometry, trigonometry, calculus, linear algebra, logic/set theory, probability/statistics, discrete mathematics, number theory, real/complex analysis, differential equations, abstract algebra, topology, combinatorics, graph theory, differential geometry, category theory, functional analysis, and additional niche areas where source data exists.

Coverage should also vary statement structure: equality, inequality, implication, iff, nested quantification, existence, multiple assumptions, typed functions/spaces, overloaded notation, and deeply nested propositions.

## 9. Gold target and comparison

Existing benchmark Lean statements act as the canonical gold formalizations.

The evaluator must not rely on raw text equality alone. Comparison proceeds in layers:

1. parse/typecheck generated Lean;
2. normalize harmless syntactic differences and compare normalized structure;
3. check Lean definitional equality where applicable;
4. for proposition statements that differ structurally, attempt a symbolic/proof-based equivalence check (`P <-> Q`) using deterministic Lean tooling and approved automated tactics/checkers;
5. unresolved cases are flagged for deeper semantic review rather than automatically marked equivalent.

Because every candidate starts from the same source statement, canonical/structural closeness to the human-authored gold formalization is itself a useful metric. Wildly different but equivalent formulations are accepted if equivalence is established, but they score worse on canonicality.

LLM-as-judge is a last-resort analysis tool, not the primary correctness oracle.

## 10. Evaluation metrics

### 10.1 Hard gates

A SleanIR candidate must satisfy:

- **Representational coverage:** it can represent every accepted valid benchmark statement without modifying the core schema for individual mathematical concepts.
- **Deterministic compilation:** accepted IR always maps to Lean without semantic decisions by the compiler.
- **Compiler generality:** mathematical concepts are handled through registry data, not `if concept == ...` compiler branches.

A candidate that fails a hard gate cannot become SleanIR v0 regardless of model score.

### 10.2 Primary metric

**Semantic faithfulness:** percentage of final Lean outputs judged to represent the same proposition as the benchmark's gold Lean statement.

For ambiguous stress items, semantic success means correctly returning `clarification_required` rather than fabricating a formalization.

### 10.3 Secondary metrics

Record at least:

- exact/normalized structural match rate;
- canonicality/structural distance from gold;
- schema-valid rate;
- Lean parse/typecheck rate;
- first-try semantic success;
- attempts required until valid/correct;
- unrecovered failure rate;
- model input/output token usage where observable;
- wall-clock latency where observable;
- IR tree size/node count;
- output size;
- compiler code complexity and number of exceptions/special cases;
- error category and severity.

Error categories should include at least wrong domain/type, dropped assumption, added assumption, reversed implication, wrong quantifier, scope error, wrong registry concept, vacuous reformulation, silent correction of a false statement, and failure to request clarification for material ambiguity.

## 11. Winner and kill criteria

Direct NL -> Lean is the control. SleanIR is retained only if it earns its additional complexity.

Primary keep rule:

- the best SleanIR candidate must improve semantic faithfulness over direct NL -> Lean by **at least 5 absolute percentage points** on the primary benchmark.

Efficiency exception:

- a SleanIR candidate may still be retained if its semantic faithfulness is effectively comparable to direct NL -> Lean (target: within 1 absolute percentage point) while providing a major measurable efficiency benefit, such as roughly **30% or more reduction in model usage burden** (tokens, retries/calls, or another reproducible compute proxy).

If neither condition is met, SleanIR should be rejected and Slean should pursue direct NL -> Lean with validation/auditing instead.

The threshold is intentionally selected before results are observed.

## 12. Model-testing protocol

### 12.1 Primary model

The primary high-volume experiment uses **GPT-5.6 Luna at Low reasoning effort through Codex**, because the experiment must be practical under the project's available subscription/usage constraints.

The same model and reasoning setting is used across A, B, C, and D.

### 12.2 Fairness rules

For each benchmark item:

- same source statement;
- same mathematical context;
- same Lean/Mathlib environment;
- same access policy for registry/Mathlib lookup;
- prompts differ only where required by the output representation;
- gold Lean output is hidden from the model;
- first attempt is recorded as the main result;
- at most two repair attempts are allowed after deterministic validation/typechecking failures;
- attempts and repair feedback are logged.

The experiment records both first-try accuracy and final accuracy after the fixed repair budget.

### 12.3 Confirmation runs

The full benchmark initially uses one generation per item/path to control usage.

After ranking candidates, the top candidate(s) and direct control are rerun approximately three times on a representative subset of roughly 100 items, subject to available usage, to measure variance.

### 12.4 Stronger models

A stronger model is not required for the primary experiment. If Luna Low performs near floor across all candidate paths such that architectural conclusions are impossible, a stronger model may be used on a small representative subset as a sanity check rather than rerunning the entire benchmark.

## 13. Reproducibility

Every experiment run must record or pin:

- dataset snapshot and item IDs;
- candidate schema versions;
- registry snapshot;
- compiler version/commit;
- Lean version;
- Mathlib commit;
- prompts;
- model identifier and reasoning setting;
- retry/repair policy;
- evaluator version;
- run timestamp and random/non-deterministic settings when exposed.

Old experiment artifacts are never silently reinterpreted against newer registry or Mathlib versions.

## 14. What this experiment does not decide

This experiment does not select:

- the proof representation layer;
- proof-generation architecture;
- tutoring UI;
- Ask/Solve implementation details;
- Check My Work implementation details;
- user/account architecture;
- production deployment stack;
- MCP interface design.

Those depend on the result of the statement-formalization experiment.

## 15. Expected outcome

The experiment ends with one of three conclusions:

1. **One SleanIR candidate clearly wins** and becomes the basis for SleanIR v0.
2. **SleanIR helps, but the tested candidates expose design flaws**, so a revised candidate is justified by specific benchmark evidence and must be tested before adoption.
3. **Direct NL -> Lean wins or is effectively equivalent**, so SleanIR is removed from the architecture rather than maintained without measurable benefit.

The experiment is successful even if the conclusion is to kill SleanIR.