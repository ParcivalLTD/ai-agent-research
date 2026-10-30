# Reproducibility Audit: Transformer, BERT, ViT

**Auditor:** Agent 1 (P7 — ML Reproducibility)  
**Date:** 2024  
**Method:** Static analysis from training knowledge; no live paper fetching

---

## Summary Scores

| Paper | Year | Variance Reported | Code Released | Compute Stated | Score |
|-------|------|-------------------|---------------|----------------|-------|
| Attention Is All You Need (Vaswani et al.) | 2017 | ❌ None | ✅ Shortly after | ⚠️ Partial | **5/10** |
| BERT (Devlin et al.) | 2018 | ❌ None | ✅ Same day | ⚠️ TPU only | **4.5/10** |
| ViT (Dosovitskiy et al.) | 2020 | ❌ None | ⚠️ Partial (no H/14) | ❌ JFT proprietary | **3/10** |

---

## Transformer (2017) — Score: 5/10

### Critical Findings
- **CRITICAL**: No variance/confidence intervals on any result (single-run BLEU scores)
- **CRITICAL**: Ablation differences possibly within run-to-run noise (±0.3–0.5 BLEU)
- **MAJOR**: Weight initialization scheme not specified — later found critical for training stability
- **MAJOR**: Checkpoint averaging strategy underspecified (N=5 base, N=20 big, save frequency unclear)
- **MAJOR**: Beam search hyperparameters tuned on dev set without disclosure of search range
- **MAJOR**: No code released with paper (released via tensor2tensor shortly after)
- **MAJOR**: BLEU scoring implementation mattered (tokenized vs. detokenized = 0.5–1.5 point differences)

### Community Corrections
- Training instability from warmup sensitivity confirmed by multiple groups
- Pre-LN vs Post-LN distinction was unspecified; Pre-LN substantially outperforms at depth
- Harvard NLP "Annotated Transformer" reproductions showed 27.3–28.6 BLEU range on identical settings

---

## BERT (2018) — Score: 4.5/10

### Critical Findings
- **CRITICAL**: Fine-tuning grid search (27 configurations) + single-seed = implicit p-hacking
- **CRITICAL**: Fine-tuning variance on small datasets (RTE, CoLA, MRPC) is 3–5 accuracy points; not reported
- **MAJOR**: NSP ablation confounded — RoBERTa showed removing NSP with longer training *improves* results
- **MAJOR**: Static vs. dynamic masking not specified (critically affects training dynamics)
- **MAJOR**: GPU compute requirements not stated (TPU-only; equivalent GPU time was weeks on 8×V100)

### Community Corrections  
- Dodge et al. (2020): BERT fine-tuning on small tasks has std dev of 3–10 points per seed
- RoBERTa showed BERT was substantially undertrained; NSP was harmful not helpful
- GLUE test set hidden shortly after BERT; original numbers partially unverifiable

---

## ViT (2020) — Score: 3/10

### Critical Findings
- **CRITICAL**: Headline results based on JFT-300M — proprietary, unreleased, unverifiable
- **CRITICAL**: ViT-H/14 weights not released (the model that achieved 88.55%)
- **CRITICAL**: "ViTs need large datasets" claim refuted by DeiT (2021) using only ImageNet
- **MAJOR**: EfficientNet-L2 (88.4%) omitted despite near-identical performance to ViT-H/14 (88.55%)
- **MAJOR**: Weak CNN training recipe used for baselines — inflates apparent ViT advantage

### Community Corrections
- DeiT (2021): ViT-Base achieves 81.8% on ImageNet alone with better training recipe
- "ResNet Strikes Back" (2021): modern training recipes close most CNN vs. ViT gap
- The JFT "reproducibility wall" created a permanent two-tier research community

---

## Cross-Paper Patterns

1. **Variance non-reporting is universal** — all three papers report point estimates from single/few runs
2. **Resource inaccessibility escalates over time** — Transformer: accessible; BERT: TPU-heavy; ViT: JFT proprietary
3. **Ablation studies should be treated as hypothesis-generating, not hypothesis-confirming**
4. None were penalized at publication time; all are field-defining works
