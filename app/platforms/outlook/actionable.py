from app.schemas import CondenseResult


def build_actionable_card(brief: CondenseResult) -> dict:
    body = [
        {
            "type": "TextBlock",
            "text": "Thread Condenser",
            "weight": "bolder",
            "size": "medium",
        }
    ]
    for title, items in (
        ("Decisions", brief.decisions),
        ("Risks", brief.risks),
        ("Actions", brief.actions),
        ("Open questions", brief.open_questions),
    ):
        if not items:
            continue
        body.append(
            {
                "type": "TextBlock",
                "text": f"{title} ({len(items)})",
                "weight": "bolder",
                "spacing": "medium",
            }
        )
        for item in items:
            summary = (
                item.summary if hasattr(item, "summary") else getattr(item, "task", "")
            )
            owner = getattr(item, "owner", None) or "Unassigned"
            confidence = int(round(getattr(item, "confidence", 0.0) * 100))
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"{summary}\nOwner: {owner} • Confidence: {confidence}%",
                    "wrap": True,
                }
            )

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }
