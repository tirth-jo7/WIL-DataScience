from __future__ import annotations

import json
from pathlib import Path

from rag.config import KNOWLEDGE_BASE_PATH
from rag.evaluation.metrics import hit_at_k, ndcg_at_k, reciprocal_rank
from rag.retrieval import BM25Retriever


CASES = json.loads(
    (Path(__file__).parents[1] / "evaluation" / "queries.json").read_text(encoding="utf-8")
)


def test_retrieval_quality_baseline() -> None:
    retriever = BM25Retriever.from_json(KNOWLEDGE_BASE_PATH)
    answerable = [case for case in CASES if case["type"] != "out_of_kb"]

    hit1 = []
    hit3 = []
    mrr = []
    ndcg3 = []

    for case in answerable:
        ranked = [item.id for item in retriever.retrieve(case["query"], top_k=5)]
        hit1.append(hit_at_k(ranked, case["relevance"], 1))
        hit3.append(hit_at_k(ranked, case["relevance"], 3))
        mrr.append(reciprocal_rank(ranked, case["relevance"]))
        ndcg3.append(ndcg_at_k(ranked, case["relevance"], 3))

    assert sum(hit1) / len(hit1) >= 0.80
    assert sum(hit3) / len(hit3) >= 0.95
    assert sum(mrr) / len(mrr) >= 0.85
    assert sum(ndcg3) / len(ndcg3) >= 0.80


def test_out_of_kb_queries_do_not_cross_answer_threshold() -> None:
    retriever = BM25Retriever.from_json(KNOWLEDGE_BASE_PATH)
    out_cases = [case for case in CASES if case["type"] == "out_of_kb"]

    for case in out_cases:
        results = retriever.retrieve(case["query"], top_k=1)
        assert not results or results[0].score < 0.18, case["id"]
