from __future__ import annotations

import math


def hit_at_k(ranked_ids: list[str], relevant: dict[str, int], k: int) -> float:
    return float(any(relevant.get(doc_id, 0) > 0 for doc_id in ranked_ids[:k]))


def reciprocal_rank(ranked_ids: list[str], relevant: dict[str, int]) -> float:
    for rank, doc_id in enumerate(ranked_ids, start=1):
        if relevant.get(doc_id, 0) > 0:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked_ids: list[str], relevant: dict[str, int], k: int) -> float:
    def dcg(grades: list[int]) -> float:
        return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades))

    observed = [relevant.get(doc_id, 0) for doc_id in ranked_ids[:k]]
    ideal = sorted(relevant.values(), reverse=True)[:k]
    ideal_score = dcg(ideal)
    if ideal_score == 0:
        return 1.0 if not any(observed) else 0.0
    return dcg(observed) / ideal_score
