"""Pydantic validation for Discord staging / ingestion payloads.

Runtime validation uses the models in this module only.

Reviewers who prefer raw JSON Schema may read the optional committed copy at
``discord_activity_tracker/schemas/discord_staging_v1.json`` (see generation
notes in ``docs/discord-tracker-schema.md``, section **JSON Schema artifact vs
runtime validation**). That file can drift if models change; regenerate it with
``python -m discord_activity_tracker.scripts.write_staging_json_schema`` (see
script docstring) or by calling ``write_staging_json_schema`` from a REPL.

Human-readable field definitions and cross-tracker alignment notes live in
``docs/discord-tracker-schema.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, NoReturn, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from core.utils.datetime_parsing import CANONICAL_INSTANT_UTC_Z_PATTERN

NormalizedMessageInstantUtcZ = Annotated[
    str, Field(pattern=CANONICAL_INSTANT_UTC_Z_PATTERN)
]


class StagingValidationError(ValueError):
    """Discord staging payload failed Pydantic validation (envelope or normalized message)."""


class DiscordExporterGuild(BaseModel):
    """Guild object inside a DiscordChatExporter JSON file."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Union[str, int, None] = None
    name: str = ""
    iconUrl: str | None = Field(default=None, validation_alias="iconUrl")


class DiscordExporterChannel(BaseModel):
    """Channel object inside a DiscordChatExporter JSON file."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Union[str, int, None] = None
    name: str = ""
    type: str | None = None
    topic: str | None = None
    category: str | None = None
    categoryId: Union[str, int, None] = Field(
        default=None, validation_alias="categoryId"
    )


class DiscordChatExporterEnvelope(BaseModel):
    """Top-level shape of a DiscordChatExporter ``.json`` export."""

    model_config = ConfigDict(extra="allow")

    guild: DiscordExporterGuild = Field(default_factory=DiscordExporterGuild)
    channel: DiscordExporterChannel = Field(default_factory=DiscordExporterChannel)
    messages: list[Any] = Field(default_factory=list)

    @field_validator("messages", mode="before")
    @classmethod
    def _messages_must_be_list(cls, v: Any) -> Any:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("messages must be a JSON array")
        return v


class NormalizedAttachment(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str | None = None


class NormalizedAuthorExport(BaseModel):
    """Author block after ``convert_exporter_message_to_dict``."""

    model_config = ConfigDict(extra="allow")

    id: int = 0
    username: str = "unknown"
    global_name: str = ""
    avatar_url: str = ""
    bot: bool = False


class NormalizedReaction(BaseModel):
    model_config = ConfigDict(extra="allow")

    emoji: str = Field(min_length=1)
    count: int = Field(ge=0)


class NormalizedDiscordMessage(BaseModel):
    """Post-converter message dict (API-shaped + canonical enrichment fields)."""

    model_config = ConfigDict(extra="forbid")

    id: int
    content: str = ""
    created_at: NormalizedMessageInstantUtcZ
    edited_at: NormalizedMessageInstantUtcZ | None = None
    message_type: str = "Default"
    is_pinned: bool = False
    author: NormalizedAuthorExport
    attachments: list[NormalizedAttachment] = Field(default_factory=list)
    reactions: list[NormalizedReaction] = Field(default_factory=list)
    reference: dict[str, Any] | None = None
    occurred_at: NormalizedMessageInstantUtcZ | None = None
    actor_id: str | None = None
    source_url: str | None = None

    @field_validator("edited_at", "occurred_at", mode="before")
    @classmethod
    def _blank_optional_timestamp_to_none(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v


def _validation_error(prefix: str, err: ValidationError) -> NoReturn:
    detail = err.errors()[:5]
    msg = f"{prefix}: " + "; ".join(
        f"{e.get('loc', ())}: {e.get('msg', '')}" for e in detail
    )
    if len(err.errors()) > 5:
        msg += f" … ({len(err.errors())} errors total)"
    raise StagingValidationError(msg) from err


def validate_envelope(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> DiscordChatExporterEnvelope:
    """Validate parsed DiscordChatExporter file contents. Raises ``StagingValidationError``."""
    prefix = f"Invalid Discord export envelope{f' ({source})' if source else ''}"
    try:
        return DiscordChatExporterEnvelope.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)


def validate_normalized_message(
    obj: dict[str, Any],
    *,
    source: str | None = None,
) -> NormalizedDiscordMessage:
    """Validate one normalized message dict. Raises ``StagingValidationError``."""
    prefix = f"Invalid normalized Discord message{f' ({source})' if source else ''}"
    try:
        return NormalizedDiscordMessage.model_validate(obj)
    except ValidationError as e:
        _validation_error(prefix, e)


def build_staging_json_schema_bundle() -> dict[str, Any]:
    """Build a JSON-serializable object holding JSON Schemas for reviewer use."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "discord_staging_v1",
        "description": (
            "Optional JSON Schema bundle for Discord staging data. Runtime "
            "validation uses Pydantic models in discord_activity_tracker/staging_schema.py."
        ),
        "discord_chat_exporter_envelope": DiscordChatExporterEnvelope.model_json_schema(
            ref_template="#/discord_chat_exporter_envelope/$defs/{model}"
        ),
        "normalized_discord_message": NormalizedDiscordMessage.model_json_schema(
            ref_template="#/normalized_discord_message/$defs/{model}"
        ),
    }


def write_staging_json_schema(path: Path | None = None) -> Path:
    """Write ``discord_staging_v1.json`` next to this package's ``schemas/`` dir."""
    target = path or (
        Path(__file__).resolve().parent / "schemas" / "discord_staging_v1.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    bundle = build_staging_json_schema_bundle()
    target.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return target
