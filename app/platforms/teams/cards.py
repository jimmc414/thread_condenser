from typing import List

from app.schemas import CondenseResult


def _section(title: str, items: List[dict]) -> dict:
    facts = []
    for item in items:
        summary = (
            item.get("summary")
            or item.get("task")
            or item.get("statement")
            or item.get("question")
        )
        owner = item.get("owner") or "Unassigned"
        due = item.get("due_date") or "-"
        confidence = int(round(item.get("confidence", 0.0) * 100))
        facts.append(
            {
                "title": summary,
                "value": f"Owner: {owner}  Due: {due}  Confidence: {confidence}%",
            }
        )
    return {
        "type": "FactSet",
        "title": title,
        "facts": facts,
    }


def build_adaptive_card(brief: CondenseResult) -> dict:
    body = [
        {
            "type": "TextBlock",
            "text": "Thread Condenser",
            "weight": "bolder",
            "size": "medium",
        }
    ]
    sections = [
        ("Decisions", brief.decisions),
        ("Risks", brief.risks),
        ("Actions", brief.actions),
        ("Open questions", brief.open_questions),
    ]
    for title, items in sections:
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
        body.append(_section(title, [i.model_dump(mode="json") for i in items]))

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }
