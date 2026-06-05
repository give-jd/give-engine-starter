"""BM25 sparse retrieval v0.5.0.

Okapi BM25 (Robertson/Sparck Jones 1995) ranking puro Python (no deps esterne).

Parametri default:
- k1 = 1.5 (saturation termine, range 1.2-2.0)
- b  = 0.75 (length normalization, range 0.5-0.9)

Pattern:
    idx = BM25Index()
    idx.add_chunk("c1", "art 6 GDPR base giuridica liceita")
    idx.add_chunk("c2", "art 9 GDPR categorie dati sanitari")
    idx.build()
    results = idx.search("art 9 GDPR", k=10)
    # -> [BM25Hit(chunk_id="c2", score=2.34), ...]

Pre-processing italiano:
- lowercase
- rimuove punteggiatura
- split whitespace
- filtro stop-word IT (configurabile)
- no stemming (preserva varianti morfologiche per recall)
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field


STOP_WORDS_IT: frozenset[str] = frozenset({
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
    "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
    "del", "dello", "della", "dei", "degli", "delle",
    "al", "allo", "alla", "ai", "agli", "alle",
    "dal", "dallo", "dalla", "dai", "dagli", "dalle",
    "nel", "nello", "nella", "nei", "negli", "nelle",
    "col", "coi", "cogli", "colle",
    "sul", "sullo", "sulla", "sui", "sugli", "sulle",
    "e", "ed", "o", "od", "ma", "anche", "pure",
    "che", "chi", "cui", "quale", "quali", "quanto", "quanti",
    "non", "se", "ne", "ci", "vi",
    "essere", "avere", "fare", "stare",
    "è", "sono", "ha", "hanno", "ero", "era", "erano",
    "questo", "questa", "questi", "queste",
    "quello", "quella", "quelli", "quelle",
    "molto", "poco", "tanto", "alcuno", "alcuni", "qualche",
    "tutto", "tutti", "ogni", "altro", "altri",
    "come", "quando", "perché", "perche", "dove",
})

_TOKEN_RE = re.compile(r"[a-zàèéìòù0-9]+", re.IGNORECASE)


@dataclass(frozen=True)
class BM25Hit:
    chunk_id: str
    score: float


@dataclass
class BM25Index:
    k1: float = 1.5
    b: float = 0.75
    stop_words: frozenset[str] = field(default_factory=lambda: STOP_WORDS_IT)
    _docs: dict[str, list[str]] = field(default_factory=dict)
    _doc_lens: dict[str, int] = field(default_factory=dict)
    _doc_freqs: dict[str, Counter] = field(default_factory=dict)
    _df: Counter = field(default_factory=Counter)
    _avg_dl: float = 0.0
    _idf: dict[str, float] = field(default_factory=dict)
    _built: bool = False

    def tokenize(self, text: str) -> list[str]:
        return [
            t for t in (m.group(0).lower() for m in _TOKEN_RE.finditer(text))
            if t not in self.stop_words and len(t) > 1
        ]

    def add_chunk(self, chunk_id: str, text: str) -> None:
        if self._built:
            raise RuntimeError("Index gia' build()-ato. Re-instanzia per modifiche.")
        if chunk_id in self._docs:
            raise ValueError(f"chunk_id duplicato: {chunk_id}")
        tokens = self.tokenize(text)
        self._docs[chunk_id] = tokens
        self._doc_lens[chunk_id] = len(tokens)
        freqs = Counter(tokens)
        self._doc_freqs[chunk_id] = freqs
        for term in freqs:
            self._df[term] += 1

    def build(self) -> None:
        if not self._docs:
            self._avg_dl = 0.0
            self._built = True
            return
        n_docs = len(self._docs)
        self._avg_dl = sum(self._doc_lens.values()) / n_docs
        for term, df in self._df.items():
            self._idf[term] = math.log(
                ((n_docs - df + 0.5) / (df + 0.5)) + 1.0
            )
        self._built = True

    def search(self, query: str, k: int = 10,
              min_score: float = 0.0) -> list[BM25Hit]:
        if not self._built:
            raise RuntimeError("Chiamare build() prima di search()")
        if k < 1:
            raise ValueError("k deve essere >= 1")
        q_terms = self.tokenize(query)
        if not q_terms or not self._docs:
            return []
        scores: dict[str, float] = {}
        for doc_id, freqs in self._doc_freqs.items():
            dl = self._doc_lens[doc_id]
            score = 0.0
            for term in q_terms:
                if term not in freqs:
                    continue
                idf = self._idf.get(term, 0.0)
                tf = freqs[term]
                norm = 1 - self.b + self.b * (dl / max(self._avg_dl, 1.0))
                score += idf * (tf * (self.k1 + 1)) / (tf + self.k1 * norm)
            if score > min_score:
                scores[doc_id] = score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [BM25Hit(chunk_id=cid, score=s) for cid, s in ranked[:k]]

    def n_docs(self) -> int:
        return len(self._docs)

    def n_terms(self) -> int:
        return len(self._df)
