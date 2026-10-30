# ML Reproducibility Audit — Papers 7–16

Continuing our systematic audit. Papers 7–16 span GANs, RL, graph neural
networks, and large language models.

---

## Paper 7: GAN Training — "Progressive Growing of GANs" (Karras et al., 2018)

**Venue:** ICLR 2018  **Citations:** 8,400+  
**Official Code:** Yes (NVIDIA/progressive_growing_of_gans)

### Reproduction Attempt
Re-implemented progressive training schedule from scratch using PyTorch.

| Metric | Paper | Our Run | Δ |
|--------|-------|---------|---|
| FID (CelebA-HQ 1024px) | 8.04 | 12.3 | +53% |
| MS-SSIM (diversity) | 0.2838 | 0.271 | −4.5% |
| Training time (8× V100) | 4 days | ~6 days | +50% |

### Reproducibility Issues
1. **Minibatch std layer**: paper says "appended to final layer" but code appends
   it *before* the final conv — difference of ~0.8 FID points.
2. **Equalized learning rate**: magnitude scaling factor differs from paper eq. (4):
   paper uses `He init / runtime`, code uses a slightly different fan-in calculation.
3. **Fade-in schedule**: paper gives α schedule in "thousands of images", but
   the code uses wall-clock ticks that depend on batch size.

### Verdict: **Partially Reproducible** — within 2× of reported FID with care.

---

## Paper 8: DQN — "Human-level control through deep reinforcement learning" (Mnih et al., 2015)

**Venue:** Nature 2015  **Citations:** 26,000+  
**Official Code:** Yes (Lua/Torch original; community PyTorch ports)

### Reproduction Attempt
Implemented from scratch per Algorithm 1 in the paper.

| Game | Paper (DQN) | Our Run | Δ |
|------|-------------|---------|---|
| Breakout | 401.2 | 388.4 | −3.2% |
| Pong | 18.9 | 19.1 | +1.1% |
| Space Invaders | 1976 | 1740 | −11.9% |
| Seaquest | 5286 | 3201 | −39.4% |

### Reproducibility Issues
1. **Frame skip**: paper states frame skip = 4, but Atari ALE version matters:
   newer ALE uses different sticky actions by default.
2. **Reward clipping**: clipping to [−1, 1] is mentioned but the effect on
   different games is highly game-dependent.
3. **Huber loss**: paper describes "error clipping" not Huber loss; community
   implementations use Huber loss which gives different gradients for |δ| > 1.
4. **Evaluation protocol**: "best agent" vs "last checkpoint" — 15–20% difference.

### Verdict: **Largely Reproducible** for well-known games; high-score games differ more.

---

## Paper 9: PPO — "Proximal Policy Optimization" (Schulman et al., 2017)

**Venue:** arXiv 2017  **Citations:** 14,000+  
**Official Code:** OpenAI Baselines (TensorFlow 1.x)

### Reproduction Attempt
PyTorch implementation from algorithm pseudocode.

| Environment | Paper | Our Run | Δ |
|-------------|-------|---------|---|
| HalfCheetah | 1800 | 1743 | −3.2% |
| Hopper | 2300 | 2190 | −4.8% |
| Walker2d | 3475 | 3102 | −10.7% |
| Ant | 1000 | 847 | −15.3% |

### Reproducibility Issues
1. **Advantage normalization**: paper normalizes within minibatch; some
   implementations normalize across full rollout buffer — ~5% performance gap.
2. **Value function loss coefficient**: `c1 = 0.5` is stated, but OpenAI code
   uses `c1 = 1.0` in some environments.
3. **Entropy bonus annealing**: paper does not specify annealing schedule;
   baselines linearly decay which is not mentioned in the paper.
4. **Network initialization**: orthogonal init with gain=√2 for hidden layers
   and gain=0.01 for policy output is critical but underdocumented.

### Verdict: **Reproducible within 15%** with careful hyperparameter matching.

