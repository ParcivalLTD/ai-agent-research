# Reproducibility Score Aggregator
# Computes aggregate statistics across all audited papers

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PaperAudit:
    """Record of a single paper's reproducibility audit."""
    paper_id: str
    title: str
    venue: str
    year: int
    domain: str
    has_official_code: bool
    score: float          # 0–10
    key_blockers: list[str] = field(default_factory=list)
    metric_gaps: dict[str, float] = field(default_factory=dict)
    notes: str = ""

    @property
    def tier(self) -> str:
        if self.score >= 8.5: return "Highly Reproducible"
        if self.score >= 7.0: return "Reproducible"
        if self.score >= 5.0: return "Partially Reproducible"
        return "Difficult to Reproduce"


# ── Audit data ─────────────────────────────────────────────────────────────

AUDITS: list[PaperAudit] = [
    PaperAudit("p1",  "Attention Is All You Need",                   "NeurIPS", 2017, "NLP",        True,  8.0,
               ["LR schedule constant undocumented", "beam search not specified"]),
    PaperAudit("p2",  "BERT",                                        "NAACL",   2019, "NLP",        True,  8.0,
               ["NSP sampling undocumented", "compute scale"]),
    PaperAudit("p3",  "Vision Transformer (ViT)",                    "ICLR",    2021, "CV",         True,  7.5,
               ["JFT-300M dataset not public", "fine-tuning LR schedule"]),
    PaperAudit("p4",  "GPT-3",                                       "NeurIPS", 2020, "NLP",        False, 3.0,
               ["Model weights not released", "infrastructure not reproducible"]),
    PaperAudit("p5",  "InstructGPT (RLHF)",                          "NeurIPS", 2022, "NLP",        False, 2.5,
               ["Human preference data not released", "reward model not public"]),
    PaperAudit("p6",  "ResNet",                                      "CVPR",    2016, "CV",         True,  9.0,
               ["Minor: batch norm momentum differs"]),
    PaperAudit("p7",  "Progressive Growing of GANs",                 "ICLR",    2018, "Generative", True,  6.0,
               ["Equalized LR implementation differs", "fade-in schedule ambiguous"]),
    PaperAudit("p8",  "DQN",                                         "Nature",  2015, "RL",         True,  7.0,
               ["ALE version matters", "evaluation protocol underspecified"]),
    PaperAudit("p9",  "PPO",                                         "arXiv",   2017, "RL",         True,  7.0,
               ["Advantage normalisation not documented", "entropy annealing undocumented"]),
    PaperAudit("p10", "GCN",                                         "ICLR",    2017, "Graph ML",   True,  9.0,
               ["Fixed data split required"]),
    PaperAudit("p11", "Transformer (original)",                      "NeurIPS", 2017, "NLP",        True,  8.0,
               ["LR schedule constant", "beam search params"]),
    PaperAudit("p12", "BERT (replication)",                          "NAACL",   2019, "NLP",        True,  8.0,
               ["NSP sampling", "compute budget"]),
]


# ── Aggregator ─────────────────────────────────────────────────────────────

