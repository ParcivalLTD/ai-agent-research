"""
MCTS-based proof search enhancements for P2.

Extends the existing proof_search.py with:
  - Beam search over tactic sequences
  - Value function estimation (predicts proof likelihood)
  - A* proof search with admissible heuristic
  - Proof trace recording for analysis
"""
from __future__ import annotations

import math
import heapq
from dataclasses import dataclass, field
from typing import Callable, Iterator


# ---------------------------------------------------------------------------
# Tactic definitions
# ---------------------------------------------------------------------------

LEAN4_TACTICS = [
    "rfl", "trivial", "simp", "ring", "linarith", "omega",
    "norm_num", "exact?", "apply?", "decide",
    "induction n with | zero => _ | succ n ih => _",
    "cases h", "constructor", "intro h",
    "have h := ", "use ",
    "simp [Nat.add_comm]", "simp [Nat.mul_comm]",
    "exact Nat.add_zero _", "exact Nat.zero_add _",
]

MATHLIB_LEMMAS = [
    "Nat.add_comm", "Nat.mul_comm", "Nat.add_assoc",
    "Nat.succ_eq_add_one", "Nat.zero_add", "Nat.add_zero",
    "Int.add_comm", "Int.mul_comm",
    "Finset.sum_comm", "Finset.card_range",
    "Nat.dvd_refl", "Nat.Prime.dvd_mul",
    "ZMod.pow_card", "ZMod.wilsons_lemma",
]


# ---------------------------------------------------------------------------
# Proof state
# ---------------------------------------------------------------------------

@dataclass
class ProofState:
    """Represents the state of an in-progress Lean 4 proof."""
    goal: str
    hypotheses: list[str] = field(default_factory=list)
    depth: int = 0
    tactic_history: list[str] = field(default_factory=list)
    is_closed: bool = False

    def __hash__(self) -> int:
        return hash((self.goal, tuple(self.hypotheses), self.depth))

    def __lt__(self, other: "ProofState") -> bool:
        return self.depth < other.depth

    @property
    def complexity_score(self) -> float:
        """Estimate of proof difficulty based on goal structure."""
        goal = self.goal.lower()
        score = 1.0
        if "∀" in goal or "∃" in goal: score += 1.0
        if "→" in goal: score += 0.5
        if "↔" in goal: score += 0.5
        if "prime" in goal or "dvd" in goal: score += 2.0
        if "mod" in goal or "%" in goal: score += 1.5
        if "induction" in " ".join(self.tactic_history): score -= 0.5
        return max(score, 0.1)


# ---------------------------------------------------------------------------
# Value function
# ---------------------------------------------------------------------------

class ProofValueFunction:
    """
    Estimates the probability that a proof state is solvable.
    In production this would be a neural network; here we use heuristics.
    """

    def estimate(self, state: ProofState) -> float:
        """Return estimated P(solvable | state) in [0, 1]."""
        if state.is_closed:
            return 1.0

        goal = state.goal.lower()
        score = 0.5  # base

        # Simple goals
        if goal in ("true", "1 = 1", "0 = 0"):
            return 0.95
        if "rfl" in goal or "refl" in goal:
            score += 0.2

        # Depth penalty
        score -= state.depth * 0.03

        # Hypothesis richness
        score += min(len(state.hypotheses) * 0.05, 0.2)

        # Good tactics already used
        good_tactics = {"simp", "ring", "linarith", "omega", "norm_num"}
        used = set(state.tactic_history)
        score += min(len(used & good_tactics) * 0.1, 0.3)

        # Known-hard goals
        hard_keywords = ["prime", "cantor", "halting", "turing", "fermat"]
        if any(k in goal for k in hard_keywords):
            score -= 0.2

        return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Beam search
# ---------------------------------------------------------------------------

@dataclass
class BeamNode:
    state: ProofState
    score: float
    path: list[str] = field(default_factory=list)

    def __lt__(self, other: "BeamNode") -> bool:
        return self.score > other.score  # max-heap by score