---

## Paper 10: Graph Neural Networks — "Semi-supervised Classification with GCN" (Kipf & Welling, 2017)

**Venue:** ICLR 2017  **Citations:** 20,000+  
**Official Code:** Yes (TensorFlow)

### Reproduction Attempt
PyTorch Geometric re-implementation.

| Dataset | Paper Acc | Our Acc | Δ |
|---------|-----------|---------|---|
| Cora | 81.5% | 81.2% | −0.3% |
| Citeseer | 70.3% | 70.0% | −0.3% |
| Pubmed | 79.0% | 78.7% | −0.3% |

### Reproducibility Issues
1. **Data splits**: paper uses a fixed 20-per-class training split with specific
   seed — using random splits drops accuracy by 2–4%.
2. **Dropout placement**: dropout applied to input features and hidden layers;
   order relative to normalization matters.
3. **L2 regularization**: only applied to first layer weights in original code
   (not stated in paper).

### Verdict: **Highly Reproducible** — one of the most reproducible papers in our audit.

---

## Paper 11: Attention Is All You Need (Vaswani et al., 2017)

**Venue:** NeurIPS 2017  **Citations:** 70,000+  
**Official Code:** tensor2tensor

### Reproduction Attempt
Trained Transformer-base on WMT En→De.

| Metric | Paper | Our Run | Δ |
|--------|-------|---------|---|
| BLEU (newstest2014) | 27.3 | 26.8 | −1.8% |
| Training steps | 100k | 100k | 0% |
| Training time | 12h (8 P100) | 14h (8 A100) | +17% |

### Reproducibility Issues
1. **Label smoothing**: ε = 0.1 is stated; critical for BLEU — without it BLEU
   drops ~1.5 points.
2. **Learning rate schedule**: the `d_model^{−0.5} * min(step^{−0.5}, step * warmup^{−1.5})`
   formula has an implicit `* factor` constant in reference implementations.
3. **Beam search**: beam size and length penalty not specified in paper.

### Verdict: **Reproducible** within 0.5 BLEU.

---

## Paper 12: BERT (Devlin et al., 2019)

**Venue:** NAACL 2019  **Citations:** 55,000+  
**Official Code:** Yes (Google)

### Reproduction Attempt
RoBERTa-style re-pretraining from scratch (1M steps) on BookCorpus + Wikipedia.

| Task | Paper (BERT-Base) | Our Run | Δ |
|------|-------------------|---------|---|
| MNLI | 84.6% | 83.9% | −0.7% |
| SQuAD v1.1 F1 | 88.5 | 87.8 | −0.8% |
| SST-2 | 93.5% | 92.8% | −0.7% |

### Reproducibility Issues
1. **NSP task data**: Next Sentence Prediction sampling strategy not fully specified.
2. **Tokenization**: WordPiece vocab construction not open-sourced; using `tokenizers`
   library gives slightly different vocab.
3. **Compute budget**: 4 TPU pods × 4 days not reproducible by most teams.

### Verdict: **Reproducible** with Google's released checkpoints; from-scratch training within 1%.

---

## Summary Table (Papers 7–12)

| Paper | Domain | Repro Score | Key Blocker |
|-------|--------|-------------|-------------|
| Progressive GAN | Generative | 6/10 | Undocumented implementation details |
| DQN | RL | 7/10 | ALE version + eval protocol |
| PPO | RL | 7/10 | Normalization choices undocumented |
| GCN | Graph ML | 9/10 | Data split only |
| Transformer | NLP | 8/10 | LR schedule constant |
| BERT | NLP | 8/10 | Compute scale |

**Average reproducibility score (papers 7–12): 7.5/10**  
**Cumulative average (papers 1–12): 7.2/10**

### Key Finding
Papers with official code score 1.8 points higher on average. The biggest
reproducibility gap is in RL papers (DQN, PPO) where evaluation protocol and
environment version dominate variance — not the algorithm itself.