class ReproducibilityAggregator:
    def __init__(self, audits: list[PaperAudit]):
        self.audits = audits

    def mean_score(self) -> float:
        if not self.audits: return 0.0
        return sum(a.score for a in self.audits) / len(self.audits)

    def score_by_domain(self) -> dict[str, float]:
        domains: dict[str, list[float]] = {}
        for a in self.audits:
            domains.setdefault(a.domain, []).append(a.score)
        return {d: sum(s)/len(s) for d, s in domains.items()}

    def official_code_effect(self) -> dict[str, float]:
        with_code    = [a.score for a in self.audits if a.has_official_code]
        without_code = [a.score for a in self.audits if not a.has_official_code]
        return {
            "with_code":    sum(with_code)    / max(len(with_code), 1),
            "without_code": sum(without_code) / max(len(without_code), 1),
            "delta":        (sum(with_code)/max(len(with_code),1)) -
                            (sum(without_code)/max(len(without_code),1)),
        }

    def tier_distribution(self) -> dict[str, int]:
        dist: dict[str, int] = {}
        for a in self.audits:
            dist[a.tier] = dist.get(a.tier, 0) + 1
        return dist

    def top_blockers(self, n: int = 5) -> list[tuple[str, int]]:
        freq: dict[str, int] = {}
        for a in self.audits:
            for b in a.key_blockers:
                # Normalise to first 5 words
                key = " ".join(b.lower().split()[:5])
                freq[key] = freq.get(key, 0) + 1
        return sorted(freq.items(), key=lambda x: -x[1])[:n]

    def report(self) -> str:
        lines = [
            "=== Reproducibility Audit — Aggregate Report ===",
            f"Papers audited: {len(self.audits)}",
            f"Mean score: {self.mean_score():.2f}/10",
            "",
            "Score by domain:",
        ]
        for domain, score in sorted(self.score_by_domain().items()):
            lines.append(f"  {domain:<15} {score:.2f}/10")
        eff = self.official_code_effect()
        lines += [
            "",
            f"Official code effect: +{eff['delta']:.2f} points",
            f"  With code:    {eff['with_code']:.2f}/10  (n={sum(1 for a in self.audits if a.has_official_code)})",
            f"  Without code: {eff['without_code']:.2f}/10  (n={sum(1 for a in self.audits if not a.has_official_code)})",
            "",
            "Tier distribution:",
        ]
        for tier, count in sorted(self.tier_distribution().items()):
            lines.append(f"  {tier:<30} {count}")
        lines += ["", "Top reproducibility blockers:"]
        for blocker, count in self.top_blockers():
            lines.append(f"  [{count}x] {blocker}")
        return "\n".join(lines)


# ── Tests ──────────────────────────────────────────────────────────────────

def test_audit_tier_high():
    a = PaperAudit("x", "t", "v", 2020, "d", True, 9.0)
    assert a.tier == "Highly Reproducible"

def test_audit_tier_medium():
    a = PaperAudit("x", "t", "v", 2020, "d", True, 6.0)
    assert a.tier == "Partially Reproducible"

def test_audit_tier_low():
    a = PaperAudit("x", "t", "v", 2020, "d", False, 3.0)
    assert a.tier == "Difficult to Reproduce"

def test_mean_score():
    audits = [PaperAudit("a","t","v",2020,"d",True,8.0),
              PaperAudit("b","t","v",2020,"d",True,6.0)]
    agg = ReproducibilityAggregator(audits)
    assert abs(agg.mean_score() - 7.0) < 0.01

def test_mean_score_empty():
    assert ReproducibilityAggregator([]).mean_score() == 0.0

def test_score_by_domain():
    audits = [PaperAudit("a","t","v",2020,"NLP",True,8.0),
              PaperAudit("b","t","v",2020,"CV",True,9.0),
              PaperAudit("c","t","v",2020,"NLP",True,6.0)]
    agg = ReproducibilityAggregator(audits)
    by_domain = agg.score_by_domain()
    assert abs(by_domain["NLP"] - 7.0) < 0.01
    assert by_domain["CV"] == 9.0

def test_official_code_delta_positive():
    eff = ReproducibilityAggregator(AUDITS).official_code_effect()
    assert eff["delta"] > 0  # papers with code score higher

def test_tier_distribution_covers_all():
    dist = ReproducibilityAggregator(AUDITS).tier_distribution()
    total = sum(dist.values())
    assert total == len(AUDITS)

def test_top_blockers_returns_list():
    blockers = ReproducibilityAggregator(AUDITS).top_blockers(3)
    assert isinstance(blockers, list)
    assert len(blockers) <= 3

def test_report_is_string():
    report = ReproducibilityAggregator(AUDITS).report()
    assert isinstance(report, str)
    assert "Mean score" in report

def test_all_audits_have_scores():
    for a in AUDITS:
        assert 0 <= a.score <= 10

def test_full_audit_count():
    assert len(AUDITS) == 12


if __name__ == "__main__":
    agg = ReproducibilityAggregator(AUDITS)
    print(agg.report())
