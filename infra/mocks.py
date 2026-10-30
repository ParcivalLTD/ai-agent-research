"""
Mock implementations for all oracles and the LLM backend.

Used in unit tests and integration tests without spending real tokens.
"""

from __future__ import annotations

from typing import Optional

from infra.oracle import FormalOracleInterface, OracleResult


class MockOracle(FormalOracleInterface):
    """
    Configurable mock oracle.

    Pass a sequence of OracleResult objects; they are returned round-robin.
    Useful for testing the refinement loop without running any external tool.

    Usage::

        oracle = MockOracle(results=[
            OracleResult(success=False, error_message="syntax error"),
            OracleResult(success=True),
        ])
    """

    def __init__(self, results: Optional[list[OracleResult]] = None) -> None:
        self._results = results or [OracleResult(success=True)]
        self._call_index = 0
        self.calls: list[str] = []  # every spec passed to check()

    def is_available(self) -> bool:
        return True

    def check(self, spec: str) -> OracleResult:
        self.calls.append(spec)
        result = self._results[self._call_index % len(self._results)]
        self._call_index += 1
        return result


class MockLLM:
    """
    Deterministic mock LLM backend.

    Returns a fixed response unless a custom ``respond`` callable is
    provided (receives the prompt, returns (text, p_tok, c_tok)).

    Usage::

        llm = MockLLM(response="theorem foo : True := trivial")
        # or
        llm = MockLLM(respond=lambda p: (f"fixed({len(p)})", 10, 5))
    """

    def __init__(
        self,
        response: str = "mock_proposal",
        respond=None,
        prompt_tokens: int = 100,
        completion_tokens: int = 50,
    ) -> None:
        self._response = response
        self._respond = respond
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self.calls: list[str] = []

    def complete(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> tuple[str, int, int]:
        self.calls.append(prompt)
        if self._respond:
            return self._respond(prompt)
        return self._response, self._prompt_tokens, self._completion_tokens
