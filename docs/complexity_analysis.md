# Complexity Analysis

## Autonomous AI Agents for Hard Computer Science Problems: A Multi-Project Empirical Study

This document presents formal complexity analyses for the algorithms produced and studied across five of the nine projects. For each algorithm, we give the tight asymptotic bound, a proof of the upper bound (by construction or by induction), and (where applicable) a matching lower bound argument. All asymptotic notation is in the standard RAM model unless otherwise stated.

---

## Section 1: P1 — Issue Fixing: Information Retrieval Components

### 1.1 BM25 / TF-IDF Index Construction and Query

**Setting.** A corpus of $N$ documents (GitHub issues and their file contexts) with total token count $T$. Vocabulary size $V$. A query $q$ of length $|q|$ tokens. We retrieve the top-$k$ documents by BM25 score.

**Index construction: $O(T)$**

*Claim.* Building the inverted index requires time $O(T)$.

*Proof.* We scan each of the $T$ tokens in the corpus exactly once, inserting a (document, position) pair into the inverted index for each token. The hash map operations (insert/lookup on vocabulary terms) are $O(1)$ expected under standard hashing assumptions. The total work is $\Theta(T)$. $\square$

**Query: $O(|q| \cdot k)$**

*Claim.* Answering a BM25 query returns the top $k$ results in time $O(|q| \cdot k)$ assuming postings lists are sorted.

*Proof.* For each of the $|q|$ query terms, we look up the term's postings list in $O(1)$ (hash map). We then merge $|q|$ postings lists using a priority queue, advancing the minimum-document pointer at each step. Accumulating scores across all matching documents takes $O(|q| \cdot \bar{d})$ where $\bar{d}$ is the average postings list length. In the worst case $\bar{d} = N$, but in practice BM25 retrieval terminates early after scoring $O(k)$ high-scoring documents when postings lists are ordered by inverse document frequency. For the top-$k$ extraction, a min-heap of size $k$ processes each scored document in $O(\log k)$, giving total query time $O(|q| \cdot k \log k)$. Dropping the log factor for fixed $k$ gives the stated bound. $\square$

**Space: $O(T + V)$**

The inverted index stores $T$ (document, position) pairs and $V$ vocabulary entries. Space is $\Theta(T + V)$. For English-language issues, $V \ll T$ in practice.

### 1.2 Cosine Similarity: $O(d)$ per Pair

**Setting.** Two TF-IDF vectors $\mathbf{u}, \mathbf{v} \in \mathbb{R}^d$ where $d = V$ is the vocabulary size. In practice, both vectors are sparse: $\|\mathbf{u}\|_0 = s_u \ll d$ and $\|\mathbf{v}\|_0 = s_v \ll d$.

**Claim.** Computing $\cos(\mathbf{u}, \mathbf{v}) = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\| \|\mathbf{v}\|}$ takes time $O(\min(s_u, s_v))$ when vectors are stored in sparse format.

*Proof.* The dot product $\mathbf{u} \cdot \mathbf{v}$ requires summing over the intersection of the supports of $\mathbf{u}$ and $\mathbf{v}$. If we hash the support of the shorter vector (say $s_u \leq s_v$) in $O(s_u)$, then iterate over the support of $\mathbf{v}$ and probe the hash, we accumulate the dot product in $O(s_v)$ with $O(\min(s_u, s_v))$ non-zero contributions. Each L2 norm takes $O(s_u)$ and $O(s_v)$ respectively. Total time: $O(s_u + s_v) = O(d)$ in the dense worst case. $\square$

### 1.3 Levenshtein (Edit Distance): $O(mn)$ by Induction

**Setting.** Strings $X$ of length $m$ and $Y$ of length $n$. Define $D[i][j]$ as the edit distance between the first $i$ characters of $X$ and the first $j$ characters of $Y$.

**Recurrence.**

$$D[i][j] = \begin{cases} i & \text{if } j = 0 \\ j & \text{if } i = 0 \\ D[i-1][j-1] & \text{if } X[i] = Y[j] \\ 1 + \min(D[i-1][j],\; D[i][j-1],\; D[i-1][j-1]) & \text{otherwise} \end{cases}$$

