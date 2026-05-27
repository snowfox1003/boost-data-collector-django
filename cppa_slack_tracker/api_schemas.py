"""Pydantic models for Slack Web API payloads at ingestion boundaries."""

from __future__ import annotations

from typing import Any, NoReturn

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)


class SlackApiValidationError(ValueError):
    """Slack API payload failed Pydantic validation."""


class SlackProfilePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    email: str | None = None
    image_72: str | None = None
    display_name: str | None = None


class SlackTopicPurpose(BaseModel):
    model_config = ConfigDict(extra="allow")

    value: str = ""


class SlackUserPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    name: str = ""
    real_name: str = ""
    profile: SlackProfilePayload = Field(default_factory=SlackProfilePayload)
    updated: int | None = None
    is_bot: bool = False


class SlackTeamPayload(BaseModel):
    """Internal shape: team_id + team_name (from API id + name)."""

    model_config = ConfigDict(extra="allow")

    team_id: str = Field(min_length=1)
    team_name: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_api_team(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "team_id" in data:
            return data
        tid = data.get("id") or data.get("team_id") or ""
        tname = (data.get("name") or data.get("team_name") or tid or "").strip()
        return {"team_id": str(tid), "team_name": tname or str(tid)}


class SlackChannelPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1)
    name: str = ""
    is_channel: bool = False
    is_private: bool = False
    is_im: bool = False
    is_mpim: bool = False
    purpose: SlackTopicPurpose | dict[str, Any] | None = None
    topic: SlackTopicPurpose | dict[str, Any] | None = None
    creator: str | None = None
    created: int | None = None
    type: str = "public_channel"


class SlackMessageEdited(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str | None = None


class SlackMessagePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str | None = None
    user: str | None = None
    text: str = ""
    subtype: str | None = None
    edited: SlackMessageEdited | dict[str, Any] | None = None
    comment: dict[str, Any] | None = None
    thread_ts: str | None = None


def _validation_error(prefix: str, err: ValidationError) -> NoReturn:
    detail = err.errors()[:5]
    msg = f"{prefix}: " + "; ".join(
        f"{e.get('loc', ())}: {e.get('msg', '')}" for e in detail
    )
    if len(err.errors()) > 5:
        msg += f" … ({len(err.errors())} errors total)"
    raise SlackApiValidationError(msg) from err


def _expect_dict(data: Any, prefix: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SlackApiValidationError(
            f"{prefix}: expected object, got {type(data).__name__}"
        )
    return data


def parse_team(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> SlackTeamPayload:
    prefix = f"Invalid Slack team{f' ({source})' if source else ''}"
    data = _expect_dict(data, prefix)
    try:
        return SlackTeamPayload.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)


def parse_channel(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> SlackChannelPayload:
    prefix = f"Invalid Slack channel{f' ({source})' if source else ''}"
    data = _expect_dict(data, prefix)
    try:
        return SlackChannelPayload.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)


def parse_message(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> SlackMessagePayload:
    prefix = f"Invalid Slack message{f' ({source})' if source else ''}"
    data = _expect_dict(data, prefix)
    try:
        return SlackMessagePayload.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)


def parse_user(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> SlackUserPayload:
    prefix = f"Invalid Slack user{f' ({source})' if source else ''}"
    data = _expect_dict(data, prefix)
    try:
        return SlackUserPayload.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)
