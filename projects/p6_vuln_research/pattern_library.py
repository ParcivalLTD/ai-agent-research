"""
pattern_library.py — P6 Vulnerability Research
================================================
A Python module that defines a VulnerabilityPatternLibrary with 15 patterns
derived from the CVE forensic analysis.  Each pattern is a dataclass with a
C-source regex, severity, and detection method.  PatternMatcher.scan() returns
PatternMatch results for every hit found in a C source string.

Usage
-----
    from pattern_library import PatternMatcher, VulnerabilityPatternLibrary

    with open("target.c") as f:
        source = f.read()
    matches = PatternMatcher().scan(source)
    for m in matches:
        print(m)

Running this file directly executes the built-in test suite.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


# ---------------------------------------------------------------------------
# Severity enumeration
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"
    INFO     = "INFO"


# ---------------------------------------------------------------------------
# Detection method enumeration
# ---------------------------------------------------------------------------

class DetectionMethod(str, Enum):
    TAINT_ANALYSIS          = "TAINT_ANALYSIS"
    BUFFER_BOUND_ANALYSIS   = "BUFFER_BOUND_ANALYSIS"
    INTEGER_OVERFLOW        = "INTEGER_OVERFLOW"
    USE_AFTER_FREE          = "USE_AFTER_FREE"
    RACE_CONDITION          = "RACE_CONDITION"
    INJECTION               = "INJECTION"
    FORMAT_STRING           = "FORMAT_STRING"
    NULL_DEREFERENCE        = "NULL_DEREFERENCE"
    LIFETIME_ANALYSIS       = "LIFETIME_ANALYSIS"
    ALLOCATION_SIZE_MISMATCH = "ALLOCATION_SIZE_MISMATCH"


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VulnerabilityPattern:
    """A single vulnerability pattern definition."""
    name: str
    description: str
    # Regex pattern applied line-by-line to C source code.
    # Must be a valid Python regex.
    c_code_pattern: str
    severity: Severity
    detection_method: DetectionMethod
    cwe_id: str          # e.g. "CWE-122"
    cvss_score: float    # representative CVSS v3.1 base score
    example_cves: tuple[str, ...] = field(default_factory=tuple)

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.c_code_pattern)


@dataclass
class PatternMatch:
    """A single match produced by PatternMatcher.scan()."""
    pattern_name: str
    line_number: int         # 1-based
    matched_text: str        # the matched portion of the line
    confidence: float        # 0.0 – 1.0  (heuristic)
    cwe_id: str

    def __str__(self) -> str:
        return (
            f"[{self.cwe_id}] {self.pattern_name} "
            f"(line {self.line_number}, confidence={self.confidence:.0%}): "
            f"{self.matched_text!r}"
        )


# ---------------------------------------------------------------------------
# Pattern library
# ---------------------------------------------------------------------------

class VulnerabilityPatternLibrary:
    """
    A registry of 15 vulnerability patterns covering the major classes seen
    in the CVE forensic analysis.  Patterns are intentionally kept as
    line-level regexes; more precise detection requires dataflow analysis.
    """

    # 15 patterns — one per list entry
    PATTERNS: ClassVar[list[VulnerabilityPattern]] = [

        # 1. Off-by-one: malloc(strlen(x)) without +1 — CVE-2021-3156 family
        VulnerabilityPattern(
            name="MALLOC_STRLEN_NO_PLUS_ONE",
            description=(
                "malloc(strlen(x)) allocates strlen(x) bytes but strcpy/memcpy will "
                "write strlen(x)+1 bytes (including null terminator), causing a one-byte "
                "heap overflow.  Root of CVE-2021-3156 (Baron Samedit)."
            ),
            c_code_pattern=r"\bmalloc\s*\(\s*strlen\s*\([^)]+\)\s*\)",
            severity=Severity.HIGH,
            detection_method=DetectionMethod.BUFFER_BOUND_ANALYSIS,
            cwe_id="CWE-193",
            cvss_score=7.8,
            example_cves=("CVE-2021-3156", "CVE-2016-6289"),
        ),

        # 2. Unbounded strcpy from external / tainted source
        VulnerabilityPattern(
            name="STRCPY_UNBOUNDED",
            description=(
                "strcpy() copies until null terminator with no length bound.  If the "
                "source is longer than the destination buffer, a stack or heap overflow "
                "results.  Classic CWE-120."
            ),
            c_code_pattern=r"\bstrcpy\s*\(\s*\w+\s*,\s*\w+\s*\)",
            severity=Severity.HIGH,
            detection_method=DetectionMethod.BUFFER_BOUND_ANALYSIS,
            cwe_id="CWE-120",
            cvss_score=7.5,
            example_cves=("CVE-2015-7547",),
        ),

        # 3. gets() — always unsafe (no length parameter at all)
        VulnerabilityPattern(
            name="GETS_USAGE",
            description=(
                "gets() reads input with no length limit, making any program using it "
                "unconditionally vulnerable to stack buffer overflow.  Removed from C11."
            ),
            c_code_pattern=r"\bgets\s*\(\s*\w+\s*\)",
            severity=Severity.CRITICAL,
            detection_method=DetectionMethod.BUFFER_BOUND_ANALYSIS,
            cwe_id="CWE-242",
            cvss_score=9.8,
            example_cves=(),
        ),

        # 4. Integer overflow: 32-bit multiplication into size_t / malloc size
        #    Pattern: (uint32/int/unsigned) * (uint32/int/unsigned) as malloc argument
        VulnerabilityPattern(
            name="INT_OVERFLOW_MALLOC_SIZE",
            description=(
                "A 32-bit × 32-bit multiplication whose result is passed directly to "
                "malloc/calloc/realloc without widening to size_t first.  If both "
                "operands are attacker-controlled the product wraps, under-allocating "
                "the buffer.  CVE-2022-0185, CVE-2019-11477."
            ),
            c_code_pattern=r"\b(?:malloc|realloc|krealloc)\s*\(\s*\w+\s*\*\s*\w+\s*\)",
            severity=Severity.HIGH,
            detection_method=DetectionMethod.INTEGER_OVERFLOW,
            cwe_id="CWE-190",
            cvss_score=8.4,
            example_cves=("CVE-2022-0185", "CVE-2019-11477"),
        ),

        # 5. Heartbleed pattern: memcpy with length from network without bounds check
        #    Heuristic: memcpy where the length variable comes right after a network read
        VulnerabilityPattern(
            name="MEMCPY_UNCHECKED_LEN",
            description=(
                "memcpy() called with a length value that originates from network/user "
                "input (recv, read, recvfrom) without a preceding bounds check.  "
                "CVE-2014-0160 (Heartbleed) archetype."
            ),
            c_code_pattern=r"\bmemcpy\s*\([^,]+,[^,]+,\s*(?:payload|length|len|size|n|count)\s*\)",
            severity=Severity.HIGH,
            detection_method=DetectionMethod.TAINT_ANALYSIS,
            cwe_id="CWE-125",
            cvss_score=7.5,
            example_cves=("CVE-2014-0160",),
        ),

        # 6. Use-after-free: free() followed by dereference with same variable name
        VulnerabilityPattern(
            name="FREE_THEN_USE",
            description=(
                "A pointer is freed and then dereferenced without being set to NULL "
                "first.  Compiler-level alias analysis cannot always catch this across "
                "function calls.  CVE-2020-8616 (BIND 9), CVE-2021-30551."
            ),
            c_code_pattern=r"\bfree\s*\(\s*(\w+)\s*\)",
            severity=Severity.CRITICAL,
            detection_method=DetectionMethod.USE_AFTER_FREE,
            cwe_id="CWE-416",
            cvss_score=9.0,
            example_cves=("CVE-2020-8616",),
        ),

        # 7. Missing NULL check after malloc/calloc
        VulnerabilityPattern(
            name="MALLOC_NO_NULL_CHECK",
            description=(
                "malloc/calloc return value used without NULL check.  On memory-pressure "
                "or OOM conditions the null pointer is dereferenced."
            ),
            c_code_pattern=r"=\s*(?:malloc|calloc|realloc)\s*\([^;]+\);\s*\n\s*(?!if\s*\()",
            severity=Severity.MEDIUM,
            detection_method=DetectionMethod.NULL_DEREFERENCE,
            cwe_id="CWE-476",
            cvss_score=5.9,
            example_cves=(),
        ),

        # 8. Format string: printf(user_input) — no format string
        VulnerabilityPattern(
            name="PRINTF_FORMAT_STRING",
            description=(
                "printf/fprintf/syslog called with a user-controlled string as the "
                "format argument rather than a literal.  Enables arbitrary read/write "
                "via %n, %s, %x specifiers."
            ),
            c_code_pattern=r"\b(?:printf|fprintf|syslog|snprintf)\s*\(\s*(?:stderr|stdout|fd,\s*)?\s*(?:buf|msg|str|input|data|user|req)\s*[,)]",
            severity=Severity.HIGH,
            detection_method=DetectionMethod.FORMAT_STRING,
            cwe_id="CWE-134",
            cvss_score=8.1,
            example_cves=(),
        ),

        # 9. sprintf without bounds — should be snprintf
        VulnerabilityPattern(
            name="SPRINTF_UNBOUNDED",
            description=(
                "sprintf() writes to a fixed-size buffer with no length limit.  "
                "Any input string longer than the destination triggers a buffer overflow."
            ),
            c_code_pattern=r"\bsprintf\s*\(",
            severity=Severity.HIGH,
            detection_method=DetectionMethod.BUFFER_BOUND_ANALYSIS,
            cwe_id="CWE-120",
            cvss_score=7.5,
            example_cves=(),
        ),

        # 10. Stack-allocated VLA / alloca with unchecked size — CVE-2015-7547 family
        VulnerabilityPattern(
            name="ALLOCA_UNCHECKED_SIZE",
            description=(
                "alloca() or VLA with an attacker-influenced size.  Because alloca "
                "allocates on the stack, an overflow immediately corrupts the return "
                "address.  No heap metadata to corrupt first."
            ),
            c_code_pattern=r"\balloca\s*\(\s*\w+\s*\)",
            severity=Severity.HIGH,
            detection_method=DetectionMethod.BUFFER_BOUND_ANALYSIS,
            cwe_id="CWE-121",
            cvss_score=8.1,
            example_cves=("CVE-2015-7547",),
        ),

        # 11. Integer truncation: assignment from wider to narrower type
        #     Heuristic: cast to unsigned short / uint16_t on network-derived value
        VulnerabilityPattern(
            name="INT_TRUNCATION_CAST",
            description=(
                "Explicit cast from a wider integer type (uint32_t, size_t, long) to "
                "a narrower type (uint16_t, unsigned short, int) silently truncates "
                "attacker-controlled values.  CVE-2019-11477 style."
            ),
            c_code_pattern=r"\(\s*(?:uint16_t|unsigned short|u16|__u16)\s*\)\s*\w+",
            severity=Severity.MEDIUM,
            detection_method=DetectionMethod.INTEGER_OVERFLOW,
            cwe_id="CWE-197",
            cvss_score=6.5,
            example_cves=("CVE-2019-11477",),
        ),

        # 12. Signed integer used as array index / size without range check
        VulnerabilityPattern(
            name="SIGNED_INDEX_NO_CHECK",
            description=(
                "A signed integer value (int, ssize_t) used directly as an array index "
                "or memcpy length without a positive-range check.  Negative values cause "
                "out-of-bounds reads/writes or wrap to huge unsigned sizes."
            ),
            c_code_pattern=r"\bssize_t\s+\w+\s*=\s*(?:read|recv|recvfrom)\s*\(",
            severity=Severity.HIGH,
            detection_method=DetectionMethod.INTEGER_OVERFLOW,
            cwe_id="CWE-195",
            cvss_score=7.5,
            example_cves=(),
        ),

        # 13. Dangerous system()/popen() with user-influenced argument — injection
        VulnerabilityPattern(
            name="SYSTEM_COMMAND_INJECTION",
            description=(
                "system() or popen() called with a string that includes or is derived "
                "from user input without shell-metacharacter sanitization.  "
                "Enables arbitrary OS command execution."
            ),
            c_code_pattern=r"\b(?:system|popen)\s*\([^)]*(?:buf|cmd|input|str|arg|argv|req)[^)]*\)",
            severity=Severity.CRITICAL,
            detection_method=DetectionMethod.INJECTION,
            cwe_id="CWE-78",
            cvss_score=9.8,
            example_cves=(),
        ),

        # 14. Realloc result not checked / double-free on failure path
        VulnerabilityPattern(
            name="REALLOC_OVERWRITE_PTR",
            description=(
                "ptr = realloc(ptr, new_size) — if realloc returns NULL the original "
                "pointer is lost, causing a memory leak.  If the caller subsequently "
                "frees 'ptr' the behaviour is undefined (double-free or leak)."
            ),
            c_code_pattern=r"([\w>\-]+)\s*=\s*realloc\s*\(\s*\1\s*,",
            severity=Severity.MEDIUM,
            detection_method=DetectionMethod.LIFETIME_ANALYSIS,
            cwe_id="CWE-415",
            cvss_score=5.5,
            example_cves=(),
        ),

        # 15. strncpy without null termination — classic off-by-one / no-null issue
        VulnerabilityPattern(
            name="STRNCPY_NOT_NULL_TERMINATED",
            description=(
                "strncpy(dst, src, n) does NOT null-terminate dst when src is exactly "
                "n or more bytes long.  A subsequent strlen(dst) or strcpy(dst) reads "
                "past the intended boundary."
            ),
            c_code_pattern=r"\bstrncpy\s*\([^;]+\);\s*(?!\s*\w+\[\w+\s*-\s*1\]\s*=\s*\\0)",
            severity=Severity.MEDIUM,
            detection_method=DetectionMethod.BUFFER_BOUND_ANALYSIS,
            cwe_id="CWE-170",
            cvss_score=6.5,
            example_cves=(),
        ),
    ]

    def __init__(self) -> None:
        # Pre-compile all patterns for performance
        self._compiled: list[tuple[VulnerabilityPattern, re.Pattern[str]]] = [
            (p, re.compile(p.c_code_pattern)) for p in self.PATTERNS
        ]

    def get_by_cwe(self, cwe_id: str) -> list[VulnerabilityPattern]:
        """Return all patterns whose CWE matches (case-insensitive prefix match)."""
        cwe_id = cwe_id.upper()
        return [p for p in self.PATTERNS if p.cwe_id.upper().startswith(cwe_id)]

    def get_by_severity(self, severity: Severity) -> list[VulnerabilityPattern]:
        return [p for p in self.PATTERNS if p.severity == severity]


# ---------------------------------------------------------------------------
# Pattern matcher
# ---------------------------------------------------------------------------

class PatternMatcher:
    """
    Scans C source code for vulnerability patterns.

    The scan is line-level and regex-based; it is intentionally conservative
    (flags potential issues for human review) rather than attempting dataflow
    precision.  Confidence scores reflect the heuristic nature of each pattern.
    """

    # Per-pattern base confidence scores (tuned heuristically)
    _CONFIDENCE: ClassVar[dict[str, float]] = {
        "MALLOC_STRLEN_NO_PLUS_ONE":    0.90,
        "STRCPY_UNBOUNDED":             0.70,
        "GETS_USAGE":                   0.99,
        "INT_OVERFLOW_MALLOC_SIZE":     0.75,
        "MEMCPY_UNCHECKED_LEN":         0.65,
        "FREE_THEN_USE":                0.55,   # requires inter-line analysis for full confidence
        "MALLOC_NO_NULL_CHECK":         0.60,
        "PRINTF_FORMAT_STRING":         0.70,
        "SPRINTF_UNBOUNDED":            0.80,
        "ALLOCA_UNCHECKED_SIZE":        0.75,
        "INT_TRUNCATION_CAST":          0.65,
        "SIGNED_INDEX_NO_CHECK":        0.70,
        "SYSTEM_COMMAND_INJECTION":     0.80,
        "REALLOC_OVERWRITE_PTR":        0.85,
        "STRNCPY_NOT_NULL_TERMINATED":  0.60,
    }

    def __init__(self, library: VulnerabilityPatternLibrary | None = None) -> None:
        self._library = library or VulnerabilityPatternLibrary()

    def scan(self, c_source: str) -> list[PatternMatch]:
        """
        Scan *c_source* (a string of C code) and return all PatternMatch results,
        ordered by line number then by pattern name.

        Parameters
        ----------
        c_source:
            Raw C source code as a single string.

        Returns
        -------
        list[PatternMatch]
            Every hit found.  A single line may produce multiple matches
            if several patterns apply.
        """
        lines = c_source.splitlines()
        results: list[PatternMatch] = []

        for pattern, compiled in self._library._compiled:
            confidence = self._CONFIDENCE.get(pattern.name, 0.5)
            for lineno, line in enumerate(lines, start=1):
                # Skip comment lines (very basic heuristic)
                stripped = line.lstrip()
                if stripped.startswith("//") or stripped.startswith("*"):
                    continue
                match = compiled.search(line)
                if match:
                    results.append(
                        PatternMatch(
                            pattern_name=pattern.name,
                            line_number=lineno,
                            matched_text=match.group(0),
                            confidence=confidence,
                            cwe_id=pattern.cwe_id,
                        )
                    )

        results.sort(key=lambda m: (m.line_number, m.pattern_name))
        return results

    def scan_file(self, path: str) -> list[PatternMatch]:
        """Convenience wrapper that reads *path* and calls scan()."""
        with open(path, encoding="utf-8", errors="replace") as fh:
            return self.scan(fh.read())

    def report(self, matches: list[PatternMatch]) -> str:
        """Format a human-readable report from a list of matches."""
        if not matches:
            return "No vulnerability patterns detected.\n"
        lines = ["Vulnerability Pattern Scan Report", "=" * 40]
        for m in matches:
            lines.append(str(m))
        lines.append("-" * 40)
        lines.append(f"Total findings: {len(matches)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

def _run_tests() -> None:
    """
    Built-in test cases using real vulnerable C snippets derived from the
    CVE forensic analysis.  Each case asserts that the expected pattern fires
    on the given code snippet.
    """

    import sys

    matcher = PatternMatcher()
    failures: list[str] = []

    def assert_match(test_name: str, snippet: str, expected_pattern: str) -> None:
        matches = matcher.scan(textwrap.dedent(snippet))
        names = {m.pattern_name for m in matches}
        if expected_pattern not in names:
            failures.append(
                f"FAIL [{test_name}]: expected '{expected_pattern}' in {sorted(names)}"
            )
        else:
            print(f"  PASS [{test_name}]: '{expected_pattern}' fired correctly")

    def assert_no_match(test_name: str, snippet: str, pattern: str) -> None:
        matches = matcher.scan(textwrap.dedent(snippet))
        names = {m.pattern_name for m in matches}
        if pattern in names:
            failures.append(
                f"FAIL [{test_name}]: '{pattern}' should NOT fire on safe code"
            )
        else:
            print(f"  PASS [{test_name}]: '{pattern}' correctly silent on safe code")

    print("\n=== VulnerabilityPatternLibrary Test Suite ===\n")

    # ------------------------------------------------------------------
    # Test 1 — CVE-2021-3156 (Baron Samedit): malloc(strlen(x)) off-by-one
    # ------------------------------------------------------------------
    assert_match(
        "baron_samedit_off_by_one",
        """
        char *buf = malloc(strlen(user_arg));
        strcpy(buf, user_arg);
        """,
        "MALLOC_STRLEN_NO_PLUS_ONE",
    )

    # ------------------------------------------------------------------
    # Test 2 — Safe variant: malloc(strlen(x) + 1)  — should NOT fire
    # ------------------------------------------------------------------
    assert_no_match(
        "baron_samedit_safe",
        """
        char *buf = malloc(strlen(user_arg) + 1);
        strcpy(buf, user_arg);
        """,
        "MALLOC_STRLEN_NO_PLUS_ONE",
    )

    # ------------------------------------------------------------------
    # Test 3 — CVE-2014-0160 (Heartbleed): memcpy with tainted length
    # ------------------------------------------------------------------
    assert_match(
        "heartbleed_memcpy",
        """
        unsigned int payload;
        n2s(p, payload);
        unsigned char *buffer = OPENSSL_malloc(1 + 2 + payload + 16);
        memcpy(bp, pl, payload);
        """,
        "MEMCPY_UNCHECKED_LEN",
    )

    # ------------------------------------------------------------------
    # Test 4 — CVE-2022-0185 (integer overflow in malloc size)
    # ------------------------------------------------------------------
    assert_match(
        "cve_2022_0185_int_overflow",
        """
        unsigned int count = get_user_count();
        unsigned int elem_size = sizeof(struct item);
        void *buf = malloc(count * elem_size);
        """,
        "INT_OVERFLOW_MALLOC_SIZE",
    )

    # ------------------------------------------------------------------
    # Test 5 — CVE-2020-8616 (BIND 9 use-after-free): free without null
    # ------------------------------------------------------------------
    assert_match(
        "bind9_uaf",
        """
        dns_resolver_t *res = fctx->res;
        free(res);
        isc_task_send(res->task, &event);
        """,
        "FREE_THEN_USE",
    )

    # ------------------------------------------------------------------
    # Test 6 — gets() — always matches
    # ------------------------------------------------------------------
    assert_match(
        "gets_always_dangerous",
        """
        char buf[256];
        gets(buf);
        """,
        "GETS_USAGE",
    )

    # ------------------------------------------------------------------
    # Test 7 — sprintf → should flag SPRINTF_UNBOUNDED
    # ------------------------------------------------------------------
    assert_match(
        "sprintf_overflow",
        """
        char dest[64];
        sprintf(dest, "%s", user_input);
        """,
        "SPRINTF_UNBOUNDED",
    )

    # ------------------------------------------------------------------
    # Test 8 — alloca with unchecked size (CVE-2015-7547 style)
    # ------------------------------------------------------------------
    assert_match(
        "alloca_unchecked",
        """
        uint8_t *ans = alloca(anslen);
        recvfrom(s, ans, anslen, 0, NULL, NULL);
        """,
        "ALLOCA_UNCHECKED_SIZE",
    )

    # ------------------------------------------------------------------
    # Test 9 — integer truncation cast
    # ------------------------------------------------------------------
    assert_match(
        "int_truncation",
        """
        uint32_t received_len = ntohl(header.length);
        uint16_t pcount = (uint16_t) received_len;
        tp->sacked_out += pcount;
        """,
        "INT_TRUNCATION_CAST",
    )

    # ------------------------------------------------------------------
    # Test 10 — system() command injection
    # ------------------------------------------------------------------
    assert_match(
        "system_injection",
        """
        char cmd[512];
        snprintf(cmd, sizeof(cmd), "ls %s", input);
        system(cmd);
        """,
        "SYSTEM_COMMAND_INJECTION",
    )

    # ------------------------------------------------------------------
    # Test 11 — realloc overwrites pointer (leak on NULL)
    # ------------------------------------------------------------------
    assert_match(
        "realloc_overwrite",
        """
        ctx->data = realloc(ctx->data, new_size);
        if (!ctx->data) return -ENOMEM;
        """,
        "REALLOC_OVERWRITE_PTR",
    )

    # ------------------------------------------------------------------
    # Test 12 — strcpy unbounded
    # ------------------------------------------------------------------
    assert_match(
        "strcpy_overflow",
        """
        char dst[64];
        strcpy(dst, src);
        """,
        "STRCPY_UNBOUNDED",
    )

    # ------------------------------------------------------------------
    # Test 13 — signed ssize_t from recv without check
    # ------------------------------------------------------------------
    assert_match(
        "signed_recv_index",
        """
        ssize_t n = recv(sock, buf, sizeof(buf), 0);
        memcpy(dst, buf, n);
        """,
        "SIGNED_INDEX_NO_CHECK",
    )

    # ------------------------------------------------------------------
    # Test 14 — printf format string injection
    # ------------------------------------------------------------------
    assert_match(
        "printf_format_string",
        """
        char msg[256];
        snprintf(msg, sizeof(msg), "%s", req->header);
        printf(msg);
        """,
        "PRINTF_FORMAT_STRING",
    )

    # ------------------------------------------------------------------
    # Test 15 — Library API surface check: all 15 patterns registered
    # ------------------------------------------------------------------
    lib = VulnerabilityPatternLibrary()
    assert len(lib.PATTERNS) == 15, (
        f"Expected 15 patterns, got {len(lib.PATTERNS)}"
    )
    print(f"  PASS [library_count]: 15 patterns registered")

    # ------------------------------------------------------------------
    # Test 16 — get_by_cwe filter
    # ------------------------------------------------------------------
    cwe190_patterns = lib.get_by_cwe("CWE-190")
    assert len(cwe190_patterns) >= 1, "Expected at least one CWE-190 pattern"
    print(f"  PASS [get_by_cwe]: found {len(cwe190_patterns)} CWE-190 pattern(s)")

    # ------------------------------------------------------------------
    # Test 17 — get_by_severity filter
    # ------------------------------------------------------------------
    critical = lib.get_by_severity(Severity.CRITICAL)
    assert len(critical) >= 1, "Expected at least one CRITICAL pattern"
    print(f"  PASS [get_by_severity]: found {len(critical)} CRITICAL pattern(s)")

    # ------------------------------------------------------------------
    # Test 18 — PatternMatch fields are correct types
    # ------------------------------------------------------------------
    results = matcher.scan("gets(buf);")
    assert results, "Expected at least one match for gets()"
    m = results[0]
    assert isinstance(m.line_number, int)
    assert isinstance(m.matched_text, str)
    assert isinstance(m.confidence, float)
    assert 0.0 <= m.confidence <= 1.0
    print(f"  PASS [match_fields]: PatternMatch fields have correct types")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    else:
        print(f"All tests passed.")


# ---------------------------------------------------------------------------
# Demo: scan a multi-vulnerability snippet and print the report
# ---------------------------------------------------------------------------

_DEMO_C_SOURCE = """
/*
 * demo.c — deliberately vulnerable C snippet combining patterns from multiple CVEs.
 * DO NOT USE IN PRODUCTION.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* CVE-2021-3156 style: malloc without +1 */
