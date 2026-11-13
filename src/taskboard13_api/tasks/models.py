"""Request and response models for tasks."""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field, StrictStr, field_validator

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TaskCreate(BaseModel):
    """Payload for creating a task; unknown fields are ignored."""

    title: StrictStr = Field(min_length=1, max_length=200)
    due_date: StrictStr | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title must not be blank")
        return value

    @field_validator("due_date")
    @classmethod
    def _due_date_is_calendar_date(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _DATE_RE.match(value):
            raise ValueError("due_date must be in the form YYYY-MM-DD")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("due_date must be a valid calendar date") from exc
        return value


class Task(BaseModel):
    """A stored task."""

    id: str
    title: str
    due_date: str | None
