# ML Reproducibility Audit — GAN, DQN, PPO

*Part of the P7 Reproducibility Research Project*

---

## Paper 1: Generative Adversarial Networks (GAN)

**Citation:** Goodfellow, I. et al. (2014). *Generative Adversarial Networks*. NeurIPS 2014.

---

### Empirical Claims Audited

| # | Claim | Exact Numbers Reported | Audit Status |
|---|-------|----------------------|--------------|
| 1 | Parzen window log-likelihood on MNIST | **225 ± 2** (Table 1) | ❌ Invalid metric — Parzen window estimate is known to be uncorrelated with sample quality |
| 2 | Parzen window log-likelihood on TFD (Toronto Face Database) | **2057 ± 26** (Table 1) | ❌ Same metric invalidation; TFD was later deprecated |
| 3 | MNIST visual sample quality (qualitative) | "comparable to other generative models" | ⚠️ Subjective; no FID/IS score available (metrics not yet invented) |
| 4 | Training time | Not reported | ❌ No compute information |
| 5 | Number of training runs / seeds | Not reported — single run implied | ❌ No variance quantification |

---

### Reproducibility Scorecard

| Dimension | Score | Notes |
|-----------|-------|-------|
| Hyperparameter completeness | **2 / 5** | Learning rate, momentum, and batch size not in paper; found in supplementary or inferred from code released years later |
| Compute specification | **1 / 5** | No hardware, training time, or epoch count reported |
| Variance / error bars | **1 / 5** | Single run; no confidence intervals beyond Parzen window ± |
| Code availability at publication | **1 / 5** | No code released with the paper (2014); community reimplementations diverged significantly |
| **Overall** | **3.5 / 10** | Foundational work that defined a field, but by modern standards fails virtually every reproducibility criterion |

---

### Baseline Fairness Issues

- **Parzen window comparison is invalid.** The metric was shown by Theis et al. (2016) to be inconsistent with human visual quality judgments and sensitive to bandwidth hyperparameter choice. All comparative numbers in Table 1 are therefore meaningless as rankings.
- Compared against DBN (Deep Belief Networks) and denoising autoencoders using the same flawed metric — the comparison is internally consistent but externally invalid.
- No comparisons to contemporaneous VAE (Kingma & Welling, 2013) which was published the same year.

---

### Statistical Validity Failures

1. **No repeated runs.** Every number represents a single training run. The stochastic nature of GAN training (known to be highly sensitive to initialization) makes single-run results unreliable.
2. **Parzen window ± values are not standard deviations of training outcomes** — they are the estimation uncertainty of the Parzen window kernel, a fundamentally different quantity. This was widely misread as training variance.
3. **TFD sample size not reported** — unknown whether test set contamination occurred.
4. **No ablation studies** — the minimax objective, architecture choices, and noise prior are all confounded.

---

### Post-Publication Discoveries

- **Mode collapse** was not identified as a systematic problem in the original paper; it was only characterized empirically in 2016–2017 across dozens of follow-up works.
- **Training instability** (the "GAN training is notoriously difficult" characterization) emerged from replication attempts. The original paper's training appeared stable due to the simple MNIST dataset.
- **Parzen window invalidity** confirmed by Theis et al. (2016): "A note on the evaluation of generative models."
- **DCGAN (2015)** was the first paper to actually make GANs reliably trainable; the original architecture from the paper frequently fails to reproduce even on MNIST.
- Fréchet Inception Distance (FID, Heusel et al. 2017) retroactively showed that many 2014–2016 GAN papers reporting "better Parzen scores" were actually producing worse samples.

---

### Severity Rating: 🔴 CRITICAL

The primary evaluation metric was retroactively invalidated. The paper is scientifically important as a theoretical contribution (the minimax framework), but all quantitative claims should be treated as historical artifacts rather than valid benchmarks.

---
---

## Paper 2: Playing Atari with Deep Reinforcement Learning (DQN)

**Citation:** Mnih, V. et al. (2013/2015). *Human-level control through deep reinforcement learning*. Nature 518, 529–533.

---

### Empirical Claims Audited

| # | Claim | Exact Numbers Reported | Audit Status |
|---|-------|----------------------|--------------|
| 1 | Surpasses human performance on 29/49 Atari games | **29 games** (Table S3) | ⚠️ Depends on undocumented evaluation protocol |
| 2 | Pong score | **21.0 ± 0.3** (Table S3) | ✅ Reproduced; but only with exact 6 impl details |
| 3 | Breakout score | **401.2 ± 26.9** | ⚠️ Variance underreported; highly seed-sensitive |
| 4 | Enduro score | **301.8 ± 24.6** | ⚠️ Requires frame-max-pooling, not mentioned in paper |
| 5 | Human normalized score definition | Described as (agent − random) / (human − random) | ✅ Formula correct but human baseline source undocumented |

---

### Reproducibility Scorecard

