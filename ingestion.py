"""
Ingestion pipeline for the NimbusPay knowledge base.

This is the file you run ONCE (or whenever data/*.md changes) to build the
vector store. Nothing else in this project should ever write to ChromaDB --
only this file builds it; everything else (tools.py, graph.py) only ever
calls query_kb() to read from it.

main task:read the docs, chunk them, embed them, index them in a vector store.
"""

from __future__ import annotations
from pathlib import Path

import chromadb

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PERSIST_DIR = PROJECT_ROOT / "chroma_db"
COLLECTION_NAME = "nimbuspay_kb"

# ---------------------------------------------------------------------------
# Manual metadata overrides
# ---------------------------------------------------------------------------
# Only the docs where "how recent is this" actually matters get a date.
# Later code (guardrails / router prompt) uses this to prefer the newer
# refund policy instead of silently picking one of two contradicting chunks.

DOC_METADATA_OVERRIDES: dict[str, dict] = {
    "refund_policy_2024.md": {"effective_date": "2024-01-01"},
    "refund_policy_2026.md": {"effective_date": "2026-01-01"},
}


# ---------------------------------------------------------------------------
# Loading + chunking
# ---------------------------------------------------------------------------

def _extract_title_and_body(text: str, fallback: str) -> tuple[str, str]:
    """
    Pull the first markdown heading out as the title, and return the body
    with that heading line removed -- we don't want "# Fees Schedule" by
    itself turning into a useless 3-word chunk later.
    """
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith("#"):
            title = line.strip().lstrip("#").strip()
            body = "\n".join(lines[:idx] + lines[idx + 1:])
            return title, body.strip()
    return fallback, text


def load_documents(data_dir: Path = DATA_DIR) -> list[dict]:
    """Read every .md file in data_dir into {filename, title, body}."""
    if not data_dir.exists():
        raise FileNotFoundError(
            f"\n\nNo such folder: {data_dir}\n"
            f"Run generate_kb.py from your project root first -- it creates "
            f"this data/ folder and fills it with the 15 KB documents.\n"
        )

    docs = []
    for path in sorted(data_dir.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        title, body = _extract_title_and_body(raw, fallback=path.stem)
        docs.append({"filename": path.name, "title": title, "body": body})

    if not docs:
        raise FileNotFoundError(
            f"\n\nFound {data_dir}, but it has no .md files in it.\n"
            f"Run generate_kb.py from your project root to populate it, "
            f"or copy your existing data/*.md files into:\n  {data_dir}\n"
        )

    return docs


def _split_into_paragraphs(text: str) -> list[str]:
    """Markdown docs separate ideas with blank lines -- split on those first."""
    return [b.strip() for b in text.split("\n\n") if b.strip()]


def _sliding_window(text: str, size: int, overlap: int) -> list[str]:
    """Fallback for the rare paragraph that's longer than max_words on its own."""
    words = text.split()
    out = []
    start = 0
    while start < len(words):
        end = start + size
        out.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = end - overlap
    return out


def chunk_body(body: str, max_words: int = 60, overlap_words: int = 15) -> list[str]:
    """
    Chunk by paragraph first, so a chunk is a complete FAQ entry / section
    rather than an arbitrary word-count cut. Consecutive small paragraphs
    get merged up to max_words; a paragraph bigger than max_words on its
    own falls back to a sliding window so no chunk is unboundedly long.
    """
    paragraphs = _split_into_paragraphs(body)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para.split())

        if para_len > max_words:
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            chunks.extend(_sliding_window(para, max_words, overlap_words))
            continue

        if current_len + para_len > max_words and current:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0

        current.append(para)
        current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


# ---------------------------------------------------------------------------
# Build the vector store
# ---------------------------------------------------------------------------

def build_vector_store(data_dir: Path = DATA_DIR, persist_dir: Path = PERSIST_DIR):
    """
    Wipe and rebuild the vector store from data/*.md. Run this directly
    (or whenever the KB docs change) -- the agent itself never calls this,
    it only ever calls query_kb().
    """
    client = chromadb.PersistentClient(path=str(persist_dir))

    # Start clean every run so re-running this never leaves duplicate/stale chunks.
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    # No embedding_function passed in, on purpose -> Chroma uses its bundled
    # default model (a small MiniLM, run locally via onnxruntime, downloaded
    # once on first use). Free, needs no API key, right-sized for a 15-25
    # document KB -- no reason to pull in a heavier framework for this.
    collection = client.create_collection(COLLECTION_NAME)

    docs = load_documents(data_dir)
    all_chunks, all_metadatas, all_ids = [], [], []

    for doc in docs:
        chunks = chunk_body(doc["body"])
        overrides = DOC_METADATA_OVERRIDES.get(doc["filename"], {})
        for i, chunk in enumerate(chunks):
            # Prefix every chunk with its title -- a chunk read in isolation
            # ("...takes 7-10 business days") is ambiguous without it.
            all_chunks.append(f"{doc['title']}\n\n{chunk}")
            all_metadatas.append({
                "source": doc["filename"],
                "title": doc["title"],
                "chunk_index": i,
                **overrides,
            })
            all_ids.append(f"{doc['filename']}::{i}")

    collection.add(documents=all_chunks, metadatas=all_metadatas, ids=all_ids)
    print(f"Indexed {len(all_chunks)} chunks from {len(docs)} documents "
          f"into '{COLLECTION_NAME}' at {persist_dir}/")
    return collection


# ---------------------------------------------------------------------------
# Query the vector store (this is what tools.py / graph.py actually call)
# ---------------------------------------------------------------------------

def get_collection(persist_dir: Path = PERSIST_DIR):
    client = chromadb.PersistentClient(path=str(persist_dir))
    return client.get_collection(COLLECTION_NAME)


def query_kb(query: str, k: int = 4, persist_dir: Path = PERSIST_DIR) -> list[dict]:
    """
    Embed `query`, return the top-k most similar chunks as plain dicts.
    Never call build_vector_store() from here -- this only ever reads.
    """
    collection = get_collection(persist_dir)
    results = collection.query(query_texts=[query], n_results=k)

    hits = []
    for text, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        hits.append({
            "text": text,
            "source": meta.get("source"),
            "title": meta.get("title"),
            "effective_date": meta.get("effective_date"),
            "distance": dist,
        })
    return hits


if __name__ == "__main__":
    build_vector_store()
    print("\n--- sanity check: 'how long do refunds take' ---")
    for hit in query_kb("how long do refunds take", k=3):
        print(f"[{hit['source']}] dist={hit['distance']:.3f}  {hit['text'][:90]}...")