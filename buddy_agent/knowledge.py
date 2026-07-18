"""PDF knowledge base: extraction, chunking, and retrieval.

Retrieval works fully offline. If the `nomic-embed-text` embedding model is
available in Ollama it is used for semantic search; otherwise we fall back to
a pure-Python BM25 keyword search, which needs no extra downloads at all.
"""

from __future__ import annotations

import math
import re

import ollama
from pypdf import PdfReader

EMBED_MODEL = "nomic-embed-text"
CHUNK_SIZE = 900      # characters per chunk
CHUNK_OVERLAP = 150   # characters carried over between chunks


def extract_pdf_text(path: str) -> tuple[str, int]:
    """Return (full_text, page_count) for a PDF file."""
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages), len(pages)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries."""
    text = re.sub(r"[ \t]+", " ", text)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 1 > size and current:
            chunks.append(current.strip())
            current = current[-overlap:] if overlap else ""
        current = (current + " " + para).strip()
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class _BM25:
    """Minimal BM25 ranking over tokenized chunks (no dependencies)."""

    K1 = 1.5
    B = 0.75

    def __init__(self, chunks: list[str]):
        self.docs = [_tokenize(c) for c in chunks]
        self.doc_lens = [len(d) for d in self.docs]
        self.avgdl = (sum(self.doc_lens) / len(self.docs)) if self.docs else 0.0
        self.idf: dict[str, float] = {}
        n = len(self.docs)
        df: dict[str, int] = {}
        for doc in self.docs:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        for term, count in df.items():
            self.idf[term] = math.log(1 + (n - count + 0.5) / (count + 0.5))

    def scores(self, query: str) -> list[float]:
        q_terms = _tokenize(query)
        out = []
        for doc, dl in zip(self.docs, self.doc_lens):
            tf: dict[str, int] = {}
            for t in doc:
                tf[t] = tf.get(t, 0) + 1
            score = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                f = tf[term]
                denom = f + self.K1 * (1 - self.B + self.B * dl / (self.avgdl or 1))
                score += self.idf.get(term, 0.0) * f * (self.K1 + 1) / denom
            out.append(score)
        return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class KnowledgeBase:
    """Holds one PDF's chunks and answers 'which chunks match this question?'."""

    def __init__(self, client: ollama.Client, pdf_path: str):
        self.client = client
        self.pdf_path = pdf_path
        text, self.page_count = extract_pdf_text(pdf_path)
        self.chunks = chunk_text(text)
        if not self.chunks:
            raise ValueError(
                f"No readable text found in {pdf_path}. "
                "It may be a scanned/image-only PDF."
            )

        self.embeddings: list[list[float]] | None = None
        if self._embedder_available():
            self.embeddings = self._embed(self.chunks)
            self.mode = "semantic search"
        else:
            self.mode = "keyword search"
        self._bm25 = _BM25(self.chunks) if self.embeddings is None else None

    def _embedder_available(self) -> bool:
        try:
            self.client.embed(model=EMBED_MODEL, input=["ping"])
            return True
        except Exception:
            return False

    def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 32):
            batch = texts[i : i + 32]
            resp = self.client.embed(model=EMBED_MODEL, input=batch)
            vectors.extend(resp["embeddings"])
        return vectors

    def retrieve(self, query: str, k: int = 4) -> list[str]:
        """Return the top-k chunks most relevant to the query."""
        if self.embeddings is not None:
            q_vec = self.client.embed(model=EMBED_MODEL, input=[query])["embeddings"][0]
            scored = [(_cosine(q_vec, vec), i) for i, vec in enumerate(self.embeddings)]
        else:
            scored = [(s, i) for i, s in enumerate(self._bm25.scores(query)) if s > 0]
            if not scored:  # no keyword overlap at all -> give opening chunks
                return self.chunks[:k]
        scored.sort(reverse=True)
        return [self.chunks[i] for _, i in scored[:k]]

    def sample_across(self, k: int = 4) -> list[str]:
        """Chunks spread evenly through the book (for overviews and quizzes)."""
        if len(self.chunks) <= k:
            return list(self.chunks)
        step = len(self.chunks) / k
        return [self.chunks[int(i * step)] for i in range(k)]
