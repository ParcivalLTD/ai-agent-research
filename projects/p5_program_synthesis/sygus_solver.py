"""
SyGuS (Syntax-Guided Synthesis) solver.

Enumerate-and-verify approach: depth-limited enumeration over the grammar,
then evaluate each candidate against all input/output examples.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Generator

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SyGUSProblem:
    """A SyGuS problem instance."""

    grammar: dict[str, list[str]]
    """Non-terminal → list of production rules (strings with embedded NTs)."""

    constraints: list[tuple]
    """List of (env_dict, expected_output) pairs."""

    max_depth: int = 5
    """Maximum AST depth for enumeration."""


# ---------------------------------------------------------------------------
# Expression evaluator
# ---------------------------------------------------------------------------

def _tokenize(expr: str) -> list[str]:
    """Tokenize a parenthesised expression into atoms and parens."""
    tokens: list[str] = []
    cur = ""
    for ch in expr:
        if ch in "()":
            if cur.strip():
                tokens.append(cur.strip())
            cur = ""
            tokens.append(ch)
        elif ch == " ":
            if cur.strip():
                tokens.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        tokens.append(cur.strip())
    return tokens


def _parse(tokens: list[str], pos: int) -> tuple:
    """Recursive descent parser → (ast_node, new_pos)."""
    tok = tokens[pos]
    if tok == "(":
        pos += 1  # consume '('
        children = []
        while tokens[pos] != ")":
            node, pos = _parse(tokens, pos)
            children.append(node)
        pos += 1  # consume ')'
        return (children[0], children[1:]), pos
    else:
        return tok, pos + 1


def eval_expr(expr: str, env: dict[str, int]) -> int | bool:
    """Evaluate a mini-language expression string given variable bindings."""
    expr = expr.strip()
    tokens = _tokenize(expr)
    ast, _ = _parse(tokens, 0)
    return _eval_ast(ast, env)


def _eval_ast(ast, env: dict[str, int]) -> int | bool:
    # Atom
    if isinstance(ast, str):
        if ast == "true":
            return True
        if ast == "false":
            return False
        if ast.lstrip("-").isdigit():
            return int(ast)
        return env[ast]

    # Compound: (op, [arg1, arg2, ...])
    op, args = ast
    if op == "+":
        return _eval_ast(args[0], env) + _eval_ast(args[1], env)
    if op == "-":
        if len(args) == 1:
            return -_eval_ast(args[0], env)
        return _eval_ast(args[0], env) - _eval_ast(args[1], env)
    if op == "*":
        return _eval_ast(args[0], env) * _eval_ast(args[1], env)
    if op == "mod":
        return _eval_ast(args[0], env) % _eval_ast(args[1], env)
    if op == "div":
        a = _eval_ast(args[0], env)
        b = _eval_ast(args[1], env)
        # truncate toward zero (SMT-LIB semantics)
        return int(a / b) if b != 0 else 0
    if op == "<":
        return _eval_ast(args[0], env) < _eval_ast(args[1], env)
    if op == "<=":
        return _eval_ast(args[0], env) <= _eval_ast(args[1], env)
    if op == ">":
        return _eval_ast(args[0], env) > _eval_ast(args[1], env)
    if op == ">=":
        return _eval_ast(args[0], env) >= _eval_ast(args[1], env)
    if op == "=":
        return _eval_ast(args[0], env) == _eval_ast(args[1], env)
    if op == "and":
        return _eval_ast(args[0], env) and _eval_ast(args[1], env)
    if op == "or":
        return _eval_ast(args[0], env) or _eval_ast(args[1], env)
    if op == "not":
        return not _eval_ast(args[0], env)
    if op == "ite":
        cond = _eval_ast(args[0], env)
        return _eval_ast(args[1], env) if cond else _eval_ast(args[2], env)
    if op == "bitand":
        return _eval_ast(args[0], env) & _eval_ast(args[1], env)
    if op == "bitor":
        return _eval_ast(args[0], env) | _eval_ast(args[1], env)
    if op == "bitxor":
        return _eval_ast(args[0], env) ^ _eval_ast(args[1], env)
    if op == "abs":
        v = _eval_ast(args[0], env)
        return abs(v)
    raise ValueError(f"Unknown operator: {op}")


# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------

class SyGUSSolver:
    """Enumerate-and-verify SyGuS solver."""

    # ------------------------------------------------------------------
    # Enumeration — AST-based, depth-limited
    # ------------------------------------------------------------------

    def _gen(
        self,
        nt: str,
        grammar: dict[str, list[str]],
        depth: int,
    ) -> Generator[str, None, None]:
        """Yield all terminal strings derivable from non-terminal *nt*
        within tree depth *depth* (0 = terminals only)."""
        for prod in grammar[nt]:
            # Collect the NTs that appear in this production (in order)
            # A production may contain multiple NTs; we enumerate their
            # Cartesian product of expansions.
            yield from self._fill(prod, grammar, depth)

    def _fill(
        self,
        template: str,
        grammar: dict[str, list[str]],
        depth: int,
    ) -> Generator[str, None, None]:
        """Replace every NT in *template* (left-to-right) with an expansion
        at depth-1, yielding all combinations."""
        # Find leftmost NT
        best_pos = len(template)
        best_nt = None
        for nt in grammar:
            idx = template.find(nt)
            if idx != -1 and idx < best_pos:
                best_pos = idx
                best_nt = nt

        if best_nt is None:
            # Pure terminal — yield as-is
            yield template
            return

        if depth <= 0:
            # No budget left; only accept terminal productions for this NT
            for prod in grammar[best_nt]:
                if not any(s in prod for s in grammar):
                    rest = template[:best_pos] + prod + template[best_pos + len(best_nt):]
                    yield from self._fill(rest, grammar, 0)
            return

        for prod in grammar[best_nt]:
            # Expand this production's own NTs at depth-1
            for filled_prod in self._fill(prod, grammar, depth - 1):
                rest = template[:best_pos] + filled_prod + template[best_pos + len(best_nt):]
                yield from self._fill(rest, grammar, depth)

    def enumerate(self, problem: SyGUSProblem) -> Generator[str, None, None]:
        """Yield candidate programs depth-by-depth (iterative deepening)."""
        start = next(iter(problem.grammar))
        seen: set[str] = set()
        for d in range(problem.max_depth + 1):
            for candidate in self._gen(start, problem.grammar, d):
                if candidate not in seen:
                    seen.add(candidate)
                    yield candidate

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(
        self,
        candidate: str,
        constraints: list[tuple],
    ) -> bool:
        """Return True iff *candidate* satisfies all (env, expected) pairs."""
        for env, expected in constraints:
            try:
                result = eval_expr(candidate, env)
                if result != expected:
                    return False
            except Exception:
                return False
        return True

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------

    def solve(self, problem: SyGUSProblem, timeout: float = 10.0) -> str | None:
        """Return the first correct program, or None if timeout is reached."""
        deadline = time.monotonic() + timeout
        for candidate in self.enumerate(problem):
            if time.monotonic() > deadline:
                return None
            if self.verify(candidate, problem.constraints):
                return candidate
        return None


# ---------------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------------

_FULL_GRAMMAR: dict[str, list[str]] = {
    "E": [
        "x", "y", "z", "lo", "hi", "0", "1", "2",
        "(+ E E)", "(- E E)", "(* E E)",
        "(ite B E E)",
    ],
    "B": [
        "true", "false",
        "(< E E)", "(<= E E)", "(> E E)", "(>= E E)", "(= E E)",
        "(and B B)", "(or B B)", "(not B)",
    ],
}

_SIMPLE_GRAMMAR: dict[str, list[str]] = {
    "E": [
        "x", "y", "0", "1",
        "(+ E E)", "(- E E)",
        "(ite B E E)",
    ],
    "B": [
        "(< E E)", "(= E E)",
    ],
}


def make_max2_problem() -> SyGUSProblem:
    constraints = [
        ({"x": 0, "y": 1}, 1),
        ({"x": 3, "y": 2}, 3),
        ({"x": -1, "y": 0}, 0),
        ({"x": 5, "y": 5}, 5),
    ]
    return SyGUSProblem(grammar=_SIMPLE_GRAMMAR, constraints=constraints, max_depth=4)


def make_abs_problem() -> SyGUSProblem:
    constraints = [
        ({"x": -3}, 3),
        ({"x": 0}, 0),
        ({"x": 4}, 4),
        ({"x": -1}, 1),
    ]
    grammar = {
        "E": ["x", "0", "(- E E)", "(ite B E E)"],
        "B": ["(< E E)", "(= E E)"],
    }
    return SyGUSProblem(grammar=grammar, constraints=constraints, max_depth=4)


def make_clamp_problem() -> SyGUSProblem:
    """clamp(x, lo, hi) = ite(x < lo, lo, ite(x > hi, hi, x))"""
    constraints = [
        ({"x": -5, "lo": 0, "hi": 10}, 0),
        ({"x": 5,  "lo": 0, "hi": 10}, 5),
        ({"x": 15, "lo": 0, "hi": 10}, 10),
        ({"x": 0,  "lo": 0, "hi": 10}, 0),
        ({"x": 10, "lo": 0, "hi": 10}, 10),
    ]
    grammar = {
        "E": ["x", "lo", "hi", "(ite B E E)"],
        "B": ["(< E E)", "(> E E)"],
    }
    return SyGUSProblem(grammar=grammar, constraints=constraints, max_depth=5)


def make_popcount_1bit_problem() -> SyGUSProblem:
    """popcount of a 1-bit number: popcount(x) = x & 1  →  bitand(x,1)"""
    constraints = [
        ({"x": 0}, 0),
        ({"x": 1}, 1),
        ({"x": 2}, 0),
        ({"x": 3}, 1),
    ]
    grammar = {
        "E": ["x", "0", "1", "(bitand E E)"],
        "B": [],
    }
    return SyGUSProblem(grammar=grammar, constraints=constraints, max_depth=3)


# ---------------------------------------------------------------------------
# Tests (pytest)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402


class TestEvalExpr:
    def test_literal_int(self):
        assert eval_expr("3", {}) == 3

    def test_variable(self):
        assert eval_expr("x", {"x": 7}) == 7

    def test_add(self):
        assert eval_expr("(+ x y)", {"x": 2, "y": 3}) == 5

    def test_sub(self):
        assert eval_expr("(- x y)", {"x": 5, "y": 3}) == 2

    def test_mul(self):
        assert eval_expr("(* x y)", {"x": 4, "y": 3}) == 12

    def test_lt(self):
        assert eval_expr("(< x y)", {"x": 1, "y": 2}) is True
        assert eval_expr("(< x y)", {"x": 2, "y": 1}) is False

    def test_eq(self):
        assert eval_expr("(= x y)", {"x": 3, "y": 3}) is True
        assert eval_expr("(= x y)", {"x": 1, "y": 2}) is False

    def test_ite_true(self):
        assert eval_expr("(ite (< x y) x y)", {"x": 1, "y": 2}) == 1

    def test_ite_false(self):
        assert eval_expr("(ite (< x y) x y)", {"x": 3, "y": 2}) == 2

    def test_nested(self):
        # max(x,y) = ite(< x y, y, x)
        assert eval_expr("(ite (< x y) y x)", {"x": 3, "y": 5}) == 5

    def test_true_false_literals(self):
        assert eval_expr("true", {}) is True
        assert eval_expr("false", {}) is False

    def test_bitand(self):
        assert eval_expr("(bitand x y)", {"x": 6, "y": 3}) == 2


class TestVerify:
    def setup_method(self):
        self.solver = SyGUSSolver()

    def test_correct_max2(self):
        constraints = [
            ({"x": 1, "y": 2}, 2),
            ({"x": 3, "y": 1}, 3),
        ]
        assert self.solver.verify("(ite (< x y) y x)", constraints) is True

    def test_incorrect_candidate(self):
        constraints = [
            ({"x": 1, "y": 2}, 2),
            ({"x": 3, "y": 1}, 3),
        ]
        assert self.solver.verify("x", constraints) is False

    def test_exception_safety(self):
        # Bad expression should return False, not raise
        assert self.solver.verify("(/ x 0)", [({}, 0)]) is False


class TestSolveMax2:
    def setup_method(self):
        self.solver = SyGUSSolver()

    def test_solve_returns_string(self):
        prob = make_max2_problem()
        sol = self.solver.solve(prob, timeout=30)
        assert isinstance(sol, str)

    def test_solve_correct_on_examples(self):
        prob = make_max2_problem()
        sol = self.solver.solve(prob, timeout=30)
        assert sol is not None
        assert self.solver.verify(sol, prob.constraints)

    def test_solve_generalises(self):
        prob = make_max2_problem()
        sol = self.solver.solve(prob, timeout=30)
        assert sol is not None
        extra = [({"x": 10, "y": 7}, 10), ({"x": -2, "y": -5}, -2)]
        assert self.solver.verify(sol, extra)


class TestSolveAbs:
    def setup_method(self):
        self.solver = SyGUSSolver()

    def test_solve_abs(self):
        prob = make_abs_problem()
        sol = self.solver.solve(prob, timeout=30)
        assert sol is not None
        assert self.solver.verify(sol, prob.constraints)

    def test_abs_extra(self):
        prob = make_abs_problem()
        sol = self.solver.solve(prob, timeout=30)
        assert sol is not None
        extra = [({"x": -100}, 100), ({"x": 7}, 7)]
        assert self.solver.verify(sol, extra)


class TestSolveClamp:
    def setup_method(self):
        self.solver = SyGUSSolver()

    def test_solve_clamp(self):
        prob = make_clamp_problem()
        sol = self.solver.solve(prob, timeout=30)
        assert sol is not None
        assert self.solver.verify(sol, prob.constraints)

    def test_clamp_boundary(self):
        prob = make_clamp_problem()
        sol = self.solver.solve(prob, timeout=30)
        assert sol is not None
        extra = [
            ({"x": 3, "lo": 3, "hi": 3}, 3),
            ({"x": -1, "lo": 0, "hi": 5}, 0),
            ({"x": 6, "lo": 0, "hi": 5}, 5),
        ]
        assert self.solver.verify(sol, extra)


class TestSolvePopcount:
    def setup_method(self):
        self.solver = SyGUSSolver()

    def test_solve_popcount_1bit(self):
        prob = make_popcount_1bit_problem()
        sol = self.solver.solve(prob, timeout=30)
        assert sol is not None
        assert self.solver.verify(sol, prob.constraints)


class TestEdgeCases:
    def setup_method(self):
        self.solver = SyGUSSolver()

    def test_empty_constraints_any_solution(self):
        """With no constraints every candidate is valid."""
        grammar = {"E": ["0", "1"]}
        prob = SyGUSProblem(grammar=grammar, constraints=[], max_depth=1)
        sol = self.solver.solve(prob, timeout=5)
        assert sol is not None

    def test_timeout_returns_none(self):
        """A very short timeout on a hard problem returns None."""
        prob = make_clamp_problem()
        # 0 second timeout — should not find anything
        sol = self.solver.solve(prob, timeout=0)
        assert sol is None

    def test_enumerate_yields_terminals(self):
        grammar = {"E": ["0", "1", "(+ E E)"]}
        prob = SyGUSProblem(grammar=grammar, constraints=[], max_depth=2)
        candidates = list(self.solver.enumerate(prob))
        assert "0" in candidates
        assert "1" in candidates

    def test_enumerate_respects_max_depth(self):
        grammar = {"E": ["0", "(+ E E)"]}
        prob = SyGUSProblem(grammar=grammar, constraints=[], max_depth=1)
        # depth=1 means we expand one level, producing "(+ 0 0)" etc.
        candidates = set(self.solver.enumerate(prob))
        # No depth-3 nesting should appear
        assert all(c.count("(+") <= 1 for c in candidates)
