"""Member and team Pydantic models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Member(BaseModel):
    id: Optional[int] = None
    name: str
    email: Optional[str] = None
    personal_email: Optional[str] = None
    github: Optional[str] = None
    slack: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    team_id: Optional[int] = None
    status: str = "active"
    flags: list[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Team(BaseModel):
    id: Optional[int] = None
    name: str
    parent_id: Optional[int] = None
    lead_id: Optional[int] = None
    description: Optional[str] = None
    members: list[Member] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MeetingItem(BaseModel):
    id: Optional[int] = None
    meeting_id: Optional[int] = None
    kind: str  # action_item, decision, topic, concern, win
    content: str
    status: str = "open"
    created_at: Optional[str] = None


class Meeting(BaseModel):
    id: Optional[int] = None
    member_id: int
    date: str
    source: Optional[str] = None
    raw_text: Optional[str] = None
    summary: Optional[str] = None
    sentiment_score: Optional[float] = None
    items: list[MeetingItem] = []
    created_at: Optional[str] = None


class Goal(BaseModel):
    id: Optional[int] = None
    member_id: Optional[int] = None
    team_id: Optional[int] = None
    cycle: Optional[str] = None
    type: str  # objective, key_result, pip_criterion, career_milestone
    title: str
    description: Optional[str] = None
    target_value: Optional[float] = None
    current_value: float = 0
    status: str = "active"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PerformanceSnapshot(BaseModel):
    id: Optional[int] = None
    member_id: int
    date: str
    source: str  # github, linear, manual
    metrics: dict = {}
    score: Optional[float] = None
    created_at: Optional[str] = None


class CoachingEntry(BaseModel):
    id: Optional[int] = None
    member_id: int
    kind: str  # observation, star_assessment, conversation_plan
    content: str
    created_at: Optional[str] = None


class Schedule(BaseModel):
    id: Optional[int] = None
    name: str
    command: str
    cron_expr: str
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    enabled: bool = True
    created_at: Optional[str] = None
