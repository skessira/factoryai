# FactoryAI — Ingestion Pipeline Spec

## What We're Building
A standalone Python script (`ingest.py`) that processes a folder of PDF manuals,
chunks them into searchable segments, generates embeddings for each chunk, and
stores them in a local vector store. This is the offline pipeline that must run
before any user query can be answered — it prepares the knowledge base.

## Requirements
- Accept a folder path containing one or more PDF files
- Extract text from each PDF
- Split text into chunks suitable for embedding
- Generate a vector embedding for each chunk
- Store each chunk (text + embedding + metadata) in a vector store
- Print progress so the operator can see what's happening
- Be re-runnable: ingesting the same folder twice should not create duplicates

## Constraints
- Pure Python script — no web server, no API, runs from the command line
- No API keys required for this iteration (local embedding model)
- Vector store: ChromaDB (embedded, no separate server required for local dev)
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (runs locally, free)
- PDF parsing: `pypdf`

## Architecture Decisions
- **ChromaDB over pgvector (for now):** pgvector requires a running PostgreSQL
  instance. For local development and learning, ChromaDB is embedded — no Docker,
  no database server. The switch to pgvector in production is documented in
  DECISIONS.md. The chunking/embedding logic is identical either way.
- **Local embedding model over OpenAI embeddings:** Avoids API key dependency
  and cost during development. `all-MiniLM-L6-v2` is fast, lightweight, and
  produces good semantic embeddings for technical text. Can be swapped for
  `text-embedding-3-small` in production with no structural changes.
- **Chunk size: 500 tokens, overlap: 50 tokens:** Overlap preserves context
  across chunk boundaries (e.g., a sentence that starts in one chunk and
  continues in the next). Tunable — documented as a variable, not a magic number.

## Data Model — What Gets Stored Per Chunk

```
{
  "id":        "siemens_s7_manual_chunk_0042",   # unique ID
  "text":      "...",                             # raw chunk text
  "embedding": [0.021, -0.143, ...],              # vector (384 dimensions)
  "metadata": {
    "source":      "Siemens_S7-1500_Manual.pdf",
    "page_number": 47,
    "chunk_index": 42
  }
}
```

## Pipeline Steps

```
Input: /docs folder containing PDF files

1. LOAD    — iterate over all .pdf files in the folder
2. PARSE   — extract raw text page by page using pypdf
3. CHUNK   — split text into overlapping chunks (500 tokens, 50 overlap)
4. EMBED   — pass each chunk through all-MiniLM-L6-v2 → 384-dim vector
5. STORE   — upsert chunk (text + embedding + metadata) into ChromaDB
6. REPORT  — print summary: files processed, chunks created, time taken

Output: ChromaDB collection populated and ready for similarity search
```

## Out of Scope (this iteration)
- OCR for scanned PDFs (assumes text-layer PDFs)
- Incremental ingestion / change detection
- Chunk quality evaluation
- pgvector integration (next iteration)
- Authentication / access control
