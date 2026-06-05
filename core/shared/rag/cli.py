"""CLI entry points for the RAG module.

Run via:
    python -m core.shared.rag.cli library-list --manifest fixtures/library_manifest.json
    python -m core.shared.rag.cli library-fetch --slug manuali-anthropic
    python -m core.shared.rag.cli verify-library
    python -m core.shared.rag.cli rebuild --db ~/.givengine/data/atheneo-light.db --dimension 768

User-facing copy is in italian per Punto 18 (italiano-first Catalogo).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from core.shared.rag import RAG_VERSION
from core.shared.rag.exceptions import LibraryError, RAGError
from core.shared.rag.library_loader import LibraryLoader
from core.shared.rag.vector_store import VectorStore


Fetcher = Callable[[str, Path], Path]


def _add_manifest_arg(p: argparse.ArgumentParser) -> None:
    default_manifest = (
        Path(__file__).resolve().parent / "fixtures" / "library_manifest.json"
    )
    p.add_argument(
        "--manifest",
        type=Path,
        default=default_manifest,
        help="Percorso del manifest libreria locale.",
    )
    p.add_argument(
        "--manifest-url",
        default=None,
        help="URL remoto del manifest libreria (alternativa a --manifest).",
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".givengine" / "library",
        help="Cartella cache locale per skill scaricate.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag",
        description=f"Gi.Ve RAG CLI (v{RAG_VERSION}). Italiano-first.",
    )
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser(
        "library-list",
        help="Elenca le skill disponibili nella libreria preindicizzata.",
    )
    _add_manifest_arg(p_list)
    p_list.add_argument(
        "--embedder",
        default=None,
        help="Filtra per modello embedder (multilingual-e5-base | bge-m3).",
    )

    p_fetch = sub.add_parser(
        "library-fetch",
        help="Scarica una skill specifica dalla libreria.",
    )
    _add_manifest_arg(p_fetch)
    p_fetch.add_argument("--slug", required=True, help="Slug della skill.")
    p_fetch.add_argument(
        "--no-verify-signature",
        action="store_true",
        help="Salta verifica firma (uso interno test, sconsigliato in produzione).",
    )

    p_verify = sub.add_parser(
        "verify-library",
        help="Verifica integrità della libreria locale installata.",
    )
    _add_manifest_arg(p_verify)

    p_rebuild = sub.add_parser(
        "rebuild",
        help="Apre / inizializza l'indice vettoriale locale.",
    )
    p_rebuild.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Percorso del file SQLite del vector store.",
    )
    p_rebuild.add_argument(
        "--dimension",
        type=int,
        required=True,
        help="Dimensione vettori (768 per e5-base, 1024 per bge-m3).",
    )

    return parser


def main(argv: list[str] | None = None, fetcher: Fetcher | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    try:
        if args.command == "library-list":
            return _cmd_library_list(args, fetcher)
        if args.command == "library-fetch":
            return _cmd_library_fetch(args, fetcher)
        if args.command == "verify-library":
            return _cmd_verify_library(args, fetcher)
        if args.command == "rebuild":
            return _cmd_rebuild(args)
        parser.print_help(sys.stderr)
        return 2
    except LibraryError as exc:
        slug_hint = f" (slug: {exc.slug})" if exc.slug else ""
        print(f"errore libreria: {exc}{slug_hint}", file=sys.stderr)
        return 1
    except RAGError as exc:
        print(f"errore RAG: {exc}", file=sys.stderr)
        return 1


def _build_loader(args: argparse.Namespace, fetcher: Fetcher | None) -> LibraryLoader:
    return LibraryLoader(
        manifest_path=args.manifest if not args.manifest_url else None,
        manifest_url=args.manifest_url,
        cache_dir=args.cache_dir,
        fetcher=fetcher,
    )


def _cmd_library_list(args: argparse.Namespace, fetcher: Fetcher | None) -> int:
    loader = _build_loader(args, fetcher)
    skills = loader.list_available_skills(embedder_model=args.embedder)
    if not skills:
        print("Nessuna skill trovata nel manifest.")
        return 0
    print(f"Skill disponibili ({len(skills)}):")
    for s in skills:
        print(
            f"  - {s.slug}  [{s.embedder_model} dim={s.dimension}]  "
            f"v{s.version}  {s.size_mb:.1f} MB"
        )
        print(f"      {s.name} — {s.description}")
    return 0


def _cmd_library_fetch(args: argparse.Namespace, fetcher: Fetcher | None) -> int:
    loader = _build_loader(args, fetcher)
    path = loader.download_skill(
        slug=args.slug,
        verify_signature=not args.no_verify_signature,
    )
    print(f"Scaricata skill '{args.slug}' in: {path}")
    return 0


def _cmd_verify_library(args: argparse.Namespace, fetcher: Fetcher | None) -> int:
    loader = _build_loader(args, fetcher)
    skills = loader.list_available_skills()
    cache_dir = Path(args.cache_dir)
    if not cache_dir.exists():
        print(f"Cache locale non esistente: {cache_dir}")
        print(f"Skill installate: 0 / {len(skills)} disponibili nel manifest.")
        return 0
    installed = list(cache_dir.glob("*.atheneo-light")) + list(
        cache_dir.glob("*.atheneo-pro")
    )
    print(
        f"Skill installate localmente: {len(installed)} / "
        f"{len(skills)} disponibili nel manifest."
    )
    for path in installed:
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"  - {path.name}  ({size_mb:.1f} MB)")
    return 0


def _cmd_rebuild(args: argparse.Namespace) -> int:
    store = VectorStore(db_path=args.db, dimension=args.dimension)
    stats = store.stats()
    print("Indice vettoriale aperto:")
    print(f"  path: {args.db}")
    print(f"  dimensione vettori: {stats['dimension']}")
    print(f"  totale chunks: {stats['total_chunks']}")
    print(f"  totale documenti: {stats['total_documents']}")
    if stats["last_indexed_at"]:
        print(f"  ultimo aggiornamento: {stats['last_indexed_at']}")
    store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
