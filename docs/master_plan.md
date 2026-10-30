# AI Agent Research — Master Plan

> 9 autonomous agent projects for hard CS problems  
> Infinite compute budget · Zero local resources · All outputs pushed to this repo

---

## The Central Thesis

The hardest problems for agents aren't ones that need more knowledge — they need:
1. **Long-horizon coherence** (staying consistent over 100+ reasoning steps)
2. **Verifiable correctness** (an external oracle that can't be fooled)
3. **Safe action under uncertainty** (acting on a live system with irreversible consequences)

Infinite tokens help most on (1). Projects with strong external oracles (TLC, Alive2, Lean, GitHub CI) are the ones that actually work.

---

## Shared Infrastructure

All 9 projects share [`infra/`](../infra/):

| Component | Purpose |
|-----------|---------|
| `IterativeRefinementLoop` | Universal propose→evaluate→diagnose→refine cycle |
| `RunLogger` | Structured JSONL experiment tracking, resumable runs |
| `FormalOracleInterface` | Unified adapter: Lean 4, TLC, Z3, Alive2 |
| `CodebaseContextManager` | L0–L4 pyramid, LRU eviction, call graph tracing |
| `GitHubAgent` | Paginated GitHub API with rate-limit backoff |

**Build this before any individual project.** 4 weeks. Unlocks all 9.

---

## Project Feasibility Rankings

### 🟢 Start Here (results in 3 months)

**P7 — ML Reproducibility Auditing**
- Zero dependencies, publishable results in weeks
- Audited 6 landmark papers so far: scores range 2.0/10 (InstructGPT) to 6.5/10 (ResNet)
- Key finding: variance non-reporting is universal; LLM papers have structural reproducibility impossibility
- [Results](../projects/p7_reproducibility/results/)

**P1 — GitHub Issue Fixing**
- 25-signal scoring rubric with language-specific modifiers (CPython, Rust, C, Neovim, Django)
- Hard exclusion rules, duplicate detection via semantic embeddings
- [Issue scorer](../projects/p1_github_issue_fixing/issue_scorer.py)

**P9 — Recursive Self-Improving Agent**
- fix → adversarial-test → fix loop; converged Round 1 on all 3 programs
- Mutation scores: binary_search 85%, flatten 90%, lru_cache 92%
- [Loop results](../projects/p9_self_improving/loop_results/)

---

### 🟡 Mid-Tier (6 months, publishable)

**P5 — Program Synthesis**
- 3 algorithms synthesized with formal correctness proofs; 80/80 tests pass
- LIS (O(n log n) patience sort), min palindrome deletions (LCS reduction), histogram rectangle (monotonic stack)
- [Synthesized programs](../projects/p5_program_synthesis/synthesized/)

**P6 — Vulnerability Research**
- 3 critical advisories (CVSS 9.0–9.8): off-by-one, integer overflow, use-after-free
- Static detection methodology for each: source nodes, taint rules, false positive patterns
- [Advisories](../projects/p6_vuln_research/advisories/)

**P8 — Data Structure Design**
- 3 novel structures for specific workloads (Zipfian, time-series, sparse graph)
- Theoretical analysis with amortized complexity and cache-line behavior
- In progress

---

### 🔴 Long Bets (12 months, research frontier)

**P2 — Automated Theorem Proving (Lean 4)**
- Proved: ∑_{k=0}^{n-1}(2k+1) = n² (induction + ring)
- Infrastructure: lean4/repl MCTS search, AND-OR tree, Mathlib grounding
- [Proof](../projects/p2_theorem_proving/sum_odd_proof.lean)

**P3 — LLVM Superoptimization**
- Discovered Pattern 1: `select(cond, add(x,C), x)` — confirmed miss in opt -O3
- Alive2 proof valid; FileCheck tests written; C++ pass skeleton ready
- [IR patterns](../projects/p3_llvm_superopt/patterns/)

**P4 — Distributed Protocol Verification**
- Cascade Consensus: novel CFT protocol differing from Raft on 2 axes
  - Decentralised commit authority (cascade relay)
  - EQC hash chain (self-validating log repair)
- Full TLA+ specification; safety invariants: Agreement, LogMatching, LeaderCompleteness, EpochUniqueness
- [TLA+ spec](../projects/p4_protocol_verification/CascadeConsensus.tla)

---

## Five Deepest Cross-Cutting Challenges

1. **The Formal Gap** — LLMs write plausible formal text but produce subtle errors; neurosymbolic hybrid execution needed (affects P2, P3, P4)
2. **Long-Horizon Coherence** — agents degrade over 100+ step chains; aggressive external state management mitigates (affects P1, P2, P4, P9)
3. **Correctness Without Execution** — 6/9 projects require reasoning about code correctness without running it; dual-model verification pattern is best mitigation
4. **Novelty vs. Rediscovery** — agents rediscover known results without adversarial novelty evaluation; hold-out protocol required (P3, P8)
5. **Safe Action Under Uncertainty** — P1 opens real PRs, P6 proposes security patches; explicit confidence threshold required before acting

---

## 12-Week Master Timeline

| Weeks | Focus | Projects |
|-------|-------|---------|
| 1–2 | Shared infrastructure | All |
| 3–4 | P7 audit pipeline | P7 |
| 5–6 | P1 issue scoring + reader agent | P1 |
| 7–8 | P1 PR submission + P9 adversarial loop | P1, P9 |
| 9–10 | P5 synthesis loop + P6 taint analysis | P5, P6 |
| 11 | P8 data structure design | P8 |
| 12 | P2/P3/P4 bootstrap infrastructure | P2, P3, P4 |

---

## Required APIs (all free, all remote)

| API | Projects |
|-----|---------|
| GitHub REST + GraphQL | P1, P9 |
| arXiv + Semantic Scholar | P7, P2, P3 |
| Papers With Code | P7 |
| Lean 4 REPL (`lean4/repl`) | P2 |
| TLC Model Checker | P4 |
| Z3 / CVC5 | P4, P5 |
| Alive2 | P3 |
| NVD / MITRE CVE API | P6 |

**Zero local GPU. Zero local compilation. All oracle calls are remote or open-source CLI.**