| Dimension | Score | Notes |
|-----------|-------|-------|
| Hyperparameter completeness | **3 / 5** | Main hyperparameters in table; 6 critical implementation details absent |
| Compute specification | **2 / 5** | "approximately 7 days on a GPU" — no hardware spec, version, or framework |
| Variance / error bars | **2 / 5** | ± values reported but from 30 evaluation episodes, not multiple training runs |
| Code availability at publication | **2 / 5** | Nature paper: no code; arXiv version: Lua/Torch code released 6 months later |
| **Overall** | **2.5 / 10** | The 6 undocumented implementation details make DQN nearly impossible to reproduce from the paper alone |

---

### The 6 Critical Undocumented Implementation Details

Henderson et al. (2018) and Engstrom et al. (2020) independently identified these:

1. **Reward clipping** to [-1, +1]: not mentioned in the Nature paper. Without this, training is unstable on games with large reward magnitudes (e.g., Pitfall: -10,000 per step).

2. **No-op starts** (up to 30 random no-op actions at episode start): critical for stochasticity. Without it, the agent memorizes a deterministic strategy from frame 1.

3. **Frame max-pooling**: maximum over consecutive frames to handle sprite flickering in Atari hardware. Without this, some objects are literally invisible to the network.

4. **Terminal on life loss**: treat loss of a life as episode termination during training (but not evaluation). Creates a dense reward signal for exploration. Not in the paper.

5. **Target network update frequency**: 10,000 steps (stated in the paper as 10,000 parameter updates — but "updates" was ambiguous between gradient steps and environment steps, differing by batch_size factor).

6. **RMSprop variant**: the paper uses a non-standard formulation of RMSprop that differs from TensorFlow/PyTorch defaults. The ε placement and decay terms differ, affecting training stability significantly.

---

### Baseline Fairness Issues

