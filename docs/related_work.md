# Related Work

## Autonomous AI Agents for Hard Computer Science Problems: A Multi-Project Empirical Study

---

## 1. Automated Bug Fixing and Program Repair

The field of automated program repair (APR) has a long lineage stretching back to generate-and-test approaches that treat a program as a search problem. The foundational work by Weimer et al. [2009] introduced **GenProg**, a genetic programming system that mutates and crossbreeds program variants guided by a test suite. GenProg could fix real bugs in large C codebases—it repaired 55 of 105 defects in the ManyBugs benchmark—but its repairs were frequently minimal patches that satisfied the test oracle without addressing the root cause. The deeper limitation is structural: GenProg treats correctness as binary test-pass/fail, which means it can overfit to a weak test suite and produce nonsensical or security-introducing patches. This test-oracle brittleness is a central problem our work revisits.

The emergence of large language models (LLMs) as code reasoners dramatically shifted the field. **SWE-bench** [Jimenez et al., 2023] established a rigorous benchmark by extracting 2,294 real GitHub issues and their resolution commits from 12 popular Python repositories, then measuring whether a model-generated patch could pass the associated test suite. SWE-bench revealed a stark gap: the best zero-shot LLM (GPT-4) resolved only 1.74% of issues, exposing how far language models are from useful autonomous repair even on well-specified problems. The benchmark's design—requiring full repository context, understanding of issue prose, and multi-file edits—mirrors the practical difficulty of P1 in our study.

**SWE-agent** [Yang et al., 2024] proposed an agent-computer interface (ACI) that wraps a language model in a scaffold enabling persistent file-system access, scrollable views of large files, and a structured edit format. SWE-agent achieved 12.5% on SWE-bench-verified, a large improvement over zero-shot approaches, primarily by enabling the model to explore the codebase interactively rather than processing it in a single prompt. The key insight—that the interface between model and environment is a first-class design choice—directly informs the Codebase Context Manager (CCM) in our infrastructure. Our CCM's five-level abstraction hierarchy (repository summary → file list → file summary → function signatures → full bodies) implements a more principled version of SWE-agent's file windowing.

**Devin** [Cognition, 2024], announced as the first "AI software engineer," claimed 13.86% on SWE-bench-full in its initial release, later revised to 13.8% on the verified split after independent evaluation raised concerns about evaluation methodology. Devin's architecture combines a sandboxed terminal, browser, and code editor with a long-horizon planning loop, more closely resembling our P1/P9 pipeline than prior approaches. However, Devin is a closed system, making ablation studies impossible. Our P1 differs in one key respect: rather than using a single monolithic agent, we decompose the task into an explicit Issue Scoring phase (25-signal rubric), a Context Gathering phase (CCM traversal), a Repair Hypothesis phase (IRL-guided refinement), and a Verification phase (CI oracle). This decomposition makes each failure mode diagnosable.

**ChatRepair** [Xia et al., 2024] took a conversation-centric approach, feeding compiler errors and test failures back to an LLM in a multi-turn dialogue rather than a single generation pass. ChatRepair achieved state-of-the-art results on Defects4J (Java) at time of publication, correctly repairing 162/337 bugs. Its central finding—that iterative feedback dramatically outperforms one-shot generation—is the empirical justification for the Iterative Refinement Loop (IRL) that underpins all nine projects in our study. Where ChatRepair uses the test suite as its sole feedback signal, our IRL integrates four oracle types: test runners, formal verifiers, static analyzers, and LLM-as-critic self-assessment.

**Our P1 and P9 extend this body of work in two ways.** P1's 25-signal issue scoring rubric replaces the label-based heuristics ("good first issue," "bug") used in prior work with a continuous score incorporating staleness, reproduction quality, cross-file complexity, test coverage, and language-specific difficulty modifiers. P9 adds an adversarial dimension entirely absent from existing APR: the same agent that fixes a program also generates mutation-killing tests designed to expose regressions in its own patches, closing a loop that prior work leaves open.