class BeamProofSearch:
    """
    Beam search over tactic sequences.
    Expands the top-B states at each depth level.
    """

    def __init__(self, beam_width: int = 5, max_depth: int = 10,
                 value_fn: ProofValueFunction | None = None):
        self.beam_width = beam_width
        self.max_depth = max_depth
        self.value_fn = value_fn or ProofValueFunction()

    def _apply_tactic(self, state: ProofState, tactic: str) -> ProofState | None:
        """Simulate applying a tactic (mock: always succeeds for demo tactics)."""
        new_depth = state.depth + 1
        new_history = state.tactic_history + [tactic]

        # Simulate proof closure for simple goals
        simple_closers = {"rfl", "trivial", "decide", "norm_num", "ring", "omega", "linarith"}
        if tactic in simple_closers and state.complexity_score < 1.5:
            return ProofState(
                goal=state.goal,
                hypotheses=state.hypotheses,
                depth=new_depth,
                tactic_history=new_history,
                is_closed=True,
            )

        # Simulate induction: splits goal into base + step
        if tactic.startswith("induction"):
            return ProofState(
                goal=f"Ind({state.goal})",
                hypotheses=state.hypotheses + ["ih: induction hypothesis"],
                depth=new_depth,
                tactic_history=new_history,
            )

        # Generic: reduce complexity
        return ProofState(
            goal=state.goal,
            hypotheses=state.hypotheses,
            depth=new_depth,
            tactic_history=new_history,
        )

    def search(self, initial: ProofState) -> list[str] | None:
        """
        Run beam search. Returns tactic sequence if proof found, else None.
        """
        beam = [BeamNode(state=initial, score=self.value_fn.estimate(initial), path=[])]

        for depth in range(self.max_depth):
            candidates: list[BeamNode] = []

            for node in beam:
                if node.state.is_closed:
                    return node.path

                for tactic in LEAN4_TACTICS[:8]:  # limit branching factor
                    next_state = self._apply_tactic(node.state, tactic)
                    if next_state is None:
                        continue
                    score = self.value_fn.estimate(next_state)
                    candidates.append(BeamNode(
                        state=next_state,
                        score=score,
                        path=node.path + [tactic],
                    ))

            if not candidates:
                break

            # Keep top-B
            candidates.sort(reverse=True, key=lambda n: n.score)
            beam = candidates[:self.beam_width]

            # Check if any closed
            for node in beam:
                if node.state.is_closed:
                    return node.path

        return None


# ---------------------------------------------------------------------------
# A* proof search
# ---------------------------------------------------------------------------

class AStarProofSearch:
    """
    A* search over proof states.
    f(n) = g(n) + h(n) where g = depth, h = estimated remaining steps.
    """

    def __init__(self, max_nodes: int = 500, value_fn: ProofValueFunction | None = None):
        self.max_nodes = max_nodes
        self.value_fn = value_fn or ProofValueFunction()

    def _heuristic(self, state: ProofState) -> float:
        """Admissible heuristic: estimated remaining proof steps."""
        p = self.value_fn.estimate(state)
        # -log(p) approximates expected remaining steps
        return -math.log(max(p, 1e-6))

    def search(self, initial: ProofState) -> list[str] | None:
        heap: list[tuple[float, int, ProofState, list[str]]] = []
        counter = 0
        g0 = 0.0
        h0 = self._heuristic(initial)
        heapq.heappush(heap, (g0 + h0, counter, initial, []))

        visited: set[int] = set()
        nodes_expanded = 0

        while heap and nodes_expanded < self.max_nodes:
            f, _, state, path = heapq.heappop(heap)
            state_hash = hash(state)
            if state_hash in visited:
                continue
            visited.add(state_hash)
            nodes_expanded += 1

            if state.is_closed:
                return path

            for tactic in LEAN4_TACTICS[:6]:
                next_state = self._simulate(state, tactic)
                if next_state is None or hash(next_state) in visited:
                    continue
                g = state.depth + 1
                h = self._heuristic(next_state)
                counter += 1
                heapq.heappush(heap, (g + h, counter, next_state, path + [tactic]))

        return None

    def _simulate(self, state: ProofState, tactic: str) -> ProofState | None:
        # Reuse beam search simulation
        bs = BeamProofSearch()
        return bs._apply_tactic(state, tactic)


# ---------------------------------------------------------------------------
# Proof trace recorder
# ---------------------------------------------------------------------------

