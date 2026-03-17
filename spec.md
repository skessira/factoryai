# FactoryAI — v1 Skeleton Spec

## What We're Building
A FastAPI skeleton for a manufacturing knowledge chatbot. This iteration (v1) establishes the API contract, routing structure, and data models. No AI model is used — responses are hardcoded. The goal is a working, documented, extensible API foundation that can be upgraded to AI-powered responses in v2 without breaking changes.

## Requirements
- Client can send a question to `POST /api/v1/ask`
- API returns a structured JSON response containing an answer, citations, and related sources
- Interactive API documentation available at `/docs` (Swagger UI) — this serves as the client for v1
- No frontend required for this iteration

## Constraints
- Framework: FastAPI (Python)
- Single endpoint: `POST /api/v1/ask`
- Hardcoded response only — no AI, no database
- Versioned routing (`/api/v1/`) to allow non-breaking future upgrades
- Loosely coupled architecture: data models defined separately from route logic

## Architecture Decisions
- **Versioning via URL prefix**: `/api/v1/` prefix on all routes. When v2 (AI-powered) is introduced, v1 remains functional. Clients opt in to upgrades.
- **Pydantic models for request and response**: Enforces schema at the boundary. FastAPI validates incoming requests automatically and rejects malformed payloads before they reach business logic.
- **Session ID in request**: Included now (even though unused in v1) to ensure future multi-turn conversation support is a non-breaking change.

## Data Model

### Request — `AskRequest`
```json
{
  "question": "What is the maintenance interval for conveyor belt CB-04?",
  "session_id": "optional-string"
}
```

### Response — `AskResponse`
```json
{
  "answer": "string",
  "citations": [
    {
      "source": "string",
      "link": "string (optional)",
      "page_number": "integer (optional)"
    }
  ],
  "related_sources": [
    {
      "title": "string",
      "link": "string (optional)"
    }
  ]
}
```

## What v2 Will Change
- Replace the hardcoded answer with a call to an LLM (OpenAI / local model)
- Populate `citations` from pgvector similarity search results
- Populate `related_sources` from next-closest vector chunks
- Use `session_id` to maintain conversation context

## Out of Scope (v1)
- Authentication / API keys
- Database / vector store
- AI model integration
- Frontend UI
- Logging / observability (noted for v2)