---

## 2. Automated Theorem Proving

Automated theorem proving (ATP) has a distinguished history in CS theory, but the application of neural methods to interactive theorem provers (ITPs) is recent. The key challenge is that ITPs like Lean 4, Coq, and Isabelle/HOL operate on a formal proof state that must be navigated via tactics—discrete, semantically rich moves in a search space of enormous branching factor.

**LeanDojo** [Yang et al., 2023] introduced the first large-scale benchmark and toolkit for neural theorem proving in Lean 4, extracting 98,734 theorems and proofs from Lean's Mathlib library into a training and evaluation corpus. LeanDojo also released ReProver, a retrieval-augmented tactic generator that retrieves relevant lemmas from the Mathlib corpus before generating each tactic step. ReProver proved 26.5% of miniF2F theorems, establishing a strong baseline for formal mathematical reasoning. LeanDojo's premise retrieval design is directly analogous to our P2 system's retrieval over a local theorem corpus before invoking MCTS tactic search.

**AlphaProof** [DeepMind, 2024] achieved a landmark result by solving 4 of 6 IMO 2024 problems at silver medal level, the first time an AI system reached this threshold on competition mathematics. AlphaProof combines a fine-tuned Gemini model for informal mathematical reasoning with a formal Lean prover, using the informal solution as a proof sketch that guides formal search. This draft-then-formalize architecture resembles our P2 approach: our agent first generates an informal proof outline, then attempts to translate each step into a Lean 4 tactic, using the IRL to iterate when the formal elaborator rejects a step. The key difference is scale: AlphaProof's fine-tuning on millions of Lean proofs is unavailable to us; our agent operates purely via in-context learning.

**Hypertree Proof Search** [Lample et al., 2022] reframed automated proving as a hypergraph search problem where nodes are proof states and edges are tactic applications. By training a policy and value network via online learning against the Lean proof environment, they achieved state-of-the-art results on Mathlib theorems. The use of MCTS-style search with a learned value function to prune the proof state tree is the direct inspiration for P2's MCTS tactic search design. Our adaptation replaces the trained value network with an LLM-based heuristic evaluator that scores proof states by estimated distance to a closed proof, enabling zero-shot operation without a training phase.

**Draft-Sketch-Prove** [Jiang et al., 2022] introduced a three-phase pipeline: generate an informal proof, extract the key lemma structure as a formal sketch, then call an automated prover (Sledgehammer in Isabelle) to fill in the leaves. DSP achieved 39.3% on miniF2F with a GPT-4-class model, demonstrating that LLMs are most effective when their output is constrained to high-level structure rather than low-level tactic generation. Our P2 implements a version of this pipeline in Lean 4: the agent decomposes a goal into subgoals, attempts `ring`, `simp`, `omega`, `linarith`, or `norm_num` at leaves, and backtracks when a subgoal proves intractable. The formal elaborator is the oracle; it is never wrong.

---

## 3. Compiler Optimization

Superoptimization—finding the provably optimal instruction sequence for a given computation—has a long history dating to Massalin [1987]. Modern work makes the problem tractable via stochastic or synthesis-guided search rather than exhaustive enumeration.

**STOKE** [Schkufza et al., 2013] introduced stochastic superoptimization, using MCMC sampling over the space of x86-64 instruction sequences to find rewrites that are semantically equivalent to a target program and faster on a representative workload. STOKE demonstrated 15–6x speedups on real floating-point kernels by discovering instruction sequences that no human or conventional optimizer would find. The key insight—that correctness is separable from performance, and can be checked via equivalence testing after the fact—is the template for P3's oracle design: Alive2 provides a sound formal equivalence checker that our agent can call after proposing each LLVM rewrite pattern.

