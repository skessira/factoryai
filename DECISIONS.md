# FactoryAI — Architecture Decision Log

This file documents key design decisions, the reasoning behind them, and where AI tools assisted vs. where domain/architectural judgment drove the choice.

---

## Decision 1: URL versioning (`/api/v1/`)

**What:** All routes prefixed with `/api/v1/`.

**Why:** When v2 introduces AI-powered responses, the endpoint contract will change (latency, response structure may evolve). URL versioning allows v1 to remain functional while v2 is introduced. Clients — whether a chat UI or an external MES/ERP system — explicitly opt in to the upgrade by changing their endpoint. This is the standard approach for enterprise APIs where breaking changes are costly.

**Alternatives rejected:** Header versioning (`Accept: application/vnd.api+json;version=2`) — more flexible but harder to test in Swagger UI and less obvious to consumers. For a demo context, URL versioning wins on clarity.

**AI vs. judgment:** Architectural judgment. URL versioning is a well-known pattern; the decision to apply it here from day one (rather than retrofitting later) was driven by thinking about the MES/ERP integration scenario.

---

## Decision 2: Pydantic models defined at module level, not inline

**What:** `AskRequest`, `AskResponse`, `Citation`, and `RelatedSource` are defined as top-level classes, not inline in the route function.

**Why:** Prepares for extraction to a `models.py` file in v2 when the codebase grows. Also makes the schema immediately visible in Swagger UI documentation, improving demo clarity.

**AI vs. judgment:** FastAPI convention; Claude confirmed this is the standard pattern.

---

## Decision 3: `session_id` included in request schema (unused in v1)

**What:** `AskRequest` includes an optional `session_id: Optional[str]` field.

**Why:** Multi-turn conversation tracking will be needed in v2 when the chatbot needs context from previous questions in a session. Adding the field now means clients that send a `session_id` in v1 won't need to change when v2 uses it. Non-breaking forward compatibility.

**AI vs. judgment:** Sammy's design call during spec phase — driven by thinking about real usage patterns in a factory floor context where a technician might ask follow-up questions.

---

## Decision 4: `citations` and `related_sources` in response (even in hardcoded v1)

**What:** The response schema includes `citations` (direct sources for the answer) and `related_sources` (adjacent relevant documents), both populated with mock data in v1.

**Why:** In a manufacturing context, an answer without a source is untrustworthy. A maintenance engineer needs to know *which manual, which page*. Designing this into the contract from v1 ensures the UI and any downstream consumers are built to display citations. It also directly maps to what pgvector returns in v2: similarity search results become citations, next-closest chunks become related sources.

**AI vs. judgment:** Schema design was Sammy's — driven by manufacturing domain knowledge. Claude helped confirm the mapping to RAG architecture.

---

## Decision 6: ChromaDB → numpy-based vector store (local dev)

**What:** Replaced ChromaDB with a custom JSON + numpy vector store for local development.

**Why:** ChromaDB depends on `chroma-hnswlib`, which requires Microsoft C++ Build Tools to compile from source on Windows. This adds a multi-GB toolchain installation as a setup prerequisite — inappropriate friction for a learning/demo environment. The numpy approach uses only packages already present as sentence-transformers dependencies.

**Trade-off:** The numpy store uses brute-force cosine similarity (O(n) scan over all chunks). This is fine for hundreds of chunks but would not scale to millions. ChromaDB and pgvector both use HNSW indexing for sub-linear search time at scale. The pipeline logic (chunk → embed → store) is identical either way — swapping the store is a contained change.

**Production path:** pgvector on PostgreSQL. The query and ingestion logic remains unchanged; only the storage and retrieval calls are replaced.

**AI vs. judgment:** Root cause diagnosis was collaborative. Decision to use numpy rather than install build tools was architectural judgment — keeping environment complexity low during the learning phase.

---

## Decision 7: `python -m pip` over `pip` on Windows

**What:** Use `python -m pip install` instead of bare `pip install` when installing into a venv on Windows.

**Why:** On Windows with multiple Python installations and venvs, the `pip` executable can resolve to a different Python environment than the active venv. `python -m pip` explicitly uses the pip belonging to whichever `python` is currently active — eliminating ambiguity. Bare `pip` is fine on clean single-Python setups but unreliable otherwise.

**AI vs. judgment:** Discovered through debugging — pip was installing to an iCloud-synced venv while python was running from a local venv. Lesson: always verify with `python -c "import sys; print(sys.executable)"` when packages are not found after install.

---

## Decision 5: `/health` endpoint

**What:** A `GET /health` endpoint returning `{"status": "ok", "version": "1.0.0"}`.

**Why:** Standard liveness probe pattern for containerised services. When FactoryAI is Dockerised in Week 4, orchestration tools (Docker Compose, Kubernetes) use this to verify the service is running. Adding it now costs nothing and avoids retrofitting.

**AI vs. judgment:** Claude suggested adding this as enterprise-grade practice. Accepted — consistent with production patterns from Microsoft/Azure deployments.
