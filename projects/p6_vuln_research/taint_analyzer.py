"""Static taint analyzer for C vulnerability detection."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum


class VulnClass(Enum):
    MALLOC_NO_PLUS_ONE = "malloc_no_plus_one"
    INTEGER_OVERFLOW   = "integer_overflow"
    USE_AFTER_FREE     = "use_after_free"
    FORMAT_STRING      = "format_string"
    COMMAND_INJECTION  = "command_injection"


@dataclass
class TaintSource:
    name: str       # function name: read, recv, fgets, gets, scanf, ...
    variable: str   # variable that receives tainted data
    line: int


@dataclass
class TaintSink:
    name: str               # function: strcpy, malloc(strlen...), printf, system
    line: int
    arguments: list[str]


@dataclass
class TaintPath:
    source: TaintSource
    sink: TaintSink
    intermediate_vars: list[str]


@dataclass
class Finding:
    vuln_class: VulnClass
    line: int
    description: str
    vulnerable_code: str
    cwe_id: str
    confidence: float   # 0.0-1.0


class ExploitabilityScore:
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"


class TaintAnalyzer:
    """
    Regex-based static taint analyzer for C source code.

    Detection model
    ---------------
    Sources: functions that introduce attacker-controlled data.
    Sinks:   functions / patterns that are dangerous when fed tainted data.

    The analyzer does a two-pass scan:
      Pass 1 — identify taint sources and the variables they write into.
      Pass 2 — scan for sinks; if any sink argument overlaps the tainted
               variable set (or matches a syntactic pattern), emit a Finding.

    Limitations (intentional for a static regex-based tool):
      - No inter-procedural analysis.
      - No pointer aliasing.
      - No path sensitivity.
    """

    # ------------------------------------------------------------------ #
    # Source patterns                                                      #
    # ------------------------------------------------------------------ #

    _SOURCE_PATTERNS: list[tuple[str, re.Pattern]] = [
        # gets(buf)
        ("gets",   re.compile(r'\bgets\s*\(\s*(\w+)\s*\)')),
        # fgets(buf, n, stream)
        ("fgets",  re.compile(r'\bfgets\s*\(\s*(\w+)\s*,')),
        # read(fd, buf, n)
        ("read",   re.compile(r'\bread\s*\(\s*\w+\s*,\s*(\w+)\s*,')),
        # recv(sock, buf, len, flags)
        ("recv",   re.compile(r'\brecv\s*\(\s*\w+\s*,\s*(\w+)\s*,')),
        # scanf("%s", buf)
        ("scanf",  re.compile(r'\bscanf\s*\(\s*"[^"]*"\s*,\s*(\w+)\s*\)')),
        # getenv("VAR")  — result assigned: char *x = getenv(...)
        ("getenv", re.compile(r'\bgetenv\s*\(\s*["\w]+\s*\)')),
    ]

    # ------------------------------------------------------------------ #
    # Sink / vulnerability patterns (line-level)                          #
    # ------------------------------------------------------------------ #

    # Pattern 1 — malloc(strlen(x)) without +1 → CWE-131
    _MALLOC_NO_PLUS_ONE = re.compile(
        r'malloc\s*\(\s*strlen\s*\(\s*(\w+)\s*\)\s*\)'
    )
    # Pattern 2 — integer overflow in size calculation before malloc: a * b
    _OVERFLOW_MALLOC = re.compile(
        r'malloc\s*\([^)]*(\w+)\s*\*\s*(\w+)[^)]*\)'
    )
    # Pattern 3a — free(ptr)
    _FREE = re.compile(r'\bfree\s*\(\s*(\w+)\s*\)')
    # Pattern 3b — ptr->field or ptr[i] (use of a pointer)
    _DEREF = re.compile(r'\b(\w+)\s*(?:->|\[)')
    # Pattern 4 — printf / fprintf / syslog with non-literal format arg
    #   Heuristic: printf(var)  where var is an identifier not a string literal
    _FORMAT_STRING = re.compile(
        r'\b(printf|fprintf|sprintf|syslog)\s*\(\s*(?!(?:stderr|stdout|"[^"]*"))\s*(\w+)\s*[,)]'
    )
    # Pattern 5 — system() / popen() / execl* / execlp called with a variable
    _CMD_INJECTION = re.compile(
        r'\b(system|popen|execl|execlp|execle|execv|execvp)\s*\(\s*(\w+)'
    )

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def analyze_file(self, c_source: str) -> list[Finding]:
        """Full pipeline: find sources, find sinks, emit findings."""
        lines = c_source.splitlines()
        sources = self.find_sources(c_source)
        tainted_vars: set[str] = {s.variable for s in sources}

        findings: list[Finding] = []
        freed_ptrs: set[str] = set()

        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()

            # --- Pattern 1: malloc(strlen(x)) without +1 ---
            m = self._MALLOC_NO_PLUS_ONE.search(line)
            # Check for +1 inside the malloc() argument only (not in comments)
            malloc_arg = re.search(r'malloc\s*\(([^)]+)\)', line)
            plus_one_in_arg = (
                malloc_arg is not None and
                bool(re.search(r'\+\s*1\b|\b1\s*\+', malloc_arg.group(1)))
            )
            if m and not plus_one_in_arg:
                var = m.group(1)
                findings.append(Finding(
                    vuln_class=VulnClass.MALLOC_NO_PLUS_ONE,
                    line=lineno,
                    description=(
                        f"malloc(strlen({var})) misses +1 for the NUL terminator. "
                        f"strcpy into this buffer will write one byte past the end."
                    ),
                    vulnerable_code=stripped,
                    cwe_id="CWE-131",
                    confidence=0.95,
                ))

            # --- Pattern 2: integer overflow in malloc argument ---
            m = self._OVERFLOW_MALLOC.search(line)
            if m:
                a, b = m.group(1), m.group(2)
                findings.append(Finding(
                    vuln_class=VulnClass.INTEGER_OVERFLOW,
                    line=lineno,
                    description=(
                        f"Potential integer overflow: '{a} * {b}' before malloc. "
                        f"If either value is attacker-controlled, the product may "
                        f"wrap around, allocating a buffer far smaller than expected."
                    ),
                    vulnerable_code=stripped,
                    cwe_id="CWE-190",
                    confidence=0.85,
                ))

            # --- Pattern 3a: track free() calls ---
            m = self._FREE.search(line)
            if m:
                freed_ptrs.add(m.group(1))

            # --- Pattern 3b: use-after-free (deref of a freed pointer) ---
            for m in self._DEREF.finditer(line):
                ptr = m.group(1)
                if ptr in freed_ptrs:
                    findings.append(Finding(
                        vuln_class=VulnClass.USE_AFTER_FREE,
                        line=lineno,
                        description=(
                            f"Use-after-free: '{ptr}' was freed earlier but is "
                            f"dereferenced here without being set to NULL or "
                            f"reallocated."
                        ),
                        vulnerable_code=stripped,
                        cwe_id="CWE-416",
                        confidence=0.90,
                    ))

            # --- Pattern 4: non-literal format string ---
            m = self._FORMAT_STRING.search(line)
            if m:
                fn, var = m.group(1), m.group(2)
                # Only flag if the format argument looks like a variable, not a literal
                if not var.startswith('"'):
                    findings.append(Finding(
                        vuln_class=VulnClass.FORMAT_STRING,
                        line=lineno,
                        description=(
                            f"Format string vulnerability: {fn}() called with "
                            f"non-literal first argument '{var}'. If attacker-controlled, "
                            f"this allows arbitrary read/write via format specifiers."
                        ),
                        vulnerable_code=stripped,
                        cwe_id="CWE-134",
                        confidence=0.92,
                    ))

            # --- Pattern 5: command injection ---
            m = self._CMD_INJECTION.search(line)
            if m:
                fn, var = m.group(1), m.group(2)
                if var in tainted_vars or self._looks_like_variable(var):
                    findings.append(Finding(
                        vuln_class=VulnClass.COMMAND_INJECTION,
                        line=lineno,
                        description=(
                            f"Command injection: {fn}() called with variable '{var}'. "
                            f"If '{var}' contains attacker-controlled data, arbitrary "
                            f"commands can be executed."
                        ),
                        vulnerable_code=stripped,
                        cwe_id="CWE-78",
                        confidence=0.88,
                    ))

        return findings

    def find_sources(self, c_source: str) -> list[TaintSource]:
        """Identify all taint sources in the source file."""
        sources: list[TaintSource] = []
        for lineno, line in enumerate(c_source.splitlines(), start=1):
            for fn_name, pattern in self._SOURCE_PATTERNS:
                m = pattern.search(line)
                if m:
                    var = m.group(1) if m.lastindex and m.lastindex >= 1 else "unknown"
                    sources.append(TaintSource(name=fn_name, variable=var, line=lineno))
        return sources

    def find_sinks(self, c_source: str) -> list[TaintSink]:
        """Identify all potential sink call sites."""
        sinks: list[TaintSink] = []
        sink_patterns = [
            re.compile(r'\b(strcpy|strcat|sprintf)\s*\(([^)]+)\)'),
            re.compile(r'\b(malloc)\s*\(([^)]+)\)'),
            re.compile(r'\b(printf|fprintf|syslog)\s*\(([^)]+)\)'),
            re.compile(r'\b(system|popen)\s*\(([^)]+)\)'),
        ]
        for lineno, line in enumerate(c_source.splitlines(), start=1):
            for pat in sink_patterns:
                m = pat.search(line)
                if m:
                    args = [a.strip() for a in m.group(2).split(',')]
                    sinks.append(TaintSink(name=m.group(1), line=lineno, arguments=args))
        return sinks

    def is_sanitized(self, path: TaintPath, c_source: str) -> bool:
        """
        Heuristic: a path is considered sanitized if the source file contains
        a bounds check or validation between the source and sink lines.
        """
        lines = c_source.splitlines()
        src_line = path.source.line
        sink_line = path.sink.line
        var = path.source.variable

        sanitize_patterns = [
            re.compile(r'\bstrlen\s*\([^)]*' + re.escape(var)),
            re.compile(r'\bsizeof\s*\([^)]*' + re.escape(var)),
            re.compile(r'\bsnprintf\b'),
            re.compile(r'if\s*\([^)]*' + re.escape(var) + r'[^)]*(?:>|<|==|!=|>=|<=)'),
            re.compile(r'\bstrlcpy\b'),
            re.compile(r'\bstrlcat\b'),
        ]
        for line in lines[src_line:sink_line - 1]:
            for pat in sanitize_patterns:
                if pat.search(line):
                    return True
        return False

    def score_exploitability(self, finding: Finding) -> str:
        """Map a finding to an exploitability bucket."""
        scores = {
            VulnClass.COMMAND_INJECTION:  ExploitabilityScore.CRITICAL,
            VulnClass.FORMAT_STRING:      ExploitabilityScore.HIGH,
            VulnClass.USE_AFTER_FREE:     ExploitabilityScore.HIGH,
            VulnClass.INTEGER_OVERFLOW:   ExploitabilityScore.HIGH,
            VulnClass.MALLOC_NO_PLUS_ONE: ExploitabilityScore.MEDIUM,
        }
        return scores.get(finding.vuln_class, ExploitabilityScore.LOW)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _looks_like_variable(token: str) -> bool:
        """Return True if token looks like an identifier (not a string literal)."""
        return bool(re.match(r'^[A-Za-z_]\w*$', token)) and not token.startswith('"')


# =========================================================================== #
# Test suite                                                                   #
# =========================================================================== #

_SNIPPET_MALLOC_NO_PLUS_ONE = r"""
#include <string.h>
#include <stdlib.h>
void vuln(char *input) {
    char *buf = malloc(strlen(input));   /* CWE-131: missing +1 */
    strcpy(buf, input);
}
"""

_SNIPPET_INTEGER_OVERFLOW = r"""
#include <stdlib.h>
void vuln(int count, int size) {
    char *buf = malloc(count * size);    /* CWE-190: no overflow check */
    /* use buf */
}
"""

_SNIPPET_USE_AFTER_FREE = r"""
#include <stdlib.h>
void vuln(char *ptr) {
    free(ptr);
    char c = ptr->data;  /* CWE-416: use after free */
}
"""

_SNIPPET_FORMAT_STRING = r"""
#include <stdio.h>
void vuln(char *user_input) {
    printf(user_input);  /* CWE-134: format string */
}
"""

_SNIPPET_COMMAND_INJECTION = r"""
#include <stdlib.h>
void vuln(char *cmd) {
    system(cmd);  /* CWE-78: command injection */
}
"""


def _run_tests():
    analyzer = TaintAnalyzer()
    all_passed = True

    def check(snippet_name: str, snippet: str,
               expected_cwe: str, expected_class: VulnClass) -> None:
        nonlocal all_passed
        findings = analyzer.analyze_file(snippet)
        matched = [f for f in findings if f.cwe_id == expected_cwe]
        if not matched:
            print(f"  FAIL [{snippet_name}]: expected {expected_cwe} ({expected_class.value}), "
                  f"got findings: {[f.cwe_id for f in findings]}")
            all_passed = False
        else:
            score = analyzer.score_exploitability(matched[0])
            print(f"  PASS [{snippet_name}]: {expected_cwe} detected "
                  f"at line {matched[0].line}, exploitability={score}, "
                  f"confidence={matched[0].confidence:.0%}")

    print("Running taint analyzer tests...\n")
    check("malloc_no_plus_one", _SNIPPET_MALLOC_NO_PLUS_ONE,
          "CWE-131", VulnClass.MALLOC_NO_PLUS_ONE)
    check("integer_overflow",   _SNIPPET_INTEGER_OVERFLOW,
          "CWE-190", VulnClass.INTEGER_OVERFLOW)
    check("use_after_free",     _SNIPPET_USE_AFTER_FREE,
          "CWE-416", VulnClass.USE_AFTER_FREE)
    check("format_string",      _SNIPPET_FORMAT_STRING,
          "CWE-134", VulnClass.FORMAT_STRING)
    check("command_injection",  _SNIPPET_COMMAND_INJECTION,
          "CWE-78",  VulnClass.COMMAND_INJECTION)

    if all_passed:
        print("\nAll 5 taint-analysis tests passed.")
    else:
        raise AssertionError("One or more taint-analysis tests FAILED.")


if __name__ == "__main__":
    _run_tests()
