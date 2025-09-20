from app.schemas import CondenseResult


def score_item(
    item,
    reactions_index: dict[str, int],
    seniority_weight: float = 1.0,
    recency_bonus: float = 0.0,
    contradiction_penalty: float = 0.0,
) -> float:
    base = float(getattr(item, "confidence", 0.0))
    agree = sum(reactions_index.get(ref.msg_id, 0) for ref in item.supporting_msgs)
    score = (
        base
        + 0.05 * agree
        + 0.05 * seniority_weight
        + recency_bonus
        - contradiction_penalty
    )
    return max(0.0, min(1.0, score))


def rank_and_filter(
    result: CondenseResult, reactions_index: dict[str, int], threshold: float
) -> CondenseResult:
    for attr in ["decisions", "risks", "actions", "open_questions"]:
        filtered = []
        for item in getattr(result, attr):
            score = score_item(item, reactions_index)
            item.confidence = score
            if score >= threshold:
                filtered.append(item)
        filtered.sort(key=lambda it: it.confidence, reverse=True)
        setattr(result, attr, filtered)
    return result