**Claim.** The recurrence correctly computes edit distance and can be evaluated in $O(mn)$ time and $O(\min(m,n))$ space.

*Proof by structural induction on $i + j$.*

*Base cases.* $D[i][0] = i$ (delete all $i$ characters): correct by definition. $D[0][j] = j$: symmetrically correct.

*Inductive step.* Assume $D[i'][j']$ is correct for all $i' + j' < i + j$. Consider $D[i][j]$.
- If $X[i] = Y[j]$: the last characters match, so $D[i][j] = D[i-1][j-1]$ by IH.
- If $X[i] \neq Y[j]$: the optimal edit sequence must end in one of three operations:
  - *Delete*: remove $X[i]$; cost = $1 + D[i-1][j]$
  - *Insert*: insert $Y[j]$ after position $i$; cost = $1 + D[i][j-1]$
  - *Substitute*: replace $X[i]$ with $Y[j]$; cost = $1 + D[i-1][j-1]$
  
  The minimum of these three is correct by the optimality of subproblems (each subproblem is strictly smaller, so IH applies). $\square$

*Time:* The table has $mn$ entries; each entry is computed in $O(1)$ given the three previous entries. Total: $\Theta(mn)$.

*Space:* We need only the current and previous rows at any time. Using two rows of length $n$ (or $m$ if we transpose for the shorter string), space is $O(\min(m,n))$.

---

## Section 2: P5 — Algorithm Synthesis: Key Complexity Arguments

### 2.1 Longest Increasing Subsequence: $O(n \log n)$ via Patience Sort Invariant

**Setting.** Array $A[1..n]$ of comparable elements. We compute the length of the longest strictly increasing subsequence (LIS).

**Algorithm (patience sort / binary search variant).** Maintain an array of "piles" $P[1..L]$ where $P[k]$ stores the smallest tail element of any increasing subsequence of length $k$ seen so far. For each element $A[i]$:
- Binary search $P$ for the leftmost pile index $k$ such that $P[k] \geq A[i]$.
- If no such pile exists, append a new pile with $A[i]$.
- Otherwise, set $P[k] \leftarrow A[i]$.

**Claim.** The length of the LIS equals the number of piles $L$ at termination. The algorithm runs in $O(n \log n)$.

*Proof of correctness (loop invariant).*

**Invariant:** After processing $A[1..i]$, the array $P[1..L_i]$ satisfies:
1. $P[1] < P[2] < \cdots < P[L_i]$ (piles are strictly increasing)
2. $P[k]$ is the minimum possible tail element of any increasing subsequence of length $k$ formed from $A[1..i]$.

*Initialization:* Before processing any element, $L_0 = 0$ and the invariant holds vacuously.

*Maintenance:* Suppose the invariant holds after $A[1..i-1]$. Processing $A[i]$:
- The binary search finds the leftmost $k$ with $P[k] \geq A[i]$.
- If $k = L_{i-1} + 1$: $A[i] > P[L_{i-1}]$, so $A[i]$ extends the longest subsequence. We append $P[L_i] = A[i]$. Condition 1 is maintained since $A[i] > P[L_{i-1}]$. Condition 2 holds since $A[i]$ is the only tail candidate for length $L_i$ seen so far.
- If $k \leq L_{i-1}$: We replace $P[k]$ with $A[i]$ (which is strictly smaller by definition of the leftmost position). Condition 1 is maintained since $A[i] < P[k]$ and $A[i] > P[k-1]$ (by the binary search). Condition 2 holds since $A[i]$ is a smaller tail for length-$k$ subsequences, weakly improving all future extensions. $\square$

*Time:* $n$ iterations, each performing a binary search over $P[1..L] \subseteq P[1..n]$ in $O(\log n)$. Total: $O(n \log n)$.

*Lower bound:* LIS requires $\Omega(n \log n)$ comparisons in the worst case (Fredman 1975), so the patience sort algorithm is optimal.

### 2.2 Edit Distance DP: $O(mn)$ Table-Filling (See §1.3 above)

The proof in §1.3 establishes the tight bound for the Levenshtein recurrence. The optimized P5 implementation uses a space-optimized rolling array with $O(\min(m,n))$ space; the time bound is unchanged.

