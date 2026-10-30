.PHONY: all test lint typecheck bench clean install venv

PYTHON   := .venv/bin/python
PYTEST   := .venv/bin/pytest
PIP      := .venv/bin/pip

# ── Setup ────────────────────────────────────────────────────────────────────

venv:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install pytest pytest-cov z3-solver ruff mypy

install: venv
	$(PIP) install -e . || true

# ── Tests ─────────────────────────────────────────────────────────────────────

test: install
	$(PYTEST) tests/ infra/test_oracle_impl.py -v --tb=short

test-all: install
	$(PYTEST) \
		tests/ \
		infra/test_oracle_impl.py \
		projects/p1_github_issue_fixing/ \
		projects/p2_theorem_proving/theorem_runner.py \
		projects/p3_llvm_superopt/integration_test.py \
		projects/p5_program_synthesis/sygus_solver.py \
		projects/p8_data_structures/benchmarks.py \
		-v --tb=short

test-fast: install
	$(PYTEST) tests/ infra/test_oracle_impl.py -q

coverage: install
	$(PYTEST) tests/ infra/test_oracle_impl.py \
		--cov=infra --cov=projects \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		-q
	@echo "Coverage report: htmlcov/index.html"

# ── Benchmarks ───────────────────────────────────────────────────────────────

bench: install
	$(PYTHON) projects/p8_data_structures/benchmarks.py

bench-synthesis: install
	$(PYTHON) projects/p5_program_synthesis/synthesis_loop.py

# ── Lint / Type ───────────────────────────────────────────────────────────────

lint: venv
	.venv/bin/ruff check . --select=E,W,F --ignore=E501,E402

typecheck: venv
	.venv/bin/mypy infra/ --ignore-missing-imports --no-strict-optional || true

# ── Project-specific runners ─────────────────────────────────────────────────

run-p1: install
	$(PYTHON) -c "from projects.p1_github_issue_fixing.issue_scorer import IssueScorer; \
		s = IssueScorer(); print(s.score.__doc__)"

run-p4: install
	$(PYTHON) projects/p4_protocol_verification/run_tlc.py --help || true

run-p7: install
	$(PYTHON) projects/p7_reproducibility/audit_pipeline.py --help || true

run-p9: install
	$(PYTHON) projects/p9_self_improving/adversarial_tester.py --help || true

# ── Theorem runner ───────────────────────────────────────────────────────────

theorems: install
	$(PYTHON) projects/p2_theorem_proving/theorem_runner.py \
		projects/p2_theorem_proving/hard_theorems.lean

# ── SyGuS ────────────────────────────────────────────────────────────────────

sygus: install
	$(PYTEST) projects/p5_program_synthesis/sygus_solver.py -v

# ── Clean ─────────────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage coverage.xml

distclean: clean
	rm -rf .venv

# ── Help ──────────────────────────────────────────────────────────────────────

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "  install      Set up virtualenv + dependencies"
	@echo "  test         Run core infra tests"
	@echo "  test-all     Run all project tests"
	@echo "  test-fast    Fast smoke tests (no coverage)"
	@echo "  coverage     Run tests with coverage report"
	@echo "  bench        Run data structure benchmarks"
	@echo "  lint         Ruff lint check"
	@echo "  typecheck    Mypy type check"
	@echo "  theorems     Run theorem parser on hard_theorems.lean"
	@echo "  sygus        Run SyGuS solver tests"
	@echo "  clean        Remove build artifacts"
	@echo "  distclean    Remove venv + build artifacts"
