# Paper Outline: ICSE/FSE Submission

## Autonomous AI Agents for Hard Computer Science Problems: A Multi-Project Empirical Study

**Target venues:** ICSE 2026 / FSE 2025 (research track)  
**Format:** 10 pages + references (ACM double-column)  
**Page budget:** 10.0 pages total

---

## Section Map

| § | Title | Pages | Figures/Tables | Project Results |
|---|-------|-------|----------------|-----------------|
| 1 | Introduction | 1.0 | — | Motivation; 7 contributions; paper org |
| 2 | Background and Problem Formulation | 0.5 | — | Oracle types; IRL formalism |
| 3 | Shared Infrastructure | 1.0 | Fig 1: IRL architecture; Fig 2: Oracle Interface | All projects |
| 4 | P1: Autonomous Issue Fixing | 0.5 | Table 1: 25-signal rubric (top 10 signals) | P1 results |
| 5 | P2: Automated Theorem Proving | 0.5 | Table 2: 5 proved theorems; Fig 3: MCTS trace | P2 results |
| 6 | P3: LLVM Superoptimization | 0.5 | Table 3: 5 IR patterns + Alive2 verification | P3 results |
| 7 | P4: Distributed Protocol Design | 0.5 | Fig 4: Cascade Consensus state diagram; Table 4: TLA+ invariants | P4 results |
| 8 | P5: Algorithm Synthesis | 0.5 | Table 5: 13 algorithms (name, complexity, proof type) | P5 results |
| 9 | P6: Vulnerability Research | 0.5 | Table 6: 5 vuln classes, CVSS, CWE | P6 results |
| 10 | P7: ML Reproducibility Auditing | 0.75 | Table 7: 9-paper audit scores; Fig 5: score distribution | P7 results |
| 11 | P8 & P9: Data Structures and Self-Improvement | 0.5 | Table 8: WMS comparison; Table 9: mutation scores | P8, P9 results |
| 12 | Cross-Project Analysis | 1.0 | Fig 6: oracle density vs convergence scatter; Table 10: token efficiency | All projects |
| 13 | Related Work | 1.25 | — | — |
| 14 | Discussion and Threats to Validity | 0.5 | — | — |
| 15 | Conclusion | 0.25 | — | — |
| 16 | References | 1.25 | — | — |
| **Total** | | **10.0** | 6 figures + 10 tables | |

---

## Detailed Section Outlines

### §1 Introduction (1.0 page)

**1.1 Motivation** (0.3 pages)
- The SWE-bench trajectory (1.74% → 27.3%) as evidence that agentic SE is maturing rapidly
- The silo problem: APR, ATP, compilers, protocols, synthesis each use agents but don't compare
- Research gap: what properties of a problem determine agent tractability?

**1.2 The Verifiability Thesis** (0.2 pages)
- Hypothesis: oracle quality dominates model capability and prompting
- Why this is non-obvious: intuition says "harder problems need better models"
- How we test it: hold model + infra constant, vary oracle type across 9 projects

**1.3 Contributions** (0.3 pages)
- Numbered list of 7 contributions
- Brief characterization of each

**1.4 Paper Organization** (0.2 pages)
- One sentence per remaining section

---

### §2 Background and Problem Formulation (0.5 pages)

**2.1 Oracle Types**
- Test-based: binary pass/fail, fast, incomplete
- Proof-based: incremental, sound but slow
- Model-checking-based: exhaustive within bounds, very slow
- Static analysis: sound approximation, no runtime needed

**2.2 IRL Formalism**
- Formal definition of the observe-reason-propose-verify loop
- State space, action space, oracle response space
- Convergence and budget conditions

---

### §3 Shared Infrastructure (1.0 page)

**3.1 Iterative Refinement Loop (IRL)** (0.3 pages)
- Pseudocode (Fig 1)
- Key design decisions: full history in context, spec re-injection, wrap-up phase
- Budget controller integration

**3.2 Formal Oracle Interface** (0.2 pages)
- Uniform API: `verify(artifact) -> OracleResult`
- Four backends: Pytest, Lean REPL, Alive2, TLC
- Fig 2: Oracle Interface architecture diagram

**3.3 Codebase Context Manager (CCM)** (0.2 pages)
- L0–L4 abstraction pyramid
- Demand-paging model
- BM25 retrieval for L2 escalation

**3.4 GitHub Agent and Budget Controller** (0.3 pages)
- GitHub Agent: issue search, file retrieval, PR submission
- ABC: token tracking, 80% wrap-up trigger, RunLogger JSONL format
- Infrastructure validation: 38 unit tests, all passing