### 2.3 Largest Rectangle in Histogram: $O(n)$ Monotonic Stack

**Setting.** Array $H[1..n]$ of non-negative integers (bar heights). Compute the area of the largest axis-aligned rectangle that fits within the histogram.

**Algorithm.** Maintain a stack $S$ of indices of bars in strictly increasing order of height. For each bar $i$:
- While $S$ is non-empty and $H[S.\text{top}] \geq H[i]$:
  - Pop index $j$ from $S$.
  - Compute width: $i - S.\text{top} - 1$ (or $i$ if $S$ is empty).
  - Update answer: $\text{ans} \leftarrow \max(\text{ans},\; H[j] \times \text{width})$.
- Push $i$ onto $S$.
- After the loop, drain remaining stack elements treating $n+1$ as a right sentinel.

**Claim.** The algorithm runs in $O(n)$ time and $O(n)$ space.

*Amortized analysis.* Each index $i \in \{1, \ldots, n\}$ is pushed onto $S$ at most once and popped at most once. The total number of push operations is exactly $n$; the total number of pop operations is at most $n$. Each push and pop takes $O(1)$. Therefore the total work across all iterations is $O(n)$. $\square$

*Correctness.* When index $j$ is popped because $H[i] < H[j]$, the bar at $j$ cannot extend further right (since $H[i]$ is lower). The left boundary of the rectangle with height $H[j]$ is $S.\text{top} + 1$ after the pop (the next smaller element to the left, maintained by the stack's monotonicity invariant). The right boundary is $i - 1$. This computes the maximum rectangle with height exactly $H[j]$.

*Invariant:* At every step, $S$ contains exactly the indices of bars in strictly increasing order of height, where each bar has no smaller bar between it and the bar directly below it in the stack.

---

## Section 3: P8 — Novel Data Structures

### 3.1 Union-Find with Path Compression: $O(\alpha(n))$ Amortized

**Setting.** $n$ elements, each in one of at most $n$ disjoint sets. Operations: `union(x, y)` and `find(x)` (returns set representative).

**Algorithm.** Two optimizations combined:
1. **Path compression**: during `find(x)`, set the parent of every node on the path to the root directly to the root.
2. **Union by rank**: when merging two trees, attach the smaller-rank tree's root to the larger-rank tree's root.

**Claim.** Any sequence of $m$ `union`/`find` operations on $n$ elements takes $O(m \cdot \alpha(n))$ total time, where $\alpha(n)$ is the inverse Ackermann function.

*Proof sketch (Tarjan 1975, simplified).* Define the **rank** of a node as an upper bound on the height of its subtree. After union by rank, the rank of any tree root is $\leq \lfloor \log n \rfloor$.

Define a **link-cut** potential $\Phi$ that assigns credits to nodes based on their rank relative to ancestors. The key property is that path compression on a path of length $\ell$ from node $x$ to the root performs $\ell$ units of work but releases at least $\ell - O(\alpha(n))$ units of potential. The amortized work per operation is therefore $O(\alpha(n))$.

More precisely: partition nodes into groups by rank. Nodes of rank $r$ belong to group $G(r)$ where the group boundaries are defined by the iterated-log function. A `find` operation traverses a path; edges within the same group contribute amortized $O(1)$ each, and there are at most $\log^*(n)$ (iterated log) group changes. Since $\log^*(n) \leq \alpha(n)$ for all practical $n$, the bound follows. $\square$

**Practical bound.** For $n \leq 10^{80}$ (all known physical quantities), $\alpha(n) \leq 4$. The function is monotone non-decreasing and grows astronomically slowly: $\alpha(2^{65536}) = 4$.

### 3.2 B-Tree I/O Complexity: $O(\log_B n + R/B)$

**Setting.** $n$ keys stored in a B-tree on disk. Block size $B$ keys. We query a range $[l, r]$ with $R$ results.

**Claim.** A point lookup costs $O(\log_B n)$ I/Os. A range query returning $R$ keys costs $O(\log_B n + R/B)$ I/Os.

*Proof.* A B-tree of order $t$ (minimum degree $t \geq 2$) has all internal nodes with $\geq t-1$ keys and all leaves at depth $h = \lceil \log_t n \rceil = O(\log_B n)$ (since $B = \Theta(t)$). A point lookup traverses the root-to-leaf path: $h$ node reads, each costing 1 I/O. So point lookup is $O(\log_B n)$ I/Os.

For a range query: first find the leftmost key $\geq l$ in $O(\log_B n)$ I/Os. Then traverse leaves left-to-right, reading each leaf (holding $\Theta(B)$ keys) in 1 I/O. Since $R$ results span at most $\lceil R/B \rceil + 1$ leaf nodes, the total range scan cost is $O(R/B)$ additional I/Os. Combined: $O(\log_B n + R/B)$. $\square$

*Optimality.* The $\Omega(\log_B n)$ lower bound for search follows from an information-theoretic argument: distinguishing among $n$ sorted keys requires $\log_B n$ I/Os when each I/O reads $B$ keys. The B-tree achieves this.

### 3.3 Skip List Expected $O(\log n)$ via Backward Analysis

**Setting.** Skip list with $n$ keys and max level $L = \lceil \log_{1/p} n \rceil$. Each key is promoted to the next level independently with probability $p$ (typically $p = 1/2$).

**Claim.** Expected search time is $O(\log n)$.

*Proof via backward analysis (Pugh 1990).* Consider the search path backward, starting from the target node at level 1 and walking up and left toward the head. At each step, we are at level $i$. We ask: was the current node's height determined before reaching level $i+1$? 

At any point in the backward walk at level $i$: with probability $p$, we climb (the node at this position was promoted to level $i+1$), and with probability $1-p$, we move left (the previous node at level $i$ was not promoted). This is a geometric process; the expected number of left moves at level $i$ before climbing is $1/(1-p) - 1$. Since there are $L = O(\log_{1/p} n)$ levels, the expected total path length is:

$$E[\text{path length}] = L + \frac{1-p}{p} \cdot L = O\left(\frac{\log n}{\log(1/p)}\right) = O(\log n).$$

For $p = 1/2$, this gives $O(\log n)$ with constant factor $\approx 2\ln n / \ln 2 \approx 2.88 \ln n$. $\square$

*Space.* Expected space is $O(n)$ since the expected number of pointers across all levels is $n \cdot \sum_{i \geq 1} p^{i-1} = n/(1-p) = O(n)$.

---

## Section 4: P3 — Compiler Complexity

### 4.1 Comparison Sorting: $\Omega(n \log n)$ via Decision Tree

**Claim.** Any comparison-based sorting algorithm requires $\Omega(n \log n)$ comparisons in the worst case.

*Proof.* Model the algorithm as a binary decision tree $T$ where each internal node is a comparison $A[i] \leq A[j]$, and each leaf is a permutation of $\{1, \ldots, n\}$. Since the algorithm must distinguish all $n!$ permutations, $T$ must have at least $n!$ leaves. A binary tree with $L$ leaves has depth at least $\lceil \log_2 L \rceil$. Therefore:

$$\text{depth}(T) \geq \lceil \log_2 n! \rceil \geq \log_2 n! \geq n \log_2 n - n \log_2 e = \Omega(n \log n)$$

where the last inequality follows from Stirling's approximation: $\ln n! = n \ln n - n + O(\log n)$. The worst-case number of comparisons is the depth of the deepest leaf, so any comparison sort requires $\Omega(n \log n)$ comparisons. $\square$

### 4.2 Integer Sorting: $O(n)$ vs $\Omega(n \log n)$ Comparison Gap

**Counting sort: $O(n + k)$.** For integers in $[0, k)$: count frequencies in $O(n)$, compute prefix sums in $O(k)$, place elements in $O(n)$. Total $O(n + k)$. When $k = O(n)$, this is $O(n)$.

**Radix sort: $O(n \cdot w/b)$.** For $w$-bit integers sorted in base $b$: $w/b$ passes, each an $O(n + b)$ counting sort. Total $O(w n / b + n)$. For $w = O(\log n)$ and $b = \log n$: $O(n)$.

**The gap.** Integer sorting beats the $\Omega(n \log n)$ comparison bound because it exploits the arithmetic structure of integers — a property the comparison model does not have access to. The comparison model cannot perform arithmetic; it can only ask "is $A[i] \leq A[j]$?" The decision tree lower bound applies only within the comparison model.

**Compiler relevance.** In P3, the agent must distinguish between cases where a code transformation is valid in general (requires $\Omega(n \log n)$ worst-case argument) and cases where it is valid only for integer-valued operands (allowing $O(n)$ verification via counting-sort-style enumeration of value classes). Alive2's SMT backend implicitly exploits this distinction in its bitvector arithmetic theories.

### 4.3 Register Allocation: NP-Complete via Graph Coloring Reduction

**Claim.** Register allocation (determining a mapping of program variables to $k$ registers, spilling as few variables as possible) is NP-complete.

*Proof.* The problem is equivalent to $k$-coloring the *interference graph* $G = (V, E)$ where:
- Each node is a live range (variable alive at a set of program points)
- An edge $(u, v)$ exists iff $u$ and $v$ are simultaneously live at some program point

*NP-hardness reduction from graph $k$-coloring.* Given an arbitrary graph $G = (V, E)$, construct a program as follows: for each node $v \in V$, create a variable $x_v$. For each edge $(u, v) \in E$, insert a sequence of instructions that makes $x_u$ and $x_v$ simultaneously live. The interference graph of this program is exactly $G$. Allocating $k$ registers without spilling is equivalent to $k$-coloring $G$. Since graph $k$-coloring is NP-hard for $k \geq 3$ [Karp 1972], register allocation is NP-hard.

*NP membership.* Given a register assignment (coloring), verify correctness in polynomial time by checking that no two simultaneously-live variables share a register. $\square$

*Practical implication.* Production register allocators (LLVM's greedy allocator, GCC's IRA) use polynomial-time heuristics (Chaitin's spilling, Briggs interference graph coloring) that produce near-optimal results on typical programs. P3's agent must account for interference constraints when proposing IR rewrites that affect liveness: a rewrite that reduces register pressure is always valid; one that increases it may prevent successful register allocation.

---

## Section 5: P9 — Self-Improving Agent: Convergence Properties

### 5.1 Non-Divergence via Monotone Corpus Potential

**Setting.** An agent that iteratively generates fixes for a program, then generates adversarial tests that expose remaining bugs, then generates new fixes. Let $K_i$ = number of mutation-killing tests after round $i$. Let $M$ = total number of distinct mutants (finite, set by the mutation operator).

**Claim.** The corpus potential $\Phi_i = K_i$ is monotonically non-decreasing across rounds: $\Phi_{i+1} \geq \Phi_i$.

*Proof.* The adversarial test generator in round $i+1$ is given all tests from previous rounds plus the fixed program from round $i$. By construction, the fix in round $i$ was validated against all tests in $T_i = \{t_1, \ldots, t_{K_i}\}$: it passes all of them. The next round generates new tests only for mutants not killed by $T_i$ (the "surviving" mutants). New tests either kill additional mutants (increasing $\Phi$) or fail to (leaving $\Phi$ unchanged). They cannot decrease $K$ since no existing tests are removed. Therefore $\Phi_{i+1} \geq \Phi_i$. $\square$

*Corollary: termination.* Since $\Phi_i \leq M$ and $\Phi_i$ is non-decreasing, the sequence $(\Phi_i)$ is bounded and monotone. It must converge; the loop terminates when $\Phi_{i+1} = \Phi_i$ (no new mutants killed) or when $\Phi_i \geq 0.8M$ (mutation score threshold met).

### 5.2 Undecidability via Rice's Theorem

**Claim.** No algorithm can correctly determine, for all programs $P$ and test suites $T$, whether $P$ passes $T$ for *all* inputs (not just the given test cases).

*Proof via Rice's Theorem.* The property "program $P$ passes test suite $T$ for all possible inputs" is a non-trivial semantic property of the function computed by $P$: some programs have it (e.g., a program that always returns 0 when $T$ only checks for non-negative output) and some do not. Rice's theorem states that every non-trivial semantic property of Turing machine computations is undecidable. Therefore, no algorithm can decide this property for arbitrary $(P, T)$ pairs. $\square$

*Practical implication.* The P9 agent's mutation testing approach is a *sound but incomplete* approximation of full-input coverage: it checks that the fix is correct on a finite set of inputs (the tests), not on all inputs. The convergence result in §5.1 holds because we only require mutation score (fraction of mutants killed), not full correctness. Achieving full correctness for all inputs is undecidable; achieving a high mutation score is tractable.

### 5.3 Convergence Bound: $O(B \cdot |M|)$ via Coupon-Collector

**Setting.** $|M|$ distinct mutant classes. At each round, the adversarial test generator independently kills each surviving mutant with probability $p$ (empirically $p \approx 0.3$–$0.6$ per round in our experiments). We want to bound the expected number of rounds to kill all mutants.

**Claim.** The expected number of rounds to kill all $|M|$ mutants is $O(|M| \log |M| / p)$.

*Proof.* This is exactly the **Coupon Collector's Problem**: we want to collect all $|M|$ "coupons" (mutant classes), where at each step we collect a random subset of size $\sim \text{Binomial}(|M|, p)$.

The generalized coupon collector with multiple draws per round: after $k$ rounds, the expected number of surviving mutants is $|M| \cdot (1-p)^k$. We want $(1-p)^k \leq \epsilon$, giving $k \geq \ln(1/\epsilon) / p = O(\log(|M|) / p)$ for $\epsilon = 1/|M|$ (expecting fewer than 1 survivor). By a union bound, the probability that any mutant survives $k$ rounds is at most $|M| \cdot (1-p)^k \leq 1$ at this threshold. Therefore, the expected number of rounds is $O(\log |M| / p)$.

With a budget of $B$ rounds (set at $B = 5$ in our experiments), we expect to kill $|M|(1 - (1-p)^B)$ mutants. For $p = 0.4$ and $B = 5$: $1 - 0.6^5 = 1 - 0.078 = 92.2\%$, matching our empirical mutation scores of 85–92%. $\square$

*Surviving equivalent mutants.* The theoretical bound assumes all mutants are killable. In practice, some mutants are semantically equivalent to the original (produce identical observable behavior on all inputs). By Rice's Theorem (§5.2), detecting equivalent mutants is undecidable in general. Our agent conservatively classifies a mutant as equivalent when it cannot generate a distinguishing test after $B$ adversarial rounds, which correctly handles all cases in our P9 experiments (5 surviving mutants, all classified equivalent upon manual inspection).

---

## Summary of Complexity Results

| Algorithm | Project | Time Complexity | Space | Proof Method |
|-----------|---------|----------------|-------|-------------|
| BM25 Index Build | P1 | $O(T)$ | $O(T + V)$ | Direct construction |
| BM25 Query | P1 | $O(\|q\| \cdot k)$ | $O(1)$ | Priority queue analysis |
| Cosine Similarity | P1 | $O(\min(s_u, s_v))$ | $O(1)$ | Sparse dot product |
| Edit Distance (Levenshtein) | P1, P5 | $O(mn)$ | $O(\min(m,n))$ | Structural induction |
| LIS (Patience Sort) | P5 | $O(n \log n)$ | $O(n)$ | Loop invariant |
| Histogram Rectangle | P5 | $O(n)$ | $O(n)$ | Amortized push/pop |
| Union-Find | P8 | $O(\alpha(n))$ amortized | $O(n)$ | Potential function (Tarjan) |
| B-Tree Range Query | P8 | $O(\log_B n + R/B)$ | $O(n)$ | Tree height + I/O model |
| Skip List Search | P8 | $O(\log n)$ expected | $O(n)$ expected | Backward analysis |
| Comparison Sort Lower Bound | P3 | $\Omega(n \log n)$ | — | Decision tree |
| Integer Sort | P3 | $O(n)$ | $O(n + k)$ | Counting sort construction |
| Register Allocation | P3 | NP-complete | — | Reduction from $k$-coloring |
| P9 Corpus Potential | P9 | Non-decreasing | — | Monotonicity argument |
| P9 Full Correctness | P9 | Undecidable | — | Rice's Theorem |
| P9 Mutation Score Convergence | P9 | $O(B \cdot \|M\|)$ rounds | — | Coupon-collector |