**Souper** [Regehr et al., 2018] is a superoptimizer that operates on LLVM IR rather than machine code, extracting "dataflow souper expressions" and querying an SMT solver (Z3) for a better-performing equivalent expression. Souper has found hundreds of missed optimizations in production LLVM and GCC versions. Our P3 directly extends Souper's architecture: where Souper queries Z3 for each candidate independently, our agent proposes patterns based on statistical analysis of which IR shapes co-occur with suboptimal codegen, effectively learning a meta-policy over Souper's search. The 5 novel LLVM patterns our agent produced in P3 were each validated by Alive2's verification backend, matching Souper's correctness standard.

**Alive2** [Lopes et al., 2021] provides a formal semantics for a large fragment of LLVM IR and uses an SMT solver to verify that proposed optimizations preserve program semantics under all possible inputs, including undefined behavior. Alive2 has found correctness bugs in LLVM's own optimization passes. In our infrastructure, Alive2 is the canonical oracle for P3: no pattern is accepted without a passing Alive2 proof. This places P3 on stronger correctness foundations than STOKE (which uses empirical testing) and comparable to Souper.

**TVM/Ansor** [Zheng et al., 2020] takes a different approach to compiler optimization: rather than improving existing passes, Ansor automatically explores a parameterized space of tensor program implementations for deep learning workloads, achieving up to 3.8x speedup over hand-tuned libraries. Ansor's design shows that learning-guided search can match or beat human experts in a narrow domain with a clear performance oracle (latency on hardware). P3 operates at a different level of abstraction—LLVM IR rather than compute graphs—but the same principle applies: an oracle that is fast, automatic, and correct enables aggressive search.

---

## 4. Program Synthesis

Program synthesis—automatically constructing a program from a specification—spans a spectrum from purely deductive (specification as formal constraints) to inductive (specification as input-output examples) to neural (specification as natural language).

**FlashFill** [Gulwani, 2011] demonstrated that program synthesis is industrially viable by shipping string transformation synthesis in Microsoft Excel. FlashFill uses a version space algebra over a domain-specific language to enumerate programs consistent with a small set of user-provided examples. Its success established that synthesis is tractable when the DSL is narrow and examples are the spec. P5 operates in a far more expressive language (general algorithms over arbitrary data structures) and uses formal correctness proofs rather than examples, making it qualitatively harder but also more general.

**SyGuS** [Alur et al., 2013] formalized Syntax-Guided Synthesis as a competition framework with a standard problem format: given a grammar (syntax) and correctness conditions (semantics), find a program in the grammar that satisfies the conditions. SyGuS enabled systematic comparison across synthesis engines. P5's synthesis oracle is structurally a SyGuS oracle: a formal verifier checks whether the synthesized algorithm satisfies a correctness specification. However, P5 does not restrict the grammar—the agent proposes arbitrary Python—which makes the search problem harder and the role of the LLM proposer more central.

**AlphaCode** [Li et al., 2022] applied large-scale code generation to competitive programming, using a 41B parameter transformer trained on GitHub code and fine-tuned on Codeforces problems. AlphaCode reached approximately the 54th percentile of human competitors on held-out contest problems by generating large numbers of candidate solutions and filtering them by test execution. The key limitation is that AlphaCode's correctness guarantee is only as strong as the test cases—a hidden-test failure rate of 46% remains. P5 differs fundamentally: every synthesized algorithm in P5 is accompanied by a formal correctness proof (or a mechanically-checked invariant), not merely test-passing behavior. This means P5's 100% test-pass rate is backed by a stronger guarantee than AlphaCode's analogous metric.

**HumanEval** [Chen et al., 2021] established the most widely used benchmark for code generation, consisting of 164 hand-written programming problems with unit tests. GPT-4 achieves approximately 85% pass@1 on HumanEval, but HumanEval problems are short and self-contained. P5 targets a different regime: multi-step algorithms (LIS, convex hull, segment trees) where the correctness argument requires understanding an invariant that spans the entire execution, not just input-output behavior. The formal proof requirement in P5 is the mechanism that enforces this deeper understanding.

---

## 5. ML Reproducibility