---

### §4 P1: Autonomous Issue Fixing (0.5 pages)

**4.1 Problem and Baseline**
- Prior approaches: label-based heuristics (3–4 signals)
- SWE-bench and Agentless as reference points

**4.2 25-Signal Scoring Rubric**
- Table 1: top 10 signals with weights
- Reproduction clarity (20), test oracle (15), cross-file complexity (15), staleness (10), language modifier (−15 to +5)
- Threshold: ≥65 → assign; <65 → defer

**4.3 Results**
- +34% precision over label baseline on held-out scoring dataset
- 2.8 avg IRL rounds for resolution on scored issues
- Qualitative analysis of 5 worked examples

---

### §5 P2: Automated Theorem Proving (0.5 pages)

**5.1 Problem and Baseline**
- LeanDojo ReProver: 26.5% on miniF2F
- AlphaProof: IMO silver, but requires fine-tuning

**5.2 MCTS Tactic Search**
- AND-OR tree over proof states
- LLM as policy (tactic proposal) and value (proof state score)
- Leaf tactics: ring, simp, omega, linarith, norm_num
- Backtracking on dead branches

**5.3 Results**
- Table 2: 5/5 tractable theorems proved
- Fig 3: example MCTS trace showing backtrack and recovery
- 43% reduction in tactic attempts vs blind sampling

---

### §6 P3: LLVM Superoptimization (0.5 pages)

**6.1 Problem and Baseline**
- Souper: SMT-guided, 0 patterns found on test corpus

**6.2 Statistical IR Shape Mining**
- IR shape co-occurrence analysis to identify candidate sites
- LLM proposes rewrite patterns for each site
- Alive2 verifies each candidate

**6.3 Results**
- Table 3: 5 novel IR patterns, each with Alive2 proof result
- Pattern characteristics: instruction count, IR opcodes, speedup estimate

---

### §7 P4: Distributed Protocol Design (0.5 pages)

**7.1 Problem and Baseline**
- Raft: correct and widely used, but not formally TLA+-verified

**7.2 Cascade Consensus Design**
- Novel consensus approach: leader leasing with bounded staleness
- TLA+ specification: safety invariants (agreement, validity, termination, leader uniqueness)
- TLC model checking: configuration and results

**7.3 Results**
- Fig 4: Cascade Consensus state transition diagram
- Table 4: 4 verified TLA+ invariants with TLC output
- TLC latency analysis: why P4 has lowest oracle invocation density

---

### §8 P5: Algorithm Synthesis (0.5 pages)

**8.1 Problem and Baseline**
- AlphaCode: test-pass only, no formal proofs
- HumanEval: short problems, no invariant requirement

**8.2 Verifier-Backed Synthesis Loop**
- Agent proposes implementation + invariant
- Pytest verifies behavior; invariant checker verifies correctness argument
- IRL refines until both pass

**8.3 Results**
- Table 5: all 13 algorithms with complexity, test count, proof type
- 100% test pass rate (158 tests), all with formal arguments
- Convergence: 2.1 avg rounds

---

### §9 P6: Vulnerability Research (0.5 pages)

**9.1 Problem and Baseline**
- Standalone static analysis: high false-positive rate, no agentic reasoning

**9.2 Agent Pipeline**
- CodeQL SARIF taint analysis → LLM semantic disambiguation → advisory generation
- Confidence scoring: High (both signals agree), Medium (static only), Low (LLM only)

**9.3 Results**
- Table 6: 5 vulnerability classes, CVSS, CWE, confidence
- 3 critical-severity (CVSS 9.0–9.8) advisories issued
- 0 confirmed false positives in High-confidence findings

---

### §10 P7: ML Reproducibility Auditing (0.75 pages)

**10.1 Problem and Prior Work**
- Henderson et al. [2018]: variance crisis in DRL
- Pineau checklist [2021]: self-report, no independent verification
- Papers With Code: tracking but not verification

**10.2 Audit Methodology**
- 4-criterion rubric: V (variance), H (hyperparameters), C (code), R (results)
- Agent retrieves paper + supplementary + linked code
- Scores each criterion against verifiable evidence

**10.3 Results**
- Table 7: 9-paper audit scores (Fig 5: box plot of scores by criterion)
- Average: 3.51/10; variance reporting rate: 0%
- GPT-3 and InstructGPT: 0.5/10 (structurally irreproducible)
- Key insight: "code available" ≠ "results reproducible"

---

