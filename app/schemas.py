from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class SupportRef(BaseModel):
    platform: str
    native_id: str
    msg_id: str
    quote: str
    url: Optional[str] = None


class PersonRef(BaseModel):
    display_name: str
    platform: str
    native_id: Optional[str] = None
    email: Optional[str] = None


class Provenance(BaseModel):
    thread_url: str
    message_ids: List[str]
    model_version: Optional[str] = None
    run_id: Optional[str] = None
    source_platform: str | None = None
    source_thread_ref: Dict[str, str]


class Decision(BaseModel):
    title: str
    summary: str
    owner: Optional[str] = None
    due_date: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    supporting_msgs: List[SupportRef]


class Risk(BaseModel):
    statement: str
    likelihood: str
    impact: str
    owner: Optional[str] = None
    mitigation: Optional[str] = None
    confidence: float
    supporting_msgs: List[SupportRef]


class ActionItem(BaseModel):
    task: str
    owner: Optional[str] = None
    due_date: Optional[str] = None
    status: str = "proposed"
    confidence: float
    supporting_msgs: List[SupportRef]


class OpenQuestion(BaseModel):
    question: str
    who_should_answer: Optional[str] = None
    confidence: float
    supporting_msgs: List[SupportRef]


class CondenseResult(BaseModel):
    platform: str
    decisions: List[Decision]
    risks: List[Risk]
    actions: List[ActionItem]
    open_questions: List[OpenQuestion]
    people_map: Dict[str, PersonRef]
    provenance: Provenance
    changelog: List[dict] = []
