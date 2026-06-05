"""Gi.Ve Engine - Caveman Optimizer.

Token-saving pre-processor for LLM context.

CLI:
    python core/caveman_optimizer.py ./my_project
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_INCLUDE = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".html", ".css", ".json", ".md", ".yml", ".yaml",
    ".sql", ".sh", ".toml",
}

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "env",
    "node_modules", "dist", "build", ".next", ".turbo", ".cache",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache",
}

MAX_BYTES_DEFAULT = 200_000



# ============================================================================
# Kanji compression - feature Catalog / All-Access
# ============================================================================
#
# Caveman Pro (ideogrammi) disponibile nel piano Catalogo:
# https://engine.givegroup.it
#
# ============================================================================
# Folder bundler (existing)
# ============================================================================


@dataclass
class FileStat:
    path: str
    original_chars: int
    optimized_chars: int

    @property
    def saved_pct(self) -> float:
        if not self.original_chars:
            return 0.0
        return round(100 * (1 - self.optimized_chars / self.original_chars), 1)


@dataclass
class Bundle:
    text: str
    files: list[FileStat] = field(default_factory=list)

    @property
    def stats(self) -> dict:
        orig = sum(f.original_chars for f in self.files)
        opt = sum(f.optimized_chars for f in self.files)
        return {
            "files": len(self.files),
            "original_chars": orig,
            "optimized_chars": opt,
            "saved_chars": orig - opt,
            "saved_pct": round(100 * (1 - opt / orig), 1) if orig else 0.0,
            "approx_tokens_original": orig // 4,
            "approx_tokens_optimized": opt // 4,
        }


class CavemanOptimizer:
    """Walk a folder, compact code, return a single bundle string."""

    def __init__(
        self,
        root: str | os.PathLike,
        include: Optional[Iterable[str]] = None,
        exclude_dirs: Optional[Iterable[str]] = None,
        max_bytes: int = MAX_BYTES_DEFAULT,
    ) -> None:
        self.root = Path(root).resolve()
        if not self.root.exists():
            raise FileNotFoundError(f"Root not found: {self.root}")
        self.include = set(include) if include else DEFAULT_INCLUDE
        self.exclude_dirs = set(exclude_dirs) if exclude_dirs else DEFAULT_EXCLUDE_DIRS
        self.max_bytes = max_bytes

    def _iter_files(self) -> Iterable[Path]:
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in self.exclude_dirs]
            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix.lower() in self.include:
                    yield p

    @staticmethod
    def _compact_python(source: str) -> str:
        try:
            tokens = tokenize.generate_tokens(io.StringIO(source).readline)
            out: list = []
            prev_type = tokenize.INDENT
            for tok in tokens:
                ttype, tstring, *_ = tok
                if ttype == tokenize.COMMENT:
                    continue
                if (
                    ttype == tokenize.STRING
                    and prev_type in (
                        tokenize.INDENT, tokenize.NEWLINE, tokenize.NL, tokenize.ENCODING,
                    )
                ):
                    continue
                out.append(tok)
                if ttype not in (tokenize.NL, tokenize.COMMENT):
                    prev_type = ttype
            return tokenize.untokenize(out)
        except (tokenize.TokenizeError, IndentationError):
            stripped = re.sub(r"(?m)^\s*#.*$", "", source)
            return CavemanOptimizer._squeeze_whitespace(stripped)

    @staticmethod
    def _compact_c_like(source: str) -> str:
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        source = re.sub(r"(^|[^:\"'])//[^\n]*", r"\1", source)
        return CavemanOptimizer._squeeze_whitespace(source)

    @staticmethod
    def _compact_html(source: str) -> str:
        return CavemanOptimizer._squeeze_whitespace(
            re.sub(r"<!--.*?-->", "", source, flags=re.S)
        )

    @staticmethod
    def _compact_shell_like(source: str) -> str:
        source = re.sub(r"(?m)^\s*#.*$", "", source)
        return CavemanOptimizer._squeeze_whitespace(source)

    @staticmethod
    def _compact_sql(source: str) -> str:
        source = re.sub(r"(?m)--[^\n]*", "", source)
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        return CavemanOptimizer._squeeze_whitespace(source)

    @staticmethod
    def _compact_markdown(source: str) -> str:
        return CavemanOptimizer._squeeze_whitespace(source, preserve_blank_lines=1)

    @staticmethod
    def _squeeze_whitespace(text: str, preserve_blank_lines: int = 0) -> str:
        text = re.sub(r"[ \t]+$", "", text, flags=re.M)
        max_blanks = max(0, preserve_blank_lines)
        text = re.sub(r"\n{%d,}" % (max_blanks + 2), "\n" * (max_blanks + 1), text)
        return text.strip() + "\n"

    def _compact(self, suffix: str, source: str) -> str:
        s = suffix.lower()
        if s == ".py":
            return self._compact_python(source)
        if s in {".js", ".ts", ".tsx", ".jsx", ".css", ".json"}:
            return self._compact_c_like(source)
        if s == ".html":
            return self._compact_html(source)
        if s in {".sh", ".yml", ".yaml", ".toml"}:
            return self._compact_shell_like(source)
        if s == ".sql":
            return self._compact_sql(source)
        if s == ".md":
            return self._compact_markdown(source)
        return self._squeeze_whitespace(source)

    def build_bundle(self) -> Bundle:
        chunks: list[str] = []
        files: list[FileStat] = []

        for path in sorted(self._iter_files()):
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if len(raw) > self.max_bytes:
                continue
            try:
                source = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue

            compacted = self._compact(path.suffix, source)
            rel = path.relative_to(self.root).as_posix()

            chunks.append(f"### FILE: {rel}\n{compacted}")
            files.append(FileStat(
                path=rel,
                original_chars=len(source),
                optimized_chars=len(compacted),
            ))

        text = "\n".join(chunks)
        return Bundle(text=text, files=files)

    # ---------------------------------------------------------- AGENTS.md

    def generate_agents_md(self, recipe_id: str, recipes_root: Optional[Path] = None) -> str:
        """Produce a kanji-compressed AGENTS.md for the given recipe.

        Reads core/recipes/<recipe_id>/caveman.md if present, otherwise falls
        back to caveman_human.md (and compresses it). The returned text is
        intended to be written as AGENTS.md inside the user's generated
        project so background LLMs (Cursor, Claude Code) read it directly.
        """
        if recipes_root is None:
            recipes_root = Path(__file__).resolve().parent.parent / "core" / "recipes"
            if not recipes_root.exists():
                # When called from inside core/, the path above is wrong;
                # try one level up.
                recipes_root = Path(__file__).resolve().parent / "recipes"

        recipe_dir = recipes_root / recipe_id
        if not recipe_dir.exists():
            raise FileNotFoundError(f"Recipe not found: {recipe_dir}")

        compressed_path = recipe_dir / "caveman.md"
        human_path = recipe_dir / "caveman_human.md"

        if compressed_path.exists():
            body = compressed_path.read_text(encoding="utf-8")
        elif human_path.exists():
            body = human_path.read_text(encoding="utf-8")
        else:
            raise FileNotFoundError(
                f"Neither caveman.md nor caveman_human.md found in {recipe_dir}"
            )

        header = (
            f"# AGENTS.md\n"
            f"# Recipe: {recipe_id}\n"
            f"# Format: kanji-compressed Italian for background LLM agents\n"
            f"# To read in plain Italian: core/caveman_optimizer.py decompress\n"
            f"#\n"
        )
        return header + body.strip() + "\n"


# ============================================================================
# CLI
# ============================================================================




def _cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Compact a folder into a cache-friendly LLM bundle "
                    "and/or compress Italian text into kanji."
    )
    parser.add_argument("root", nargs="?", help="Folder to scan (optional if --demo)")
    parser.add_argument("-o", "--out", help="Write bundle to this file (default: stdout)")
    parser.add_argument("--stats-only", action="store_true", help="Print only the stats JSON")
    parser.add_argument("--agents-md", metavar="RECIPE_ID",
                        help="Generate AGENTS.md for the given recipe")
    args = parser.parse_args(argv)

    if args.agents_md:
        opt = CavemanOptimizer(args.root or ".")
        print(opt.generate_agents_md(args.agents_md))
        return 0

    if not args.root:
        parser.error("root folder is required unless --demo / --compress / --agents-md is used")

    opt = CavemanOptimizer(args.root)
    bundle = opt.build_bundle()

    if args.stats_only:
        print(json.dumps(bundle.stats, indent=2))
        return 0

    if args.out:
        Path(args.out).write_text(bundle.text, encoding="utf-8")
        print(json.dumps(bundle.stats, indent=2))
        print(f"# bundle written to {args.out}")
    else:
        sys.stdout.write(bundle.text)
        sys.stderr.write("\n--- stats ---\n")
        sys.stderr.write(json.dumps(bundle.stats, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
