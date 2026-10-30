"""Codebase reader for the autonomous GitHub issue-fixing agent."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Symbol:
    name: str
    kind: str  # "function", "class", "method", "variable"
    file: str
    line_start: int
    line_end: int
    docstring: Optional[str] = None


@dataclass
class CallGraph:
    """Directed call graph: caller -> set of callees."""
    edges: dict[str, set[str]] = field(default_factory=dict)

    def add_call(self, caller: str, callee: str) -> None:
        self.edges.setdefault(caller, set()).add(callee)

    def callees_of(self, name: str) -> set[str]:
        return self.edges.get(name, set())

    def callers_of(self, name: str) -> set[str]:
        return {caller for caller, callees in self.edges.items() if name in callees}

    def reachable_from(self, start: str, max_depth: int = 5) -> set[str]:
        visited: set[str] = set()
        frontier = {start}
        for _ in range(max_depth):
            next_frontier: set[str] = set()
            for node in frontier:
                for callee in self.callees_of(node):
                    if callee not in visited:
                        next_frontier.add(callee)
            visited |= frontier
            frontier = next_frontier
        return visited - {start}


@dataclass
class BugLocation:
    file: str
    line: int
    function: str
    confidence: float
    reason: str


@dataclass
class CodebaseModel:
    files: dict[str, str]  # filename -> source
    symbols: dict[str, Symbol]  # qualified_name -> Symbol
    call_graph: CallGraph
    suspected_locations: list[BugLocation]

    def get_function_source(self, qualified_name: str) -> Optional[str]:
        sym = self.symbols.get(qualified_name)
        if not sym:
            return None
        src = self.files.get(sym.file, "")
        lines = src.splitlines()
        return "\n".join(lines[sym.line_start - 1 : sym.line_end])


# ---------------------------------------------------------------------------
# Symbol extractors
# ---------------------------------------------------------------------------

class _PythonSymbolExtractor(ast.NodeVisitor):
    """Extract symbols from a Python AST."""

    def __init__(self, filename: str, source: str) -> None:
        self.filename = filename
        self.source = source
        self.symbols: dict[str, Symbol] = {}
        self._class_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = "method" if self._class_stack else "function"
        qualified = (
            f"{self._class_stack[-1]}.{node.name}" if self._class_stack else node.name
        )
        docstring = ast.get_docstring(node)
        self.symbols[qualified] = Symbol(
            name=node.name,
            kind=kind,
            file=self.filename,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            docstring=docstring,
        )
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = node.name
        self.symbols[qualified] = Symbol(
            name=node.name,
            kind="class",
            file=self.filename,
            line_start=node.lineno,
            line_end=getattr(node, "end_lineno", node.lineno),
            docstring=ast.get_docstring(node),
        )
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()


class _CSymbolExtractor:
    """Regex-based symbol extraction for C source files."""

    FUNC_PATTERN = re.compile(
        r"^(?:static\s+|extern\s+|inline\s+|__attribute__\([^)]*\)\s*)*"
        r"(?:(?:unsigned\s+|const\s+|volatile\s+)?[a-zA-Z_]\w*(?:\s*\*+)?)\s+"
        r"([a-zA-Z_]\w*)\s*\([^;{]*\)\s*\{",
        re.MULTILINE,
    )

    def extract(self, filename: str, source: str) -> dict[str, Symbol]:
        symbols: dict[str, Symbol] = {}
        lines = source.splitlines()
        for m in self.FUNC_PATTERN.finditer(source):
            name = m.group(1)
            line_no = source[: m.start()].count("\n") + 1
            # Approximate end by scanning for matching brace
            end_line = self._find_end_brace(lines, line_no - 1)
            symbols[name] = Symbol(
                name=name,
                kind="function",
                file=filename,
                line_start=line_no,
                line_end=end_line,
            )
        return symbols

    @staticmethod
    def _find_end_brace(lines: list[str], start: int) -> int:
        depth = 0
        for i in range(start, len(lines)):
            depth += lines[i].count("{") - lines[i].count("}")
            if depth <= 0 and i > start:
                return i + 1
        return len(lines)


# ---------------------------------------------------------------------------
# Call graph builder (Python)
# ---------------------------------------------------------------------------

class _CallGraphBuilder(ast.NodeVisitor):
    def __init__(self, current_function: str = "<module>") -> None:
        self.graph = CallGraph()
        self._current: str = current_function

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        old = self._current
        self._current = node.name
        self.generic_visit(node)
        self._current = old

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        callee = self._resolve_call_name(node.func)
        if callee:
            self.graph.add_call(self._current, callee)
        self.generic_visit(node)

    @staticmethod
    def _resolve_call_name(node: ast.expr) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None


# ---------------------------------------------------------------------------
# CodebaseReader
# ---------------------------------------------------------------------------

class CodebaseReader:
    """Read a codebase and build a model relevant to a given issue."""

    def __init__(self) -> None:
        self._c_extractor = _CSymbolExtractor()

    def read_for_issue(
        self,
        files: dict[str, str],
        issue_title: str,
        issue_body: str,
        suspected_function: str = "",
    ) -> CodebaseModel:
        """Build a full CodebaseModel for the given files and issue."""
        symbols = self.extract_symbols(files)
        call_graph = self.extract_call_graph(files)
        relevant = self.identify_relevant_files(files, issue_title, issue_body)
        locations = self.find_bug_location(
            files=files,
            symbols=symbols,
            call_graph=call_graph,
            issue_body=issue_body,
            suspected_function=suspected_function,
        )
        return CodebaseModel(
            files=files,
            symbols=symbols,
            call_graph=call_graph,
            suspected_locations=locations,
        )

    def identify_relevant_files(
        self, files: dict[str, str], issue_title: str, issue_body: str
    ) -> list[str]:
        """Return files likely relevant to the issue, ranked by keyword overlap."""
        keywords = self._extract_keywords(issue_title + " " + issue_body)
        scores: list[tuple[float, str]] = []
        for filename, content in files.items():
            score = sum(1.0 for kw in keywords if kw.lower() in content.lower())
            score += sum(2.0 for kw in keywords if kw.lower() in filename.lower())
            scores.append((score, filename))
        scores.sort(reverse=True)
        return [f for _, f in scores if _ > 0]

    def extract_call_graph(self, files: dict[str, str]) -> CallGraph:
        """Build a merged call graph from all Python files."""
        merged = CallGraph()
        for filename, source in files.items():
            if not filename.endswith(".py"):
                continue
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            builder = _CallGraphBuilder()
            builder.visit(tree)
            for caller, callees in builder.graph.edges.items():
                for callee in callees:
                    merged.add_call(caller, callee)
        return merged

    def trace_execution_path(
        self, call_graph: CallGraph, entry: str, target: str, max_depth: int = 10
    ) -> list[str]:
        """BFS path from entry to target in the call graph."""
        if entry == target:
            return [entry]
        visited: set[str] = set()
        queue: list[list[str]] = [[entry]]
        while queue:
            path = queue.pop(0)
            node = path[-1]
            if node in visited:
                continue
            visited.add(node)
            for callee in call_graph.callees_of(node):
                new_path = path + [callee]
                if callee == target:
                    return new_path
                if len(new_path) <= max_depth:
                    queue.append(new_path)
        return []

    def extract_symbols(self, files: dict[str, str]) -> dict[str, Symbol]:
        """Extract all symbols from all files."""
        all_symbols: dict[str, Symbol] = {}
        for filename, source in files.items():
            if filename.endswith(".py"):
                extractor = _PythonSymbolExtractor(filename, source)
                try:
                    extractor.visit(ast.parse(source))
                except SyntaxError:
                    continue
                all_symbols.update(extractor.symbols)
            elif filename.endswith((".c", ".h", ".cpp", ".cc")):
                all_symbols.update(self._c_extractor.extract(filename, source))
        return all_symbols

    def find_bug_location(
        self,
        files: dict[str, str],
        symbols: dict[str, Symbol],
        call_graph: CallGraph,
        issue_body: str,
        suspected_function: str = "",
    ) -> list[BugLocation]:
        """
        Multi-strategy bug location waterfall:
        1. Traceback parsing (highest confidence)
        2. Suspected function from issue title
        3. Semantic keyword match
        4. Call graph centrality
        """
        locations: list[BugLocation] = []

        # Strategy 1: Parse Python traceback
        tb_locations = self._parse_traceback(issue_body, files)
        locations.extend(tb_locations)

        # Strategy 2: Suspected function name
        if suspected_function and suspected_function in symbols:
            sym = symbols[suspected_function]
            locations.append(
                BugLocation(
                    file=sym.file,
                    line=sym.line_start,
                    function=suspected_function,
                    confidence=0.80,
                    reason="Explicitly named suspected function",
                )
            )

        # Strategy 3: Semantic keyword match in function bodies
        keywords = self._extract_keywords(issue_body)
        for qualified_name, sym in symbols.items():
            if sym.kind not in ("function", "method"):
                continue
            source = files.get(sym.file, "")
            lines = source.splitlines()
            body = "\n".join(lines[sym.line_start - 1 : sym.line_end])
            overlap = sum(1 for kw in keywords if kw.lower() in body.lower())
            if overlap >= 2:
                locations.append(
                    BugLocation(
                        file=sym.file,
                        line=sym.line_start,
                        function=qualified_name,
                        confidence=min(0.30 + overlap * 0.10, 0.70),
                        reason=f"Semantic keyword overlap ({overlap} keywords)",
                    )
                )

        # Strategy 4: Call graph centrality (high in-degree = risky)
        callers_count = {
            name: len(call_graph.callers_of(name))
            for name in symbols
        }
        for name, count in sorted(callers_count.items(), key=lambda x: x[1], reverse=True)[:3]:
            sym = symbols[name]
            if sym.kind in ("function", "method") and count >= 2:
                locations.append(
                    BugLocation(
                        file=sym.file,
                        line=sym.line_start,
                        function=name,
                        confidence=0.25,
                        reason=f"High call-graph centrality ({count} callers)",
                    )
                )

        # Sort by confidence descending
        locations.sort(key=lambda l: l.confidence, reverse=True)
        # Deduplicate by function
        seen: set[str] = set()
        unique: list[BugLocation] = []
        for loc in locations:
            if loc.function not in seen:
                seen.add(loc.function)
                unique.append(loc)
        return unique

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful words from text, excluding stop words."""
        stop = {
            "the", "a", "an", "is", "it", "in", "on", "at", "of", "to",
            "and", "or", "but", "for", "with", "this", "that", "when",
            "was", "are", "be", "by", "from", "has", "have", "not", "no",
            "i", "we", "you", "he", "she", "they", "can", "will", "would",
            "should", "could", "may", "also", "just", "if", "as", "my",
        }
        words = re.findall(r"\b[a-zA-Z_]\w*\b", text)
        return [w for w in words if w.lower() not in stop and len(w) >= 3]

    @staticmethod
    def _parse_traceback(text: str, files: dict[str, str]) -> list[BugLocation]:
        """Extract file/line/function from Python traceback in issue body."""
        pattern = re.compile(
            r'File "([^"]+)", line (\d+), in (\w+)'
        )
        locations: list[BugLocation] = []
        for m in pattern.finditer(text):
            tb_file = m.group(1).lstrip("./")
            line_no = int(m.group(2))
            func_name = m.group(3)
            # Find the best matching file in the codebase
            matched_file = tb_file
            for f in files:
                if f.endswith(tb_file) or tb_file.endswith(f):
                    matched_file = f
                    break
            locations.append(
                BugLocation(
                    file=matched_file,
                    line=line_no,
                    function=func_name,
                    confidence=0.92,
                    reason="Direct traceback reference",
                )
            )
        return locations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _run_tests():
    print("Running CodebaseReader tests...")
    reader = CodebaseReader()
    passed = 0
    failed = 0

    # Test data
    SOURCE_A = """\
class Parser:
    def parse(self, text):
        \"\"\"Parse the input text.\"\"\"
        tokens = self.tokenize(text)
        return self.build_tree(tokens)

    def tokenize(self, text):
        return text.split()

    def build_tree(self, tokens):
        if not tokens:
            return None
        return {"root": tokens[0], "children": tokens[1:]}

def run_parser(text):
    p = Parser()
    return p.parse(text)
"""

    SOURCE_B = """\
def validate_input(data):
    if data is None:
        raise ValueError("data cannot be None")
    return True

def process(data):
    validate_input(data)
    result = []
    for item in data:
        result.append(item * 2)
    return result
"""

    files = {"parser.py": SOURCE_A, "utils.py": SOURCE_B}

    # Test 1: Symbol extraction
    symbols = reader.extract_symbols(files)
    assert "Parser" in symbols, "Should find Parser class"
    assert "Parser.parse" in symbols or "parse" in symbols, "Should find parse method"
    assert "run_parser" in symbols, "Should find run_parser function"
    print(f"  Test 1 PASS: extracted {len(symbols)} symbols")
    passed += 1

    # Test 2: Call graph extraction
    cg = reader.extract_call_graph(files)
    assert len(cg.edges) > 0, "Call graph should have edges"
    print(f"  Test 2 PASS: call graph has {sum(len(v) for v in cg.edges.values())} edges")
    passed += 1

    # Test 3: Relevant file identification
    relevant = reader.identify_relevant_files(files, "Parser crashes on empty input", "build_tree returns None")
    assert "parser.py" in relevant, f"parser.py should be relevant, got {relevant}"
    print(f"  Test 3 PASS: relevant files = {relevant}")
    passed += 1

    # Test 4: Traceback parsing
    tb_text = 'File "utils.py", line 7, in process\nKeyError: missing key'
    locations = reader._parse_traceback(tb_text, files)
    assert len(locations) > 0, "Should parse traceback location"
    assert locations[0].line == 7
    assert locations[0].function == "process"
    assert locations[0].confidence >= 0.9
    print(f"  Test 4 PASS: traceback -> {locations[0]}")
    passed += 1

    # Test 5: Bug location waterfall
    model = reader.read_for_issue(
        files=files,
        issue_title="process crashes with NoneType error",
        issue_body='File "utils.py", line 7, in process\nAttributeError: NoneType',
        suspected_function="validate_input",
    )
    assert len(model.suspected_locations) > 0
    print(f"  Test 5 PASS: {len(model.suspected_locations)} bug locations found")
    print(f"    Top: {model.suspected_locations[0]}")
    passed += 1

    # Test 6: Execution path tracing
    cg2 = CallGraph()
    cg2.add_call("run_parser", "parse")
    cg2.add_call("parse", "tokenize")
    cg2.add_call("parse", "build_tree")
    path = reader.trace_execution_path(cg2, "run_parser", "build_tree")
    assert "build_tree" in path, f"Path should reach build_tree: {path}"
    print(f"  Test 6 PASS: path = {path}")
    passed += 1

    # Test 7: C symbol extraction
    c_source = """\
static int compute_hash(const char *key) {
    int h = 0;
    while (*key) h = h * 31 + *key++;
    return h;
}

void insert_entry(HashTable *ht, const char *key, void *val) {
    int idx = compute_hash(key) % ht->capacity;
    ht->buckets[idx] = val;
}
"""
    c_symbols = reader._c_extractor.extract("hash.c", c_source)
    assert "compute_hash" in c_symbols or "insert_entry" in c_symbols, \
        f"Should find C functions, got {list(c_symbols.keys())}"
    print(f"  Test 7 PASS: C symbols = {list(c_symbols.keys())}")
    passed += 1

    # Test 8: get_function_source
    model2 = CodebaseModel(
        files=files,
        symbols=symbols,
        call_graph=cg,
        suspected_locations=[],
    )
    src = model2.get_function_source("run_parser")
    assert src is not None, "Should retrieve function source"
    assert "run_parser" in src
    print(f"  Test 8 PASS: function source retrieved ({len(src)} chars)")
    passed += 1

    # Test 9: reachable_from in call graph
    cg3 = CallGraph()
    cg3.add_call("a", "b")
    cg3.add_call("b", "c")
    cg3.add_call("c", "d")
    reachable = cg3.reachable_from("a", max_depth=3)
    assert "b" in reachable and "c" in reachable, f"Should reach b,c: {reachable}"
    print(f"  Test 9 PASS: reachable_from('a') = {reachable}")
    passed += 1

    # Test 10: keyword extraction
    keywords = reader._extract_keywords("The parser crashes on empty input tokens")
    assert "parser" in keywords
    assert "the" not in keywords  # stop word
    print(f"  Test 10 PASS: keywords = {keywords[:6]}")
    passed += 1

    print(f"\nResults: {passed} passed, {failed} failed")


if __name__ == "__main__":
    _run_tests()
