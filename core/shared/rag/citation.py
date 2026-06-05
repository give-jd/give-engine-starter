"""Citation parser e dataclass per sintesi AI con citation obbligatoria.

Pattern atteso nella risposta LLM:
    "Affermazione X [chunk N]. Affermazione Y [chunk M]."

Supporta varianti `[chunk N]`, `[chunk_N]`, case-insensitive. Le label sono
normalizzate a "chunk N" lowercase con spazio.

Una risposta è considerata `is_validated=True` se:
- contiene almeno una citation
- TUTTE le citation puntano a chunks effettivamente presenti nei chunks forniti
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.shared.rag.vector_store import ScoredChunk


_CITATION_PATTERN = re.compile(r"\[\s*chunk[\s_]+(\d+)\s*\]", re.IGNORECASE)


@dataclass
class CitedResponse:
    text: str
    citations: dict[str, ScoredChunk] = field(default_factory=dict)
    is_validated: bool = False


class CitationParser:
    def parse(
        self,
        raw_response: str,
        available_chunks: list[ScoredChunk],
    ) -> CitedResponse:
        if not raw_response:
            return CitedResponse(text=raw_response, citations={}, is_validated=False)

        chunk_lookup: dict[str, ScoredChunk] = {
            f"chunk {i + 1}": sc for i, sc in enumerate(available_chunks)
        }

        citations: dict[str, ScoredChunk] = {}
        all_referenced_valid = True
        found_any = False
        for match in _CITATION_PATTERN.finditer(raw_response):
            found_any = True
            n = match.group(1)
            label = f"chunk {n}"
            if label in chunk_lookup:
                citations[label] = chunk_lookup[label]
            else:
                all_referenced_valid = False

        is_validated = found_any and all_referenced_valid and bool(citations)
        return CitedResponse(
            text=raw_response,
            citations=citations,
            is_validated=is_validated,
        )

    def reject_uncited(self, response: CitedResponse) -> bool:
        """True se la risposta NON è validata e va rigenerata."""
        return not response.is_validated
