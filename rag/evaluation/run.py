from __future__ import annotations

import json
from pathlib import Path

from rag.config import KNOWLEDGE_BASE_PATH
from rag.evaluation.metrics import hit_at_k, ndcg_at_k, reciprocal_rank
from rag.retrieval import BM25Retriever


def main() -> None:
    cases_path = Path(__file__).with_name("queries.json")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    retriever = BM25Retriever.from_json(KNOWLEDGE_BASE_PATH)

    answerable = [case for case in cases if case["type"] != "out_of_kb"]
    out_of_kb = [case for case in cases if case["type"] == "out_of_kb"]

    rows = []
    for case in answerable:
        results = retriever.retrieve(case["query"], top_k=5)
        ranked = [result.id for result in results]
        rows.append(
            {
                "id": case["id"],
                "hit@1": hit_at_k(ranked, case["relevance"], 1),
                "hit@3": hit_at_k(ranked, case["relevance"], 3),
                "hit@5": hit_at_k(ranked, case["relevance"], 5),
                "mrr": reciprocal_rank(ranked, case["relevance"]),
                "ndcg@3": ndcg_at_k(ranked, case["relevance"], 3),
            }
        )

    summary = {
        metric: round(sum(row[metric] for row in rows) / len(rows), 4)
        for metric in ("hit@1", "hit@3", "hit@5", "mrr", "ndcg@3")
    }
    false_retrievals = 0
    for case in out_of_kb:
        results = retriever.retrieve(case["query"], top_k=1)
        if results and results[0].score >= 0.18:
            false_retrievals += 1
    summary["out_of_kb_false_retrieval_rate"] = round(
        false_retrievals / max(len(out_of_kb), 1), 4
    )

    print(json.dumps({"summary": summary, "cases": rows}, indent=2))


if __name__ == "__main__":
    main()
