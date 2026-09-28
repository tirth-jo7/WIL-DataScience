# Student Wellbeing RAG

This package implements the Python RAG service called by the existing Telegram bot.
It keeps the current `POST /query` contract while replacing the hard-coded prototype
with a test-driven, source-grounded pipeline.

## Architecture

1. Deterministic safety pre-check.
2. BM25 retrieval over a curated, verified wellbeing knowledge base.
3. Ollama prompt construction using only the top retrieved sources.
4. JSON-schema-constrained LLM generation.
5. Post-generation guardrails for clinical advice, fabricated citations and URLs.
6. Existing `RagResponse` returned to the Telegram client.

The retrieval baseline follows the key Walert idea of evaluating ranking separately from
answer generation. The test collection contains **known**, **inferred** and **out-of-KB**
queries and reports Hit@k, MRR and NDCG.

## Local setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -r rag/requirements-dev.txt
```

Install Ollama separately, then pull any chat model you want to use. The default is:

```bash
ollama pull llama3.2:3b
```

You can override it:

```bash
export OLLAMA_MODEL=<installed-model-name>
export OLLAMA_HOST=http://localhost:11434
```

Run the API:

```bash
uvicorn rag.main:app --reload --port 8000
```

The existing TypeScript bot already calls `http://localhost:8000/query`.

## Tests

```bash
pytest rag/tests -q
```

The automated suite covers four project evaluation axes:

- **Effectiveness:** retrieval Hit@k, MRR and NDCG.
- **Safety:** deterministic crisis routing, clinical-scope blocking and injection resistance.
- **Source attribution:** generated source IDs must be a subset of actually retrieved IDs.
- **Faithfulness:** the system fails closed on fabricated citations/URLs; `evaluation/faithfulness.py`
  provides an optional Ollama-based grounding judge for experiment runs (use alongside human review).

Run the retrieval benchmark directly:

```bash
python -m rag.evaluation.run
```

## Safety design

- Crisis routing happens before retrieval or LLM generation.
- Crisis contact details come from a fixed, verified RMIT source rather than model memory.
- Clinical diagnosis, treatment and medication requests are out of scope.
- The LLM may cite only source IDs that were actually retrieved.
- Any fabricated source ID or URL causes the answer to fail closed as `unsupported`.
- Retrieved content is explicitly treated as untrusted data to reduce prompt-injection risk.
- Full student wellbeing messages are not logged by the Python service.

## Knowledge-base maintenance

`rag/data/services.json` contains paraphrased service descriptions with official RMIT URLs
and a `last_verified` date. Because support details can change, re-check these sources before
production deployment and update both the content and verification date.