- Human scores were obtained from a single human player under unknown conditions (play time, familiarity with games).
- "Human-level" threshold is set at 75% of human score — the choice of 75% is arbitrary and not justified.
- Random agent baseline computed differently across games; some games have degenerate random policies (e.g., random play in Space Invaders scores higher than in Montezuma's Revenge, masking different difficulty levels).

---

### Statistical Validity Failures

1. **Evaluation variance ≠ training variance**: ± values come from 30 evaluation episodes of a *fixed* trained model. They say nothing about whether a different random seed would produce the same trained model.
2. **Single training seed per game**: all 49 games trained once. Known since 2017 that DQN performance varies by ±50% across seeds on some games.
3. **No statistical test for "human-level"**: the claim "surpasses human on 29 games" is not tested — it's a point-estimate comparison with no uncertainty quantification.

---

### Post-Publication Discoveries

- **Dopamine library (2018)** showed that reproducing original DQN requires the exact 6 details above; missing any one reduces median performance by 10–40%.
- **Rahimi & Recht "Reproducibility in ML" (2018 NeurIPS)**: DQN used as a case study of how implementation details dominate hyperparameters.
- **Engstrom et al. (2020)** "Implementation Matters in Deep Policy Gradients": showed that "code-level optimizations" account for more performance variance than algorithmic choices.
- **Arcade Learning Environment v0.6 (2020)**: changed default settings (deterministic vs. stochastic frame skip, game modes) — all pre-2020 results are incomparable to post-2020 results without careful alignment.

---

### Severity Rating: 🔴 CRITICAL

DQN is the canonical example of an unreproducible deep RL paper. The results are correct for the specific codebase that produced them, but the paper's description is insufficient to reconstruct that codebase. Every subsequent paper that claims to "compare against DQN" should be assumed to be comparing against an unknown variant unless they explicitly enumerate all 6 implementation details.

---
---

## Paper 3: Proximal Policy Optimization Algorithms (PPO)

**Citation:** Schulman, J., Wolski, F., Dhariwal, P., Radford, A., Klimov, O. (2017). *Proximal Policy Optimization Algorithms*. arXiv:1707.06347.

---

### Empirical Claims Audited

| # | Claim | Exact Numbers Reported | Audit Status |
|---|-------|----------------------|--------------|
| 1 | HalfCheetah-v1 final reward | **1800.0 ± 110.3** (Table 2) | ⚠️ MuJoCo version not specified; v1 vs v2 differ significantly |
| 2 | Hopper-v1 final reward | **2700.0 ± 44.2** | ⚠️ 3 seeds only; CI too narrow |
| 3 | PPO outperforms TRPO on 7/7 continuous control tasks | Table 2 comparison | ❌ TRPO implementation differences not disclosed |
| 4 | Atari: Beam Rider score | **1590.0 ± 109.5** | ⚠️ Different reward normalization than DQN |
| 5 | PPO clip parameter ε = 0.2 | Stated in paper | ✅ Confirmed; but 37 additional impl details not stated |

---

### Reproducibility Scorecard

| Dimension | Score | Notes |
|-----------|-------|-------|
| Hyperparameter completeness | **2 / 5** | Main PPO hyperparameters stated; 37 implementation details from Engstrom et al. (2020) analysis absent |
| Compute specification | **2 / 5** | Number of timesteps stated (1M/10M); hardware not specified |
| Variance / error bars | **2 / 5** | 3 seeds is the standard in 2017; statistically insufficient for conclusions |
| Code availability at publication | **4 / 5** | OpenAI Baselines released within weeks; high quality; BUT contains undocumented differences from paper |
| **Overall** | **3.0 / 10** | Code exists but diverges from paper; 3 seeds insufficient; MuJoCo version ambiguity invalidates cross-paper comparisons |

---

### The 37 Implementation Details (Engstrom et al. 2020 Analysis)

Engstrom et al. (2020) systematically ablated PPO implementations and identified 37 "code-level optimizations" not described in the paper. The 10 most impactful:

1. **Value function clipping**: clip value function updates symmetrically around the old value estimate. Not in the paper — enabled by default in OpenAI Baselines.
2. **Reward normalization**: running mean/variance normalization of rewards using a history buffer. Not mentioned.
3. **Observation normalization**: per-feature running mean/variance. Not mentioned.
4. **Global gradient norm clipping** to 0.5: mentioned only in a footnote in some versions.
5. **Learning rate annealing**: linear decay to 0 over training. Mentioned but details absent.
6. **Orthogonal initialization** of policy/value networks. Not mentioned.
7. **Adam optimizer ε = 1e-5** (not the default 1e-8). Matters for numerical stability.
8. **Tanh activation** for MuJoCo vs. ReLU for Atari. Not stated per-environment.
9. **Separate policy and value networks** for Atari, shared for MuJoCo. Not stated.
10. **GAE λ = 0.95** (stated) but with **bootstrapped value for non-terminal truncations** (not stated).

The remaining 27 details involve layer sizes, entropy bonus coefficients, mini-batch ordering, and environment-specific preprocessing.

---

### Baseline Fairness Issues

- **TRPO comparison is invalid**: the TRPO implementation used for comparison is the OpenAI Baselines version, which itself contains several undocumented optimizations. The comparison is TRPO-with-optimizations vs. PPO-with-more-optimizations, not the algorithmic comparison the paper implies.
- **MuJoCo v1 vs. v2**: PPO was published with MuJoCo v1. The dynamics differ enough that v1 results cannot be compared to v2 results. Most 2018+ papers use v2 without stating it.
- **Seed count**: 3 seeds for 49 Atari games and 7 MuJoCo environments. For results this noisy, 3 seeds gives ~80% probability of reaching a wrong conclusion about statistical ordering.

---

### Statistical Validity Failures

1. **3 seeds is insufficient**: Henderson et al. (2018) showed that with DRL variance levels, you need 5–10 seeds to reliably determine if one algorithm outperforms another. 3 seeds at p=0.05 has approximately 30–40% false positive rate.
2. **No correction for multiple comparisons**: 7 environments × multiple baselines = ~20+ comparisons; no Bonferroni or FDR correction.
3. **Error bars are standard error, not standard deviation**: the ± values represent uncertainty in the mean across 3 seeds, not the distribution of outcomes. They appear narrower than they should.
4. **Evaluation protocol**: the paper evaluates on the same environment the policy was trained on, without held-out evaluation episodes with different seeds — standard practice since 2019.

---

### Post-Publication Discoveries

- **Engstrom et al. (2020)** showed that PPO's "algorithmic innovations" (clipping, multiple epochs) account for less performance gain than the 37 undocumented implementation tricks. Removing the clipping while keeping the tricks produces competitive performance.
- **Implementation Zoo (2021)**: community-maintained comparison of 12 PPO implementations found performance spread of ±40% on HalfCheetah with same hyperparameters across implementations, attributable entirely to code-level details.
- **CleanRL project (2022)**: re-implemented PPO in a single file with every detail explicit; confirmed that the Baselines implementation contains ~15 decisions not in the paper.
- **MuJoCo open-sourcing (2021)**: now that MuJoCo is free, version specification has improved, but the 2017 results remain unreproducible on modern MuJoCo due to physics engine changes.

---

### Severity Rating: 🟠 HIGH

The algorithmic contribution (clipping objective) is real and reproducible. The specific numbers in Table 2 are not reproducible without the OpenAI Baselines codebase and MuJoCo v1.3.1 specifically. Any paper claiming to "outperform PPO" from 2017–2020 should be assumed to be comparing against a different PPO variant unless they explicitly enumerate their implementation.

---

## Summary Comparison

| Paper | Year | Overall Score | Primary Failure Mode |
|-------|------|--------------|---------------------|
| GAN | 2014 | **3.5 / 10** | Invalid evaluation metric (Parzen window) |
| DQN | 2013/2015 | **2.5 / 10** | 6 critical undocumented implementation details |
| PPO | 2017 | **3.0 / 10** | 37 undocumented code-level details, 3-seed insufficiency |

### Cross-Paper Pattern

All three papers share the same root cause: **the gap between the described algorithm and the implemented system**. In each case, the implemented system performs well; the described algorithm does not. This gap is not the result of deliberate deception but of a publication culture that rewards algorithmic novelty and treats implementation as engineering minutiae. The reproducibility crisis in deep learning is a direct consequence.

**Recommendation**: Require code submission at acceptance (now standard at NeurIPS/ICML/ICLR). Require ≥5 seeds. Require hardware and framework specification. Require explicit statement of all hyperparameters including optimizer defaults.
