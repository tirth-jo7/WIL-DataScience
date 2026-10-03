# Vector retrieval layer

This folder implements the agreed Role 3 interface:

```python
from retrieval.store import retrieve
results = retrieve(query, top_k=4, topic=None)
```

## Build

1. Make sure Ollama is running.
2. Pull the embedding model once:

```powershell
ollama pull nomic-embed-text
```

3. Build the store:

```powershell
python retrieval/store.py build
```

The generated `retrieval/vector_store.json` should normally stay out of Git because it can be rebuilt from `data/**/*.md`.

## Query manually

```powershell
python retrieval/store.py query "I'm struggling to afford rent"
python retrieval/store.py query "I need urgent support tonight" --topic crisis
```

Knowledge-base Markdown files use simple metadata:

```text
Title: Service title
Source: https://official-source.example
Verified: YYYY-MM-DD

Markdown content...
```
