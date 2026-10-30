# AI Agent Research Agenda

**9 autonomous agent projects for hard computer science problems — infinite compute, zero local resources.**

## Projects

| ID | Project | Status |
|----|---------|--------|
| P1 | [Autonomous GitHub Issue Fixing](projects/p1_github_issue_fixing/) | 🟡 Active |
| P2 | [Automated Theorem Proving (Lean 4)](projects/p2_theorem_proving/) | 🟡 Active |
| P3 | [LLVM Superoptimization](projects/p3_llvm_superopt/) | 🟡 Active |
| P4 | [Distributed Protocol Design & Verification](projects/p4_protocol_verification/) | 🟡 Active |
| P5 | [Program Synthesis from Natural Language](projects/p5_program_synthesis/) | 🟡 Active |
| P6 | [Autonomous Vulnerability Research](projects/p6_vuln_research/) | 🟡 Active |
| P7 | [ML Paper Reproducibility Auditing](projects/p7_reproducibility/) | 🟢 Results |
| P8 | [Novel Data Structure Design](projects/p8_data_structures/) | 🟡 Active |
| P9 | [Recursive Self-Improving Agent](projects/p9_self_improving/) | 🟡 Active |

## Architecture

All 9 projects share a common infrastructure layer in [`infra/`](infra/):

- **`IterativeRefinementLoop`** — universal propose → evaluate → diagnose → refine cycle
- **`RunLogger`** — structured experiment tracking with resumable runs
- **`FormalOracleInterface`** — unified adapter for Lean 4, TLC, Z3, Alive2
- **`CodebaseContextManager`** — L0–L4 pyramid for large codebase navigation
- **`GitHubAgent`** — GitHub API wrapper with rate limiting

## Quick Start

```bash
pip install -e .
cp config.yaml config.local.yaml  # edit with your API keys
python main.py --config config.local.yaml
```

## Research Output

- [Master Plan](docs/master_plan.md)
- [ML Reproducibility Audit Results](projects/p7_reproducibility/results/)
- [Issue Selection Algorithm](projects/p1_github_issue_fixing/issue_scorer.py)
- [Cascade Consensus Protocol (TLA+)](projects/p4_protocol_verification/CascadeConsensus.tla)
- [Program Synthesis Results](projects/p5_program_synthesis/synthesized/)
- [Vulnerability Analysis](projects/p6_vuln_research/advisories/)
- [LLVM IR Pattern Analysis](projects/p3_llvm_superopt/patterns/)
- [Self-Improving Agent Loop Results](projects/p9_self_improving/loop_results/)

## License

MIT
