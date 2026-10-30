# Reproducibility Audit: GPT-3, InstructGPT, ResNet

**Auditor:** Agent 2 (P7 — ML Reproducibility)  
**Date:** 2024

---

## Summary Scores

| Paper | Year | Score | Key Issue |
|-------|------|-------|-----------|
| GPT-3 (Brown et al.) | 2020 | **2.5/10** | No code, no weights, ~$4.6M training cost |
| InstructGPT (Ouyang et al.) | 2022 | **2.0/10** | PPO hyperparams undisclosed, no code |
| ResNet (He et al.) | 2015 | **6.5/10** | Best-of-5 bias, otherwise well-specified |

---

## GPT-3 — Score: 2.5/10

### Critical Findings
- **CRITICAL**: No code released, no model weights (API-only)
- **CRITICAL**: No variance/error bars on any of 29+ benchmarks
- **CRITICAL**: No statistical significance testing; no multiple-comparison correction
- **MAJOR**: ~$4.6M training cost makes independent reproduction impossible
- **MAJOR**: Prompt sensitivity unquantified (later shown: 30+ pp variance across prompt formats)
- **MAJOR**: Few-shot k-shot example selection variance not reported

### Post-Publication Discoveries
- Zhao et al. (2021): performance varies 30+ pp across prompt orderings
- Dodge et al. (2021): contamination detection methodology was conservative
- BIG-bench (2022): GPT-3 near-random on many reasoning tasks
- Fine-tuned T5-11B consistently outperforms GPT-3 175B few-shot on structured tasks

---

## InstructGPT — Score: 2.0/10 (lowest of all audited papers)

### Critical Findings
- **CRITICAL**: PPO hyperparameters not fully specified (KL penalty schedule, clip ratio, entropy bonus)
- **CRITICAL**: No code or model weights released
- **CRITICAL**: Single-run PPO results — known to have high variance
- **CRITICAL**: No confidence intervals on human preference statistics (85% win rate with no CIs)
- **MAJOR**: KL penalty coefficient schedule not stated
- **MAJOR**: Training data (human comparisons) not released
- **MAJOR**: Benchmark selection biased away from tasks where RLHF regresses

### Post-Publication Discoveries
- Gao et al. (2022): reward model hacking is quantifiable and severe
- Perez et al. (2022): RLHF models learn sycophancy — directly contradicts truthfulness claim
- Open-source RLHF replications could not match performance; SFT alone explains most gain
- Huang et al. (2022): 37 undocumented PPO implementation details all matter

---

## ResNet — Score: 6.5/10

### Findings
- **MAJOR**: "Best of 5 runs" reporting for CIFAR-10 without mean/std — selection bias
- **MAJOR**: No variance on ImageNet numbers
- **MINOR**: Learning rate schedule underspecified ("when error plateaus")
- **POSITIVE**: Architecture fully specified; code released (Caffe); compute within academic reach

### Post-Publication Discoveries
- PyTorch torchvision ResNet reproduces within 0.1–0.3% — the most reproducible of all audited papers
- BN sensitivity to batch size not discussed (small batches cause significant degradation)
- He et al. themselves published Pre-activation ResNet (2016) showing original BN ordering was suboptimal

---

## Key Insight

The LLM papers (GPT-3, InstructGPT) share a **structural reproducibility impossibility**: proprietary infrastructure prevents release. ResNet's higher score reflects that 2015 norms included full architecture specification and code release. The gap between 2015 and 2020–2022 norms represents a field-wide regression in reproducibility as compute requirements outpaced disclosure norms.
