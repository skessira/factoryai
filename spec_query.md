# FactoryAI — Query Pipeline Spec
**Version:** 1.0
**Date:** 2026-03-17
**Builds on:** spec.md (API contract), spec_ingestion.md (vector store format)

---

## What we're building

The query pipeline is the runtime half of FactoryAI. It receives a natural language
question, retrieves the most relevant chunks from the vector store, assembles a grounded
prompt, calls the LLM, and returns a structured response with citations.

This replaces the hardcoded v1 stub in `main.py` with a real RAG pipeline.
The result will be encapsulated in a new module: `query.py`.

---

## Inputs and outputs

**Input:** A question string (already validated by Pydantic in `main.py`)
```
"What is the maximum operating temperature for the conveyor belt motor?"
```

**Output:** An `AskResponse` object matching the existing Pydantic contract
```python
AskResponse(
    answer="...",           # LLM-generated prose, grounded in retrieved context
    citations=[...],        # Extracted from retrieval metadata — NOT from LLM output
    related_sources=[]      # Out of scope for this iteration
)
```

---

## Pipeline steps

```
Question (str)
    │
    ▼
1. EMBED QUESTION
   └─ Same model as ingestion: all-MiniLM-L6-v2
   └─ Returns: 384-dimensional vector

    │
    ▼
2. SIMILARITY SEARCH
   └─ Load vector_store.json
   └─ Compute cosine similarity between question vector and every chunk vector
   └─ Sort by score descending, return top K chunks (K=3)
   └─ Returns: list of dicts { id, text, metadata, score }

    │
    ▼
3. BUILD PROMPT
   └─ System message: role + grounding constraints
   └─ Context block: top-K chunk texts injected verbatim
   └─ User message: original question
   └─ Returns: messages list for OpenAI chat API

    │
    ▼
4. CALL LLM
   └─ Model: gpt-4o-mini
   └─ API key: from .env (OPENAI_API_KEY)
   └─ Returns: answer string

    │
    ▼
5. ASSEMBLE RESPONSE
   └─ answer: LLM output
   └─ citations: built from top-K chunk metadata (source + page_number)
   └─ Returns: AskResponse
```

---

## Prompt template

```
SYSTEM:
You are FactoryAI, a knowledge assistant for factory floor operators and
maintenance engineers.

Your purpose is to help workers find accurate information from equipment
documentation quickly and safely.

Rules:
- Answer ONLY using the context provided below. Do not use any outside knowledge.
- If the context does not contain enough information to answer the question,
  say so clearly. Do not guess or invent information.
- Be concise and precise. Factory workers need fast, reliable answers.
- Do not add information that is not explicitly stated in the context.

CONTEXT:
[Chunk 1 text]
---
[Chunk 2 text]
---
[Chunk 3 text]

USER:
[Question]
```

**Why this structure matters:**
The grounding rule ("Answer ONLY using the context provided") is the single most
important constraint. Without it, the LLM fills gaps with training knowledge —
which for equipment specs may be plausible but wrong and potentially dangerous.

---

## Key decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Top-K | 3 chunks | Enough context for most single-topic questions; avoids token waste and noise |
| LLM | gpt-4o-mini | Fast, cheap, sufficient quality for retrieval-augmented tasks |
| Citations source | Retrieval metadata | Deterministic and accurate — LLM-generated citations hallucinate |
| API key handling | python-dotenv + .env | Standard pattern; .env is gitignored |
| Module structure | Separate query.py | Keeps main.py as routing layer only; query logic is independently testable |

---

## What is out of scope for this iteration

- Streaming responses (would improve UX but adds complexity)
- Multi-turn conversation / session memory (`session_id` field reserved in schema)
- Reranking (a second pass to improve retrieval quality beyond cosine similarity)
- `related_sources` field (returns empty list for now)
- Confidence score thresholding (ignoring chunks below a minimum similarity score)

These are natural v3 candidates.

---

## Files changed

| File | Change |
|------|--------|
| `query.py` | New — full query pipeline implementation |
| `main.py` | Updated — `/api/v1/ask` calls `query.run()` instead of returning hardcoded stub |
| `requirements.txt` | Add: `openai`, `python-dotenv` |
| `.env` | New (gitignored) — contains `OPENAI_API_KEY` |
