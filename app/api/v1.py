from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models import Brief

router = APIRouter(prefix="/v1")


class CondenseRequest(BaseModel):
    platform: str
    thread_ref: dict
    options: dict | None = None


class GraphNotification(BaseModel):
    value: list[dict] = []
    validationToken: str | None = None


@router.post("/condense")
def condense(req: CondenseRequest, db: Session = Depends(get_db)):
    from app.workers.tasks import enqueue_condense_external

    run_id = enqueue_condense_external(req.platform, req.thread_ref, req.options or {})
    return {"run_id": run_id}


@router.get("/briefs/{run_id}")
def get_brief(run_id: str, db: Session = Depends(get_db)):
    brief = db.query(Brief).filter(Brief.run_id == run_id).first()
    if not brief:
        raise HTTPException(404)
    return brief.json_blob


class EditRequest(BaseModel):
    patch: dict


@router.post("/items/{item_id}/edit")
def edit_item(item_id: str, req: EditRequest, db: Session = Depends(get_db)):
    from app.workers.tasks import edit_item_sync

    return edit_item_sync(item_id, req.patch, db)


@router.get("/graph/notifications")
def graph_validation(validationToken: str):
    return Response(content=validationToken, media_type="text/plain")


@router.post("/graph/notifications")
def graph_notifications(payload: GraphNotification):
    from app.workers.tasks import trigger_condense

    if payload.validationToken:
        return Response(content=payload.validationToken, media_type="text/plain")
    for notification in payload.value:
        resource = notification.get("resource", "")
        resource_data = notification.get("resourceData", {})
        if "/messages" not in resource:
            continue
        if "/chats/" in resource or "/teams/" in resource:
            platform = "msteams"
        else:
            platform = "outlook"
        thread_ref = {**resource_data, "resource": resource}
        trigger_condense(platform, thread_ref, None)
    return {"status": "accepted"}