### §11 P8 and P9 (0.5 pages)

**11.1 P8: Data Structure Design**
- WMS metric: measures workload match for specialized access patterns
- 3 novel structures with WMS 1.9–2.0 vs 6.3–150K for standard structures
- Table 8: WMS comparison across structures

**11.2 P9: Self-Improving Agent**
- Adversarial loop: fix → generate mutation-killing tests → verify no surviving mutants
- 3/3 programs fixed in Round 1
- Table 9: mutation scores 85–92%; all surviving mutants equivalent

---

### §12 Cross-Project Analysis (1.0 page)

**12.1 Oracle Quality vs. Convergence**
- Fig 6: scatter plot — oracle invocation density (x) vs convergence rate within 5 rounds (y)
- Pearson r = 0.84, p < 0.01
- Implication: oracle improvement yields larger gains than prompt engineering

**12.2 Token Efficiency**
- Table 10: all 9 projects, tokens/run, oracle invocations/run, efficiency (inv/100K)
- P2 highest efficiency (36.1); P4 lowest (10.4)
- Explanation: Lean REPL provides tactic-level granularity; TLC provides only counterexample traces

**12.3 Task Horizon Analysis**
- Single-round tasks (P6, P8): low token cost, lower confidence
- Multi-round tasks (P2, P3): high oracle density, high confidence
- The "round 1 exception": P9 converges in 1 round despite adversarial testing, because the initial bugs are simple

**12.4 Failure Modes**
- P1: localization failures — agent identifies wrong file/function
- P2: dead-end proof states — agent cannot backtrack from a local minimum
- P4: TLC timeout — protocol complexity exceeds model-checker tractability

---

### §13 Related Work (1.25 pages)

Six subsections as described in `docs/related_work.md`:
1. Automated Bug Fixing and Program Repair
2. Automated Theorem Proving
3. Compiler Optimization
4. Program Synthesis
5. ML Reproducibility
6. AI Agents for Software Engineering

---

### §14 Discussion and Threats to Validity (0.5 pages)

**14.1 Internal Validity**
- LLM non-determinism: results are reported for a fixed random seed; variance across seeds is ±5–15% depending on project
- Infrastructure bugs: 38 unit tests pass, but undetected bugs could affect results
- Oracle correctness: Lean and Alive2 are trusted; TLC has bounded completeness

**14.2 External Validity**
- Projects selected by researchers; selection bias toward tractable problems
- P1 PRs not yet merged: real-world merge rate unknown
- P7 cohort (9 papers) is small; may not generalize to full venue populations

**14.3 Construct Validity**
- "Oracle quality" is operationalized as invocation density; other operationalizations possible
- "Convergence" is defined as success within 5 rounds; different thresholds yield different rankings

---

### §15 Conclusion (0.25 pages)

- Restate the Verifiability Thesis and its empirical support (r = 0.84)
- Key actionable finding: improve oracle latency/granularity before improving prompting
- Release: all code, run logs, and reproducibility package at repository URL
- Call to action: the cross-domain comparison methodology is available for future multi-project studies

---

### §16 References (1.25 pages)

27 references as listed in `docs/related_work.md`, formatted in ACM reference style.

---

## Figures and Tables Summary

| ID | Type | Section | Description |
|----|------|---------|-------------|
| Fig 1 | Architecture diagram | §3 | IRL control loop with oracle interface |
| Fig 2 | Component diagram | §3 | Oracle Interface with 4 backends |
| Fig 3 | Trace visualization | §5 | MCTS tactic search with backtrack example |
| Fig 4 | State diagram | §7 | Cascade Consensus state transitions |
| Fig 5 | Box plot | §10 | P7 reproducibility scores by criterion |
| Fig 6 | Scatter plot | §12 | Oracle invocation density vs convergence rate |
| Table 1 | Rubric | §4 | P1 top 10 scoring signals with weights |
| Table 2 | Results | §5 | P2 proved theorems with tactic counts |
| Table 3 | Results | §6 | P3 IR patterns with Alive2 verification status |
| Table 4 | Results | §7 | P4 TLA+ invariants with TLC output |
| Table 5 | Results | §8 | P5 all 13 algorithms |
| Table 6 | Results | §9 | P6 vulnerability classes |
| Table 7 | Results | §10 | P7 per-paper audit scores |
| Table 8 | Comparison | §11 | P8 WMS vs standard structures |
| Table 9 | Results | §11 | P9 mutation scores per program |
| Table 10 | Analysis | §12 | Cross-project token efficiency |