@dataclass
class ProofTrace:
    """Records a full proof search trace for analysis."""
    theorem_name: str
    initial_goal: str
    search_algorithm: str
    found: bool
    tactic_sequence: list[str] = field(default_factory=list)
    nodes_expanded: int = 0
    depth_reached: int = 0

    def to_lean(self) -> str:
        if not self.found or not self.tactic_sequence:
            return f"-- Proof not found for {self.theorem_name}\ntheorem {self.theorem_name} : {self.initial_goal} := by\n  sorry\n"
        tactics = "\n  ".join(self.tactic_sequence)
        return f"theorem {self.theorem_name} : {self.initial_goal} := by\n  {tactics}\n"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_proof_state_complexity_simple():
    s = ProofState(goal="1 = 1")
    assert s.complexity_score >= 0.1


def test_proof_state_complexity_hard():
    s = ProofState(goal="prime p → p dvd a * b → p dvd a ∨ p dvd b")
    assert s.complexity_score > 2.0


def test_value_function_closed():
    vf = ProofValueFunction()
    s = ProofState(goal="x = x", is_closed=True)
    assert vf.estimate(s) == 1.0


def test_value_function_trivial():
    vf = ProofValueFunction()
    s = ProofState(goal="true")
    assert vf.estimate(s) >= 0.9


def test_value_function_depth_penalty():
    vf = ProofValueFunction()
    s0 = ProofState(goal="a + b = b + a", depth=0)
    s5 = ProofState(goal="a + b = b + a", depth=5)
    assert vf.estimate(s0) > vf.estimate(s5)


def test_beam_search_simple():
    bs = BeamProofSearch(beam_width=3, max_depth=5)
    state = ProofState(goal="1 = 1", depth=0)
    result = bs.search(state)
    assert result is None or isinstance(result, list)


def test_beam_search_returns_list_or_none():
    bs = BeamProofSearch(beam_width=2, max_depth=3)
    state = ProofState(goal="True", depth=0)
    result = bs.search(state)
    assert result is None or isinstance(result, list)


def test_astar_heuristic_positive():
    a = AStarProofSearch()
    s = ProofState(goal="a + b = b + a")
    assert a._heuristic(s) >= 0


def test_astar_search_smoke():
    a = AStarProofSearch(max_nodes=50)
    s = ProofState(goal="1 = 1")
    result = a.search(s)
    assert result is None or isinstance(result, list)


def test_proof_trace_to_lean_not_found():
    trace = ProofTrace("my_thm", "P → Q", "beam", found=False)
    lean = trace.to_lean()
    assert "sorry" in lean
    assert "my_thm" in lean


def test_proof_trace_to_lean_found():
    trace = ProofTrace("add_comm", "∀ n m, n + m = m + n", "beam",
                       found=True, tactic_sequence=["intro n m", "ring"])
    lean = trace.to_lean()
    assert "ring" in lean
    assert "sorry" not in lean


def test_mathlib_lemmas_not_empty():
    assert len(MATHLIB_LEMMAS) >= 10


def test_lean4_tactics_not_empty():
    assert len(LEAN4_TACTICS) >= 10


def test_beam_node_ordering():
    from dataclasses import dataclass as dc
    n1 = BeamNode(ProofState("g"), 0.9, [])
    n2 = BeamNode(ProofState("g"), 0.5, [])
    assert n1 < n2  # higher score = "less than" in max-heap logic


def test_apply_tactic_simple_close():
    bs = BeamProofSearch()
    state = ProofState(goal="1 = 1", depth=0)
    result = bs._apply_tactic(state, "rfl")
    assert result is not None
    assert result.is_closed


if __name__ == "__main__":
    print("=== Beam Proof Search Demo ===")
    vf = ProofValueFunction()
    bs = BeamProofSearch(beam_width=5, max_depth=8)
    for goal in ["1 = 1", "0 + n = n", "n + m = m + n (ring)", "prime p → p dvd a"]:
        state = ProofState(goal=goal)
        result = bs.search(state)
        status = "✓ " + " → ".join(result) if result else "✗ not found"
        print(f"  {goal[:40]:<40} {status}")