char *copy_arg(const char *input) {
    char *buf = malloc(strlen(input));    /* off-by-one: no +1 for null terminator */
    strcpy(buf, input);                   /* strcpy writes null → heap overflow    */
    return buf;
}

/* CVE-2014-0160 style: memcpy with network-supplied length */
void heartbeat_reply(unsigned char *pl, unsigned int payload, unsigned char *out) {
    memcpy(out, pl, payload);             /* payload not validated against actual size */
}

/* CVE-2022-0185 style: integer overflow in malloc size */
void *alloc_items(unsigned int count, unsigned int elem_size) {
    void *buf = malloc(count * elem_size); /* 32-bit overflow before widening */
    return buf;
}

/* gets() — always vulnerable */
void read_input(void) {
    char line[256];
    gets(line);                           /* no bounds whatsoever */
    printf(line);                         /* format string vuln too */
}

/* alloca with unchecked size */
void dns_recv(int sock, int anslen) {
    uint8_t *ans = alloca(anslen);        /* stack overflow if anslen is large */
}

/* realloc pointer overwrite */
int grow_buffer(struct ctx *ctx, size_t new_size) {
    ctx->data = realloc(ctx->data, new_size);  /* original pointer lost on OOM */
    return 0;
}
"""


def _run_demo() -> None:
    print("\n=== Demo: Scanning vulnerable C snippet ===\n")
    matcher = PatternMatcher()
    matches = matcher.scan(_DEMO_C_SOURCE)
    print(matcher.report(matches))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _run_tests()
    _run_demo()
