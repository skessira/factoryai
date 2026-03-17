"""
FactoryAI — Query Pipeline
--------------------------
Receives a question string, retrieves the most relevant chunks from the vector
store, assembles a grounded prompt, calls the LLM, and returns a structured
response dict matching the AskResponse schema in main.py.

Called by main.py — do not run directly.
See spec_query.md for full design rationale.
"""

import json
import os
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Configuration — tune without touching pipeline logic
# ---------------------------------------------------------------------------
VECTOR_STORE    = "vector_store.json"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # must match the model used in ingest.py
TOP_K           = 3                     # number of chunks to retrieve per query
LLM_MODEL       = "gpt-4o-mini"

# Load OPENAI_API_KEY from .env file
load_dotenv()


# ---------------------------------------------------------------------------
# Module-level singletons
# These are loaded once at startup, not on every request.
# Loading the embedding model or vector store on every API call would be slow.
# ---------------------------------------------------------------------------
_embedding_model: SentenceTransformer | None = None
_vector_store: dict | None = None
_openai_client: OpenAI | None = None


def _get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    return _embedding_model


def _get_vector_store() -> dict:
    global _vector_store
    if _vector_store is None:
        if not Path(VECTOR_STORE).exists():
            raise FileNotFoundError(
                f"Vector store not found at '{VECTOR_STORE}'. "
                "Run ingest.py first to build the knowledge base."
            )
        with open(VECTOR_STORE, "r", encoding="utf-8") as f:
            _vector_store = json.load(f)
    return _vector_store


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not found. "
                "Create a .env file with: OPENAI_API_KEY=sk-..."
            )
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


# ---------------------------------------------------------------------------
# Step 1: Embed the question
# Uses the same model as ingestion — critical for vector space compatibility.
# A different model would produce incomparable vectors.
# ---------------------------------------------------------------------------
def embed_question(question: str) -> list[float]:
    """Convert the question string to a 384-dimensional embedding vector."""
    model = _get_embedding_model()
    return model.encode(question).tolist()


# ---------------------------------------------------------------------------
# Step 2: Similarity search — retrieve top-K chunks
# ---------------------------------------------------------------------------
def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Cosine similarity between two vectors.
    Returns 1.0 (identical) → 0.0 (unrelated) → -1.0 (opposite).
    Same calculation used in ingest.py and by ChromaDB/pgvector internally.
    """
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def retrieve(question_embedding: list[float], top_k: int = TOP_K) -> list[dict]:
    """
    Score every chunk in the vector store against the question embedding.
    Returns the top-K chunks sorted by similarity score (highest first).

    Each returned chunk dict contains: id, text, metadata, score.
    """
    store = _get_vector_store()
    scored = []

    for chunk in store["chunks"]:
        score = cosine_similarity(question_embedding, chunk["embedding"])
        scored.append({
            "id":       chunk["id"],
            "text":     chunk["text"],
            "metadata": chunk["metadata"],
            "score":    score,
        })

    # Sort descending, take top K
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


# ---------------------------------------------------------------------------
# Step 3: Build the prompt
# Three-part structure: system role/rules + injected context + user question.
# ---------------------------------------------------------------------------
def build_messages(question: str, chunks: list[dict]) -> list[dict]:
    """
    Assemble the messages list for the OpenAI chat API.

    The grounding rule is the most important constraint: the LLM must answer
    ONLY from the provided context. Without it, the model fills knowledge gaps
    with training data — which for equipment specs may be dangerously wrong.
    """
    system_prompt = (
        "You are FactoryAI, a knowledge assistant for factory floor operators "
        "and maintenance engineers.\n\n"
        "Your purpose is to help workers find accurate, reliable information "
        "from equipment documentation quickly and safely.\n\n"
        "Rules:\n"
        "- Answer ONLY using the context provided below. "
        "Do not use any outside knowledge.\n"
        "- If the context does not contain enough information to answer the "
        "question, say so clearly. Do not guess or invent information.\n"
        "- Be concise and precise. Factory workers need fast, reliable answers.\n"
        "- Do not add information that is not explicitly stated in the context."
    )

    # Inject retrieved chunks — each labelled with source and page for traceability
    context_block = "\n---\n".join(
        f"[Source: {c['metadata']['source']}, Page {c['metadata']['page_number']}]\n{c['text']}"
        for c in chunks
    )

    user_message = (
        f"Context:\n{context_block}\n\n"
        f"Question: {question}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]


# ---------------------------------------------------------------------------
# Step 4: Call the LLM
# ---------------------------------------------------------------------------
def call_llm(messages: list[dict]) -> str:
    """
    Send the assembled prompt to gpt-4o-mini and return the answer string.
    temperature=0 for deterministic output — factual Q&A, not creative tasks.
    """
    client = _get_openai_client()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0,
    )
    return response.choices[0].message.content


# ---------------------------------------------------------------------------
# Step 5: Assemble the response
# ---------------------------------------------------------------------------
def build_response(answer: str, chunks: list[dict]) -> dict:
    """
    Construct the response dict matching AskResponse in main.py.

    Citations are built from retrieval metadata — NOT parsed from LLM output.
    This makes citations deterministic and accurate. LLM-generated citations
    hallucinate source names and page numbers.
    """
    citations = [
        {
            "source":      c["metadata"]["source"],
            "link":        None,
            "page_number": c["metadata"]["page_number"],
        }
        for c in chunks
    ]

    return {
        "answer":          answer,
        "citations":       citations,
        "related_sources": [],
    }


# ---------------------------------------------------------------------------
# Public entry point — called by main.py
# ---------------------------------------------------------------------------
def run(question: str) -> dict:
    """
    Execute the full query pipeline for a given question.

    Steps:
        1. Embed question → 384-dim vector
        2. Retrieve top-K most similar chunks from vector store
        3. Build grounded prompt (system + context + question)
        4. Call gpt-4o-mini
        5. Assemble and return AskResponse-compatible dict
    """
    question_embedding = embed_question(question)
    chunks             = retrieve(question_embedding)
    messages           = build_messages(question, chunks)
    answer             = call_llm(messages)
    return build_response(answer, chunks)