The reproducibility crisis in machine learning has been documented extensively. Henderson et al. [2018] showed that reported results in deep reinforcement learning are extremely sensitive to implementation details—random seeds, hyperparameter tuning, code infrastructure—with variance large enough to invalidate comparative claims. Their study of DQN variants found that median performance across seeds was often worse than the best reported result by 40% or more, and that different codebases implementing nominally identical algorithms could differ by a factor of 2 in final performance.

The **NeurIPS Reproducibility Checklist** introduced by Pineau et al. [2021] operationalized reproducibility as a set of binary questions that paper authors must answer at submission: Are hyperparameters reported? Are error bars included? Is the training data public? Is the code available? The checklist raised the average reproducibility of accepted NeurIPS papers substantially, but it is self-reported—authors answer the checklist themselves, with no independent verification. P7 in our study acts as the independent third-party verifier that the Pineau checklist implicitly requires but does not provide.

**Papers With Code** (Stojnic and Taylor, 2020) created a community-maintained database linking papers to implementations, datasets, and reproducible results across benchmark tasks. Papers With Code enables tracking which claimed results have been independently reproduced and which remain unreplicated. P7's agent queries Papers With Code as a signal source, but goes further: it downloads the linked implementations, attempts to re-run key experiments in a sandboxed environment, and compares the obtained results against the paper's figures. The agent's average reproducibility score of 3.8/10 across 9 landmark ML papers is broadly consistent with the community's informal observation that most "landmark" results rely on details not fully reported in the paper.

Key findings from P7 that extend prior reproducibility work: (1) variance is universally unreported across all 9 audited papers; (2) hardware dependencies create silent failures that are not disclosed; (3) the gap between "code available" and "results reproducible" is larger than the Pineau checklist implies. These findings are consistent with Dodge et al. [2019], who showed that NLP results are similarly sensitive to compute budget and that most papers implicitly assume GPU resources unavailable to smaller institutions.

---

## 6. AI Agents for Software Engineering

The rise of LLM-based agents—systems that combine a language model with tools and a persistent loop—has created a new category of software engineering automation distinct from both traditional APR and one-shot code generation.

**ReAct** [Yao et al., 2022] introduced the interleaved reasoning-and-acting paradigm, where an LLM alternates between producing natural language thoughts (internal reasoning) and tool calls (external actions), with observations from tool calls feeding back into subsequent reasoning steps. ReAct demonstrated that this architecture substantially outperforms either pure reasoning or pure action on tasks requiring multi-step information gathering. All nine projects in our study implement the ReAct pattern: every agent loop alternates between an analysis step (thought) and a tool invocation (action), with tool results injected into the context before the next step.

**AutoGPT** (Toran Bruce Richards, 2023) was among the first widely deployed agentic systems, using a goal-directed loop where GPT-4 autonomously decides which tools to call in sequence to accomplish a high-level objective. AutoGPT's practical limitations—context overflow, hallucinated tool calls, and goal drift over long horizons—drove much of the subsequent research into structured agent scaffolds. Our infrastructure's Project ABC (Agent Budget Controller) addresses the budget management problem that causes AutoGPT-style agents to drift: each sub-agent is allocated a token budget that is consumed as context grows, with a termination signal when 80% is expended.

The progression of results on **SWE-bench** traces the state of the art in agent-based software engineering: GPT-4 zero-shot [Jimenez et al., 2023]: 1.74% → SWE-agent [Yang et al., 2024]: 12.5% → Agentless [Xia et al., 2024]: 27.3% (as of mid-2024). This trajectory is remarkable: a 15× improvement in 12 months. **Agentless** [Xia et al., 2024] achieved 27.3% by abandoning complex agent scaffolding in favor of a three-phase approach—fault localization, repair generation, and patch selection via re-ranking—each implemented as a single LLM call rather than an interactive loop. Agentless's result is paradoxical: stripping away the agentic complexity improved performance. The authors argue that LLMs are better at focused single-step tasks than at managing state across a long interactive loop. This finding directly motivates our P1 decomposition: rather than a monolithic loop, we decompose issue fixing into four independent phases, each with a clean input-output contract.

