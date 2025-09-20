def item_section(item, idx: int):
    title = (
        item.get("title")
        or item.get("task")
        or item.get("statement")
        or item.get("question")
    )
    confidence = int(round(item.get("confidence", 0.0) * 100))
    owner = item.get("owner") or "Unassigned"
    due = item.get("due_date") or "-"
    quotes = item.get("supporting_msgs", [])[:2]
    quote_lines = []
    for ref in quotes:
        line = ref.get("quote", "")
        if ref.get("url"):
            line = f"<{ref['url']}|{line}>"
        quote_lines.append(f"> {line}")
    quote_text = "\n".join(quote_lines)
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title}*\nOwner: `{owner}`  Due: `{due}`  Conf: *{confidence}%*\n{quote_text}",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Confirm"},
                    "style": "primary",
                    "action_id": "item_confirm",
                    "value": str(idx),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Edit"},
                    "action_id": "item_edit",
                    "value": str(idx),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Assign"},
                    "action_id": "item_assign",
                    "value": str(idx),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Create ticket"},
                    "action_id": "item_create_ticket",
                    "value": str(idx),
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Snooze"},
                    "action_id": "item_snooze",
                    "value": str(idx),
                },
            ],
        },
        {"type": "divider"},
    ]


def brief_card(result_json):
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Thread Condenser"},
        }
    ]
    for section in ["decisions", "risks", "actions", "open_questions"]:
        items = result_json.get(section, [])
        if not items:
            continue
        pretty = {
            "decisions": "Decisions",
            "risks": "Risks",
            "actions": "Actions",
            "open_questions": "Open questions",
        }[section]
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{pretty}*  ({len(items)})"},
            }
        )
        blocks.append({"type": "divider"})
        for idx, it in enumerate(items):
            blocks.extend(item_section(it, idx))
    return blocks
