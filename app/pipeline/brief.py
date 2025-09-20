from sqlalchemy.orm import Session

from app.models import Brief
from app.schemas import CondenseResult


def save_brief(
    db: Session,
    run_id: str,
    thread_id,
    brief: CondenseResult,
    model_version: str = "v1.0",
    api_version: str = "v1",
):
    payload = brief.model_dump(mode="json")
    record = Brief(
        run_id=run_id,
        thread_id=thread_id,
        platform=brief.platform,
        version="1",
        model_version=model_version,
        api_version=api_version,
        json_blob=payload,
    )
    db.merge(record)
    db.commit()
    return record
