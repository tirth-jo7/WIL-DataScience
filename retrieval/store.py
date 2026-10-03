from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("RAG_DATA_DIR", str(REPO_ROOT / "data")))
STORE_PATH = Path(
    os.getenv("RAG_VECTOR_STORE_PATH", str(REPO_ROOT / "retrieval" / "vector_store.json"))
)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "nomic-embed-text")
TIMEOUT_SECONDS = float(os.getenv("RAG_EMBED_TIMEOUT_SECONDS", "120"))

_META_RE = re.compile(r"^([A-Za-z_ -]+):\s*(.+)$")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def _read_document(path: Path) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8").strip()
    lines = raw.splitlines()

    metadata: dict[str, str] = {}
    body_start = 0

    # Parse simple metadata lines at the top of the Markdown file.
    # Example:
    # Title: RMIT Counselling and Psychological Services
    # Source: https://...
    # Verified: 2026-10-04
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            body_start = i + 1
            break

        match = _META_RE.match(stripped)
        if not match:
            body_start = i
            break

        key = match.group(1).strip().lower().replace(" ", "_").replace("-", "_")
        metadata[key] = match.group(2).strip()
        body_start = i + 1

    body = "\n".join(lines[body_start:]).strip()

    topic = path.relative_to(DATA_DIR).parts[0] if len(path.relative_to(DATA_DIR).parts) > 1 else "general"

    title = metadata.get("title") or path.stem.replace("_", " ").replace("-", " ").title()
    source = metadata.get("source") or ""
    verified = metadata.get("verified") or metadata.get("last_verified") or ""

    return {
        "title": title,
        "source": source,
        "verified": verified,
        "topic": topic,
        "body": body,
        "path": path.relative_to(REPO_ROOT).as_posix(),
    }


def _split_chunks(body: str, max_chars: int = 1100) -> list[str]:
    """Chunk Markdown by paragraph while keeping chunks compact and readable."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current = ""

    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        # Split very long paragraphs/single sections without adding dependencies.
        while len(paragraph) > max_chars:
            cut = paragraph.rfind(" ", 0, max_chars)
            if cut < max_chars // 2:
                cut = max_chars
            chunks.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()

        current = paragraph

    if current:
        chunks.append(current)

    return chunks


def _embed(inputs: list[str]) -> list[list[float]]:
    if not inputs:
        return []

    payload = {
        "model": EMBED_MODEL,
        "input": inputs,
    }

    try:
        response = httpx.post(
            f"{OLLAMA_HOST}/api/embed",
            json=payload,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Could not get embeddings from Ollama at {OLLAMA_HOST}. "
            f"Make sure Ollama is running and '{EMBED_MODEL}' is installed."
        ) from exc

    data = response.json()
    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(inputs):
        raise RuntimeError("Ollama returned an unexpected embedding response")

    return embeddings


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build() -> dict[str, Any]:
    files = sorted(DATA_DIR.rglob("*.md"))
    if not files:
        raise RuntimeError(f"No Markdown knowledge-base files found under {DATA_DIR}")

    rows: list[dict[str, Any]] = []
    embed_texts: list[str] = []

    for path in files:
        doc = _read_document(path)
        chunks = _split_chunks(doc["body"])

        for idx, chunk in enumerate(chunks):
            # Put metadata into the text itself as well. This lets downstream
            # adapters recover source URL/title/date without a custom schema.
            retrieval_text = "\n".join(
                part for part in [
                    f"TITLE: {doc['title']}",
                    f"SOURCE: {doc['source']}" if doc["source"] else "",
                    f"VERIFIED: {doc['verified']}" if doc["verified"] else "",
                    f"TOPIC: {doc['topic']}",
                    "",
                    chunk,
                ] if part != ""
            )

            rows.append(
                {
                    "id": f"{doc['path']}#chunk-{idx}",
                    "text": retrieval_text,
                    "source": doc["path"],
                    "topic": doc["topic"],
                    "title": doc["title"],
                    "url": doc["source"],
                    "verified": doc["verified"],
                }
            )
            # Prefixes make the intent explicit for retrieval embeddings.
            embed_texts.append(f"search_document: {retrieval_text}")

    embeddings = _embed(embed_texts)
    for row, embedding in zip(rows, embeddings):
        row["embedding"] = embedding

    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(
        json.dumps(
            {
                "version": 1,
                "embedding_model": EMBED_MODEL,
                "data_dir": str(DATA_DIR),
                "chunks": rows,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return {
        "documents": len(files),
        "chunks": len(rows),
        "store": str(STORE_PATH),
        "embedding_model": EMBED_MODEL,
    }


def _load_store() -> dict[str, Any]:
    if not STORE_PATH.exists():
        raise RuntimeError(
            f"Vector store not found at {STORE_PATH}. "
            "Build it first with: python retrieval/store.py build"
        )

    return json.loads(STORE_PATH.read_text(encoding="utf-8"))


def retrieve(
    query: str,
    top_k: int = 4,
    topic: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve relevant KB chunks.

    Public interface intentionally matches the agreed Role 3 contract:
        retrieve(query, top_k=4, topic=None)

    Returns dictionaries containing at least:
        text, source, topic
    """
    query = query.strip()
    if not query:
        return []

    store = _load_store()
    chunks = store.get("chunks", [])

    if topic:
        wanted = topic.strip().lower()
        chunks = [
            chunk
            for chunk in chunks
            if str(chunk.get("topic", "")).lower() == wanted
        ]

    if not chunks:
        return []

    query_embedding = _embed([f"search_query: {query}"])[0]

    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunks:
        score = _cosine(query_embedding, chunk["embedding"])
        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)

    results: list[dict[str, Any]] = []
    for score, chunk in scored[: max(1, top_k)]:
        results.append(
            {
                "text": chunk["text"],
                "source": chunk["source"],
                "topic": chunk["topic"],
                "title": chunk.get("title"),
                "url": chunk.get("url"),
                "verified": chunk.get("verified"),
                "score": score,
            }
        )

    return results


def _main() -> None:
    parser = argparse.ArgumentParser(description="Build or query the local student-support vector store.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("build", help="Embed data/**/*.md and build the local vector store")

    query_parser = subparsers.add_parser("query", help="Run a retrieval query")
    query_parser.add_argument("text")
    query_parser.add_argument("--top-k", type=int, default=4)
    query_parser.add_argument("--topic", default=None)

    args = parser.parse_args()

    if args.command == "build":
        print(json.dumps(build(), indent=2))
        return

    results = retrieve(args.text, top_k=args.top_k, topic=args.topic)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()
