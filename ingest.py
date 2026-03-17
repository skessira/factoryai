"""
FactoryAI — Ingestion Pipeline
-------------------------------
Reads PDF manuals from the /docs folder, chunks them, generates embeddings,
and stores everything in a local JSON vector store.

Run this script once (or whenever documents change) before starting the API.

Usage:
    python ingest.py
"""

import json
import time
from pathlib import Path

import numpy as np
import pypdf
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Configuration — tune these without touching the pipeline logic
# ---------------------------------------------------------------------------
DOCS_FOLDER      = "docs"                  # folder containing PDF files
CHUNK_SIZE       = 500                     # characters per chunk
CHUNK_OVERLAP    = 50                      # characters of overlap between chunks
VECTOR_STORE     = "vector_store.json"     # where embeddings are saved to disk
EMBEDDING_MODEL  = "all-MiniLM-L6-v2"     # local sentence-transformers model


# ---------------------------------------------------------------------------
# Step 1: LOAD & PARSE
# Extract text from each page of a PDF file.
# Returns a list of dicts — one per page — with text and metadata.
# ---------------------------------------------------------------------------
def load_pdf(path: Path) -> list[dict]:
    pages = []
    reader = pypdf.PdfReader(str(path))

    for page_num, page in enumerate(reader.pages):
        text = page.extract_text()

        # Skip pages with no extractable text (scanned images, blank pages)
        if not text or not text.strip():
            continue

        pages.append({
            "text":        text,
            "page_number": page_num + 1,   # 1-indexed for human readability
            "source":      path.name
        })

    return pages


# ---------------------------------------------------------------------------
# Step 2: CHUNK
# Split a block of text into overlapping chunks.
# Overlap preserves context across chunk boundaries.
# ---------------------------------------------------------------------------
def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    chunks = []
    start = 0

    while start < len(text):
        end   = start + chunk_size
        chunk = text[start:end]

        if chunk.strip():   # skip chunks that are only whitespace
            chunks.append(chunk)

        start = end - overlap   # step back by overlap to create continuity

    return chunks


# ---------------------------------------------------------------------------
# Step 3: STORE (numpy-based, no compilation required)
#
# Each entry in the store is a dict:
#   {
#     "id":        str,         unique chunk identifier
#     "text":      str,         raw chunk text (injected into LLM prompt)
#     "embedding": list[float], 384-dimensional vector
#     "metadata":  dict         source, page_number, chunk_index
#   }
#
# Similarity search uses cosine similarity:
#   cos(A, B) = (A · B) / (|A| * |B|)
#   Result is 1.0 (identical) → 0.0 (unrelated) → -1.0 (opposite)
#
# This is the same calculation ChromaDB/pgvector run internally —
# we're just doing it explicitly here so you can see what's happening.
# ---------------------------------------------------------------------------
def cosine_similarity(a: list[float], b: list[float]) -> float:
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def load_store(path: str) -> dict:
    """Load existing vector store from disk, or return empty store."""
    if Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"chunks": []}


def save_store(store: dict, path: str) -> None:
    """Persist vector store to disk as JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def upsert_chunk(store: dict, chunk_id: str, text: str,
                 embedding: list[float], metadata: dict) -> None:
    """Insert chunk if new, update if ID already exists (safe to re-run)."""
    for existing in store["chunks"]:
        if existing["id"] == chunk_id:
            existing["text"]      = text
            existing["embedding"] = embedding
            existing["metadata"]  = metadata
            return
    store["chunks"].append({
        "id":        chunk_id,
        "text":      text,
        "embedding": embedding,
        "metadata":  metadata
    })


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main():
    start_time = time.time()

    # --- Validate docs folder ---
    docs_path = Path(DOCS_FOLDER)
    if not docs_path.exists():
        print(f"ERROR: docs folder not found at '{DOCS_FOLDER}'")
        print("Create a 'docs' folder and place your PDF manuals inside it.")
        return

    pdf_files = list(docs_path.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in '{DOCS_FOLDER}'. Add some PDFs and re-run.")
        return

    print(f"Found {len(pdf_files)} PDF file(s) in '{DOCS_FOLDER}'")

    # --- Load embedding model (runs locally, no API key needed) ---
    print(f"\nLoading embedding model '{EMBEDDING_MODEL}'...")
    print("(First run downloads ~90MB — this may take a moment)")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print("Embedding model ready.")

    # --- Load or create vector store ---
    print(f"\nLoading vector store from '{VECTOR_STORE}'...")
    store = load_store(VECTOR_STORE)
    existing_count = len(store["chunks"])
    print(f"  {existing_count} existing chunk(s) found.")

    # --- Process each PDF ---
    total_chunks = 0

    for pdf_path in pdf_files:
        print(f"\n--- {pdf_path.name} ---")

        # LOAD & PARSE
        pages = load_pdf(pdf_path)
        print(f"  Extracted text from {len(pages)} page(s)")

        if not pages:
            print("  WARNING: No extractable text found. Skipping (possibly scanned PDF).")
            continue

        file_chunks = 0

        for page in pages:

            # CHUNK
            chunks = chunk_text(page["text"], CHUNK_SIZE, CHUNK_OVERLAP)

            for i, chunk in enumerate(chunks):

                # Build a unique, deterministic ID for this chunk
                chunk_id = f"{pdf_path.stem}_p{page['page_number']}_c{i}"

                # EMBED — convert chunk text to a 384-dimensional vector
                embedding = model.encode(chunk).tolist()

                # STORE — upsert into our JSON store
                upsert_chunk(
                    store     = store,
                    chunk_id  = chunk_id,
                    text      = chunk,
                    embedding = embedding,
                    metadata  = {
                        "source":      page["source"],
                        "page_number": page["page_number"],
                        "chunk_index": i
                    }
                )

                file_chunks += 1

        print(f"  Stored {file_chunks} chunk(s)")
        total_chunks += file_chunks

    # --- Save to disk ---
    save_store(store, VECTOR_STORE)

    # --- Summary ---
    elapsed = time.time() - start_time
    print(f"\n{'='*40}")
    print(f"Ingestion complete.")
    print(f"  Files processed  : {len(pdf_files)}")
    print(f"  Total chunks     : {total_chunks}")
    print(f"  Time taken       : {elapsed:.1f}s")
    print(f"  Vector store     : {VECTOR_STORE}")
    print(f"{'='*40}")
    print("\nThe knowledge base is ready. You can now start the API with:")
    print("  uvicorn main:app --reload")


if __name__ == "__main__":
    main()