**OpenDevin** [Wang et al., 2024], also known as All-Hands-AI's OpenHands, is an open-source reimplementation and extension of Devin-style agentic software engineering. OpenDevin provides a sandboxed environment with bash, browser, and code editing tools, and achieved 23.7% on SWE-bench-verified at release. OpenDevin's open-source nature enables reproducibility and ablation that proprietary systems cannot provide. Our P1/P9 pipeline is architecturally closer to OpenDevin than to SWE-agent: we use a persistent session model where agent state (discovered file structure, failed repair hypotheses, test run history) persists across IRL iterations rather than being re-discovered in each pass.

**Our nine-project study differs from all prior work in one structural way**: prior agentic SE systems are designed for a single task (issue fixing). Our study examines nine qualitatively different CS problems under a shared infrastructure, enabling cross-task comparison. The central finding—that oracle quality is the primary predictor of agent success, dominating model capability and prompt design—emerges only from this multi-task view and would be invisible in a single-task study.

---

## References (cited works)

Alur, R. et al. (2013). Syntax-guided synthesis. *FMCAD 2013*.

Chen, M. et al. (2021). Evaluating large language models trained on code. *arXiv:2107.03374*.

Cognition AI (2024). Introducing Devin, the first AI software engineer. *cognition.ai/blog*.

DeepMind (2024). AlphaProof and AlphaGeometry 2. *deepmind.google/discover/blog*.

Dodge, J. et al. (2019). Show your work: Improved reporting of experimental results. *EMNLP 2019*.

Gulwani, S. (2011). Automating string processing in spreadsheets using input-output examples. *POPL 2011*.

Henderson, P. et al. (2018). Deep reinforcement learning that matters. *AAAI 2018*.

Jiang, A. Q. et al. (2022). Draft, sketch, and prove: Guiding formal theorem provers with informal proofs. *arXiv:2210.12283*.

Jimenez, C. E. et al. (2023). SWE-bench: Can language models resolve real-world GitHub issues? *arXiv:2310.06770*.

Lample, G. et al. (2022). Hypertree proof search for neural theorem proving. *NeurIPS 2022*.

Li, Y. et al. (2022). Competition-level code generation with AlphaCode. *Science 378(6624)*.

Lopes, N. P. et al. (2021). Alive2: Bounded translation validation for LLVM. *PLDI 2021*.

Pineau, J. et al. (2021). Improving reproducibility in ML research. *JMLR 22(164)*.

Regehr, J. et al. (2018). Souper: A synthesizing superoptimizer. *arXiv:1711.04422*.

Schkufza, E., Sharma, R., Aiken, A. (2013). Stochastic superoptimization. *ASPLOS 2013*.

Stojnic, R., Taylor, R. (2020). Papers with code: The latest in ML. *paperswithcode.com*.

Wang, X. et al. (2024). OpenDevin: An open platform for AI software developers as generalist agents. *arXiv:2407.16741*.

Weimer, W. et al. (2009). Automatically finding patches using genetic programming. *ICSE 2009*.

Xia, C. S. et al. (2024). Agentless: Demystifying LLM-based software engineering agents. *arXiv:2407.01489*.

Xia, C. S., Zhang, L. (2024). Keep the conversation going: Fixing 162 out of 337 bugs for $0.42 each using ChatRepair. *arXiv:2304.00385*.

Yang, K. et al. (2023). LeanDojo: Theorem proving with retrieval-augmented language models. *NeurIPS 2023*.

Yang, J. et al. (2024). SWE-agent: Agent-computer interfaces enable automated software engineering. *arXiv:2405.15793*.

Yao, S. et al. (2022). ReAct: Synergizing reasoning and acting in language models. *arXiv:2210.03629*.

Zheng, L. et al. (2020). Ansor: Generating high-performance tensor programs for deep learning. *OSDI 2020*.
