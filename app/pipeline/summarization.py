from app.config import settings
from app.llm.router import get_llm


async def summarize_segments(segments: list[str]) -> list[str]:
    llm = get_llm()
    system = open("app/prompts/summarization.md", "r", encoding="utf-8").read()
    outs: list[str] = []
    for segment in segments:
        text = await llm.complete_text(
            system=system,
            user=segment,
            model=settings.OPENAI_MODEL,
            temperature=0.2,
            max_tokens=400,
        )
        outs.append(text)
    return outs
