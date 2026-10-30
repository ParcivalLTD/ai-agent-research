"""
CodebaseContextManager — smart codebase reader with L0–L4 representation pyramid.

L0 — raw file bytes (on-disk, never loaded unless explicitly requested)
L1 — file metadata: path, language, line count, last-modified
L2 — symbol inventory: function/class names, signatures (no bodies)
L3 — docstrings + type signatures
L4 — full source text

LRU eviction operates at the L4 level (cheapest-to-regen is evicted first).
Demand-driven: lower levels are loaded automatically when higher ones are needed.
"""

from __future__ import annotations

import ast
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FileMetadata:          # L1
    path: str
    language: str
    line_count: int
    size_bytes: int
    last_modified: float


@dataclass
class Symbol:
    name: str
    kind: str           # "function" | "class" | "method" | "struct" | "impl"
    signature: str
    docstring: str = ""
    start_line: int = 0
    end_line: int = 0


@dataclass
class FileContext:
    meta: FileMetadata                   # always present
    symbols: list[Symbol] = field(default_factory=list)   # L2+
    source: Optional[str] = None         # L4 (may be None if evicted)
    loaded_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Language-specific symbol extractors
# ---------------------------------------------------------------------------

def _extract_python_symbols(source: str) -> list[Symbol]:
    symbols: list[Symbol] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return symbols

    lines = source.splitlines()

    def _sig(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        args = ast.unparse(node.args) if hasattr(ast, "unparse") else "..."
        ret = f" -> {ast.unparse(node.returns)}" if node.returns and hasattr(ast, "unparse") else ""
        return f"def {node.name}({args}){ret}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node) or ""
            symbols.append(Symbol(
                name=node.name,
                kind="function",
                signature=_sig(node),
                docstring=doc,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
            ))
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ""
            symbols.append(Symbol(
                name=node.name,
                kind="class",
                signature=f"class {node.name}",
                docstring=doc,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
            ))
    return symbols


def _extract_c_symbols(source: str) -> list[Symbol]:
    """Heuristic C symbol extractor — captures top-level function signatures."""
    pattern = re.compile(
        r"^(?:static\s+|extern\s+|inline\s+)*"
        r"(?:[\w\*]+\s+){1,4}"   # return type (up to 4 words + pointer)
        r"(\w+)\s*\(([^)]*)\)\s*\{",
        re.MULTILINE,
    )
    symbols: list[Symbol] = []
    for m in pattern.finditer(source):
        name = m.group(1)
        sig = m.group(0).rstrip("{").strip()
        line_no = source[: m.start()].count("\n") + 1
        symbols.append(Symbol(name=name, kind="function", signature=sig, start_line=line_no))
    return symbols


def _extract_rust_symbols(source: str) -> list[Symbol]:
    """Heuristic Rust symbol extractor."""
    fn_pattern = re.compile(
        r"^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(\w+)\s*(<[^>]*>)?\s*\(([^)]*)\)"
        r"(?:\s*->\s*([^{]+))?",
        re.MULTILINE,
    )
    struct_pattern = re.compile(
        r"^(?:pub(?:\([^)]*\))?\s+)?struct\s+(\w+)",
        re.MULTILINE,
    )
    impl_pattern = re.compile(
        r"^impl(?:<[^>]*>)?\s+([\w<>, ]+?)\s*\{",
        re.MULTILINE,
    )
    symbols: list[Symbol] = []
    for m in fn_pattern.finditer(source):
        line_no = source[: m.start()].count("\n") + 1
        symbols.append(Symbol(name=m.group(1), kind="function", signature=m.group(0), start_line=line_no))
    for m in struct_pattern.finditer(source):
        line_no = source[: m.start()].count("\n") + 1
        symbols.append(Symbol(name=m.group(1), kind="struct", signature=m.group(0), start_line=line_no))
    for m in impl_pattern.finditer(source):
        line_no = source[: m.start()].count("\n") + 1
        symbols.append(Symbol(name=m.group(1).strip(), kind="impl", signature=m.group(0).rstrip("{").strip(), start_line=line_no))
    return symbols


def _extract_lua_symbols(source: str) -> list[Symbol]:
    """Heuristic Lua symbol extractor."""
    pattern = re.compile(
        r"^(?:local\s+)?function\s+([\w.:]+)\s*\(([^)]*)\)",
        re.MULTILINE,
    )
    symbols: list[Symbol] = []
    for m in pattern.finditer(source):
        line_no = source[: m.start()].count("\n") + 1
        symbols.append(Symbol(name=m.group(1), kind="function", signature=m.group(0), start_line=line_no))
    return symbols


_EXTRACTORS = {
    "python": _extract_python_symbols,
    "c": _extract_c_symbols,
    "rust": _extract_rust_symbols,
    "lua": _extract_lua_symbols,
}

_LANG_MAP = {
    ".py": "python",
    ".c": "c", ".h": "c",
    ".rs": "rust",
    ".lua": "lua",
}


# ---------------------------------------------------------------------------
# Call-graph tracer (Python only, lightweight)
# ---------------------------------------------------------------------------

def _trace_call_graph_python(source: str, target_fn: str) -> set[str]:
    """Return names of all functions called by *target_fn* in *source*."""
    called: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return called

    target_node: Optional[ast.FunctionDef] = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target_fn:
            target_node = node
            break

    if target_node is None:
        return called

    for node in ast.walk(target_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    return called


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class CodebaseContextManager:
    """
    Smart codebase reader.

    Usage::

        ctx = CodebaseContextManager("/path/to/repo", max_l4_files=50)
        meta = ctx.get_file_meta("src/foo.py")        # L1
        syms = ctx.get_symbols("src/foo.py")           # L2
        src  = ctx.get_source("src/foo.py")            # L4
        callers = ctx.callers_of("src/foo.py", "bar")  # call-graph
    """

    def __init__(self, root: str | Path, max_l4_files: int = 50) -> None:
        self.root = Path(root).resolve()
        self.max_l4_files = max_l4_files
        # L1 cache: always kept
        self._meta_cache: dict[str, FileMetadata] = {}
        # L2 cache: always kept (symbols are small)
        self._symbol_cache: dict[str, list[Symbol]] = {}
        # L4 LRU cache: evicted when full
        self._source_cache: OrderedDict[str, str] = OrderedDict()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_file_meta(self, rel_path: str) -> FileMetadata:
        if rel_path not in self._meta_cache:
            self._meta_cache[rel_path] = self._load_meta(rel_path)
        return self._meta_cache[rel_path]

    def get_symbols(self, rel_path: str) -> list[Symbol]:
        if rel_path not in self._symbol_cache:
            source = self.get_source(rel_path)
            lang = self.get_file_meta(rel_path).language
            extractor = _EXTRACTORS.get(lang, lambda _: [])
            self._symbol_cache[rel_path] = extractor(source)
        return self._symbol_cache[rel_path]

    def get_source(self, rel_path: str) -> str:
        if rel_path in self._source_cache:
            self._source_cache.move_to_end(rel_path)  # refresh LRU
            return self._source_cache[rel_path]
        source = (self.root / rel_path).read_text(errors="replace")
        self._source_cache[rel_path] = source
        self._source_cache.move_to_end(rel_path)
        self._evict_if_needed()
        return source

    def get_symbol_body(self, rel_path: str, symbol_name: str) -> Optional[str]:
        """Return the source lines for a named symbol."""
        syms = self.get_symbols(rel_path)
        sym = next((s for s in syms if s.name == symbol_name), None)
        if sym is None or sym.end_line == 0:
            return None
        lines = self.get_source(rel_path).splitlines()
        return "\n".join(lines[sym.start_line - 1 : sym.end_line])

    def callers_of(self, rel_path: str, fn_name: str) -> set[str]:
        """Return function names that call *fn_name* within *rel_path*."""
        lang = self.get_file_meta(rel_path).language
        if lang != "python":
            return set()  # only Python supported for now
        source = self.get_source(rel_path)
        return _trace_call_graph_python(source, fn_name)

    def scan_directory(self) -> list[str]:
        """Return all supported relative paths under root."""
        paths: list[str] = []
        for p in self.root.rglob("*"):
            if p.is_file() and p.suffix in _LANG_MAP:
                paths.append(str(p.relative_to(self.root)))
        return sorted(paths)

    def iter_symbols_across_repo(self) -> Iterator[tuple[str, Symbol]]:
        """Yield (rel_path, symbol) for every symbol in the repo."""
        for rel_path in self.scan_directory():
            for sym in self.get_symbols(rel_path):
                yield rel_path, sym

    def evict(self, rel_path: str) -> None:
        """Manually evict a file from the L4 cache."""
        self._source_cache.pop(rel_path, None)

    def cache_stats(self) -> dict[str, int]:
        return {
            "l1_files": len(self._meta_cache),
            "l2_files": len(self._symbol_cache),
            "l4_files": len(self._source_cache),
            "l4_max": self.max_l4_files,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_meta(self, rel_path: str) -> FileMetadata:
        full = self.root / rel_path
        stat = full.stat()
        lang = _LANG_MAP.get(full.suffix, "unknown")
        try:
            line_count = full.read_text(errors="replace").count("\n")
        except OSError:
            line_count = 0
        return FileMetadata(
            path=rel_path,
            language=lang,
            line_count=line_count,
            size_bytes=stat.st_size,
            last_modified=stat.st_mtime,
        )

    def _evict_if_needed(self) -> None:
        while len(self._source_cache) > self.max_l4_files:
            evicted_key, _ = self._source_cache.popitem(last=False)
            # Optionally keep symbols even after evicting source
            _ = evicted_key
