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

## Decision 8: LLM choice — gpt-4o-mini

**What:** Used OpenAI's `gpt-4o-mini` as the generation model.

**Why:** Fast, cheap, and more than capable for retrieval-augmented tasks. In RAG, the LLM's job is relatively constrained — it synthesises provided context into prose, it doesn't need to reason from scratch. gpt-4o-mini handles this well at a fraction of the cost of GPT-4o. For dev usage, the cost is negligible (hundreds of requests per dollar).

**Alternatives rejected:** Ollama (local Llama 3 / Mistral) — no API cost and privacy-preserving, but slower on CPU and more complex setup for this stage. Valid for production in privacy-sensitive factory environments. OpenAI GPT-4o — higher quality but ~10x the cost with no meaningful improvement for grounded Q&A tasks.

**AI vs. judgment:** Architectural judgment on model tier. Cost/capability analysis was done collaboratively.

---

## Decision 9: `temperature=0` for LLM calls

**What:** Set `temperature=0` in the OpenAI API call.

**Why:** Temperature controls output randomness. At 0, the model is deterministic — same input always produces the same output. For factual Q&A on equipment documentation, consistency and accuracy matter more than variety. A maintenance engineer asking the same question twice should get the same answer.

**Trade-off:** Determinism means less "creative" phrasing, but that's a feature not a bug here. Higher temperature would be appropriate for tasks like generating maintenance report summaries or operator communications.

**AI vs. judgment:** Claude suggested this as standard practice for factual RAG. Accepted — consistent with production patterns.

---

## Decision 10: Module-level singletons for expensive resources

**What:** The embedding model, vector store, and OpenAI client are each loaded once at module level using a lazy-init pattern (`_get_X()` functions with global cache).

**Why:** Loading the embedding model (all-MiniLM-L6-v2) takes 1-2 seconds. Reading the vector store from disk is an I/O operation. Doing either on every API request would make response times unacceptable. Loading once at startup and reusing across requests is the correct pattern for stateless resources.

**AI vs. judgment:** Claude generated the pattern. The reasoning (why lazy init matters for API performance) was covered in the code walkthrough — understood and validated.

---

## Decision 11: Citations sourced from retrieval metadata, not LLM output

**What:** Citations in the API response are built directly from the metadata of the top-K retrieved chunks, not parsed or generated from the LLM's text output.

**Why:** LLMs hallucinate citation details — source names, page numbers, section titles. If you ask the model to produce its own citations, it will invent plausible-sounding but wrong references. Since we already have accurate metadata attached to every retrieved chunk (source filename, page number), we use that directly. The LLM's job is only to generate the answer prose.

**Impact:** Citations are always accurate and deterministic. This is a critical correctness property for a manufacturing context where a wrong manual reference could mean wrong maintenance procedure.

**AI vs. judgment:** Sammy identified this principle during the Socratic walkthrough before any code was written. Core RAG design judgment.

---

## Decision 12: Top-K = 3 chunks

**What:** The retrieval step returns the 3 most similar chunks to pass to the LLM.

**Why:** Enough context for most single-topic questions without flooding the LLM context window with noise. More chunks increase token cost and can dilute the signal — the LLM may weight a weaker chunk and produce a less focused answer. 3 is a reasonable starting point; tunable as the knowledge base grows.

**Known limitation:** All 3 chunks can come from the same page if relevant content is concentrated there, producing duplicate citations. Future improvement: deduplicate citations by (source, page_number) before returning the response.

**AI vs. judgment:** Value chosen collaboratively. The deduplication gap was identified by Sammy reviewing the first live response.

---

## Decision 13: Separate `query.py` module

**What:** All query pipeline logic lives in `query.py`. `main.py` only handles routing, Pydantic validation, and error mapping.

**Why:** Separation of concerns. `main.py` is the HTTP boundary layer — it should know nothing about embeddings or LLMs. `query.py` is the intelligence layer — it should know nothing about HTTP. This makes each independently testable and means the pipeline logic can be reused outside a web context (e.g., a CLI tool or a batch processing script).

**AI vs. judgment:** Claude proposed the separation. Accepted as clean architecture practice consistent with production patterns.

---

## Decision 14: Version control from day one, not after "v1 complete"

**What:** Git + GitHub initialized at the start of the query pipeline session, not deferred until a "finished" version existed.

**Why:** Commit history is the portfolio artifact, not just the final code. A repo showing incremental commits (skeleton → ingestion → query pipeline) demonstrates architectural thinking and iterative development. A single "initial commit" of finished code looks like it was dumped in, regardless of quality. The two historical commits (v1 skeleton, ingestion pipeline) reconstruct the project's real development arc.

**AI vs. judgment:** Sammy raised the question. The reasoning about portfolio signal vs. code quality was the deciding factor.

---

## Decision 5: `/health` endpoint

**What:** A `GET /health` endpoint returning `{"status": "ok", "version": "1.0.0"}`.

**Why:** Standard liveness probe pattern for containerised services. When FactoryAI is Dockerised in Week 4, orchestration tools (Docker Compose, Kubernetes) use this to verify the service is running. Adding it now costs nothing and avoids retrofitting.

**AI vs. judgment:** Claude suggested adding this as enterprise-grade practice. Accepted — consistent with production patterns from Microsoft/Azure deployments.
