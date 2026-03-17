# FactoryAI — Manufacturing Knowledge Assistant

A RAG-powered chatbot API for factory floor operators and maintenance engineers.
Ask questions in natural language and get answers grounded in your actual equipment documentation.

Built as part of a structured SA/SE technical upskilling program.

---

## What it does

Factory environments generate enormous amounts of documentation — maintenance manuals,
fault code references, preventive maintenance schedules, safety procedures. FactoryAI
makes this knowledge queryable via a simple REST API.

A maintenance engineer can ask:
> *"What is the maximum operating temperature for the conveyor belt motor?"*

And get back a cited, grounded answer pulled from the actual source document —
not a hallucinated response.

---

## Architecture

```
PDF Manuals
    │
    ▼
[ Ingestion Pipeline ]          ingest.py
    │  Load → Chunk → Embed → Store
    ▼
Vector Store (JSON / pgvector)
    │
    ▼
[ Query Pipeline ]              query.py
    │  Embed question → Similarity search → Prompt assembly → LLM
    ▼
[ FastAPI ]                     main.py
    │  POST /api/v1/ask
    ▼
Structured JSON Response
    { answer, citations, related_sources }
```

**Embedding model:** `all-MiniLM-L6-v2` (runs locally, no API key required)
**LLM:** OpenAI `gpt-4o-mini`
**Vector store:** NumPy cosine similarity (transparent, no build dependencies)

---

## Project structure

```
FactoryAI/
├── main.py              # FastAPI app — routes and Pydantic models
├── query.py             # Query pipeline — retrieval + prompt assembly + LLM call
├── ingest.py            # Ingestion pipeline — PDF → chunks → embeddings → store
├── docs/                # Place PDF manuals here before running ingest.py
├── spec.md              # API design spec (written before code)
├── spec_ingestion.md    # Ingestion pipeline spec
├── DECISIONS.md         # Architecture decisions and trade-offs log
├── requirements.txt     # Python dependencies
└── .env                 # API keys (not committed — see .gitignore)
```

---

## Quickstart

**1. Set up environment**
```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

**2. Add your API key**
```bash
# Create a .env file in the project root
OPENAI_API_KEY=sk-...
```

**3. Add PDF documents**
```bash
# Place your equipment manuals in the docs/ folder
```

**4. Run ingestion**
```bash
python ingest.py
# Reads PDFs → generates embeddings → saves vector_store.json
```

**5. Start the API**
```bash
uvicorn main:app --reload
# Swagger UI available at http://127.0.0.1:8000/docs
```

---

## API

### `POST /api/v1/ask`

```json
{
  "question": "What is the maximum operating temperature for the conveyor belt motor?"
}
```

**Response:**
```json
{
  "answer": "The maximum operating temperature is 85°C. Sustained operation above this threshold triggers thermal protection and requires immediate shutdown.",
  "citations": [
    {
      "source": "conveyor_maintenance_manual.pdf",
      "page_number": 14
    }
  ],
  "related_sources": []
}
```

### `GET /health`
```json
{ "status": "ok", "version": "2.0.0" }
```

---

## Design decisions

See [`DECISIONS.md`](DECISIONS.md) for the full log of architecture choices, trade-offs considered, and where AI assistance was used vs. where domain judgment drove the decision.

---

## Domain context

Built specifically for the **manufacturing and industrial IoT** domain, drawing on experience with Smart Factory, Connected Products, and industrial automation at Bosch and Nokia.

The manufacturing domain is a good fit for RAG because:
- Documentation is dense, technical, and highly specific
- Errors have real safety and cost consequences (hallucinations are unacceptable)
- Operators need fast, cited answers — not general web results
