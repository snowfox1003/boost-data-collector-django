"""Pydantic models for GitHub REST API payloads at ingestion boundaries."""

from __future__ import annotations

from typing import Any, NoReturn

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class GitHubApiValidationError(ValueError):
    """GitHub API payload failed Pydantic validation."""


class GitHubUser(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    login: str = ""
    name: str | None = None
    avatar_url: str | None = None


class GitHubLabel(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""


class GitHubComment(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    body: str = ""
    user: GitHubUser | None = None
    created_at: str | None = None
    updated_at: str | None = None


class GitHubReview(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    body: str = ""
    user: GitHubUser | None = None
    in_reply_to_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class GitHubRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    sha: str = ""


class GitHubIssue(BaseModel):
    model_config = ConfigDict(extra="allow")

    number: int
    id: int | None = None
    title: str = ""
    body: str | None = ""
    state: str = "open"
    state_reason: str = ""
    user: GitHubUser | None = None
    created_at: str | None = None
    updated_at: str | None = None
    closed_at: str | None = None
    comments: list[GitHubComment] = Field(default_factory=list)
    assignees: list[GitHubUser] = Field(default_factory=list)
    labels: list[GitHubLabel] = Field(default_factory=list)


class GitHubPullRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    number: int
    id: int | None = None
    title: str = ""
    body: str | None = ""
    state: str = "open"
    user: GitHubUser | None = None
    head: GitHubRef = Field(default_factory=GitHubRef)
    base: GitHubRef = Field(default_factory=GitHubRef)
    created_at: str | None = None
    updated_at: str | None = None
    merged_at: str | None = None
    closed_at: str | None = None
    comments: list[GitHubComment] = Field(default_factory=list)
    reviews: list[GitHubReview] = Field(default_factory=list)
    assignees: list[GitHubUser] = Field(default_factory=list)
    labels: list[GitHubLabel] = Field(default_factory=list)


class GitHubCommitAuthor(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str | None = None
    email: str | None = None
    date: str | None = None


class GitHubCommitBlob(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str = ""
    author: GitHubCommitAuthor | None = None
    committer: GitHubCommitAuthor | None = None


class GitHubCommitFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    filename: str | None = None
    previous_filename: str | None = None
    status: str | None = None
    additions: int | None = None
    deletions: int | None = None
    patch: str | None = None


class GitHubCommit(BaseModel):
    model_config = ConfigDict(extra="allow")

    sha: str
    author: GitHubUser | None = None
    committer: GitHubUser | None = None
    commit: GitHubCommitBlob = Field(default_factory=GitHubCommitBlob)
    files: list[GitHubCommitFile] = Field(default_factory=list)


class GitHubIssueBundle(BaseModel):
    """Fetcher/sync bundle: flat issue or nested issue_info + comments."""

    model_config = ConfigDict(extra="allow")

    issue: GitHubIssue

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "issue" in data and isinstance(data.get("issue"), dict):
            return data
        if "issue_info" in data and isinstance(data.get("issue_info"), dict):
            issue = dict(data["issue_info"])
            raw_comments = data.get("comments", issue.get("comments", []))
            issue["comments"] = raw_comments if isinstance(raw_comments, list) else []
            return {"issue": issue}
        issue = {k: v for k, v in data.items() if k != "comments"}
        raw_comments = data.get("comments", [])
        issue["comments"] = raw_comments if isinstance(raw_comments, list) else []
        return {"issue": issue}


class GitHubPullRequestBundle(BaseModel):
    """Fetcher/sync bundle: flat PR or nested pr_info + comments + reviews."""

    model_config = ConfigDict(extra="allow")

    pr: GitHubPullRequest

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if "pr" in data and isinstance(data.get("pr"), dict):
            return data
        if "pr_info" in data and isinstance(data.get("pr_info"), dict):
            pr = dict(data["pr_info"])
            raw_comments = data.get("comments", pr.get("comments", []))
            raw_reviews = data.get("reviews", pr.get("reviews", []))
            pr["comments"] = raw_comments if isinstance(raw_comments, list) else []
            pr["reviews"] = raw_reviews if isinstance(raw_reviews, list) else []
            return {"pr": pr}
        pr = {k: v for k, v in data.items() if k not in ("comments", "reviews")}
        raw_comments = data.get("comments", [])
        raw_reviews = data.get("reviews", [])
        pr["comments"] = raw_comments if isinstance(raw_comments, list) else []
        pr["reviews"] = raw_reviews if isinstance(raw_reviews, list) else []
        return {"pr": pr}


def _validation_error(prefix: str, err: ValidationError) -> NoReturn:
    detail = err.errors()[:5]
    msg = f"{prefix}: " + "; ".join(
        f"{e.get('loc', ())}: {e.get('msg', '')}" for e in detail
    )
    if len(err.errors()) > 5:
        msg += f" … ({len(err.errors())} errors total)"
    raise GitHubApiValidationError(msg) from err


def parse_issue_bundle(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> GitHubIssueBundle:
    prefix = f"Invalid GitHub issue bundle{f' ({source})' if source else ''}"
    try:
        return GitHubIssueBundle.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)


def parse_pr_bundle(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> GitHubPullRequestBundle:
    prefix = f"Invalid GitHub PR bundle{f' ({source})' if source else ''}"
    try:
        return GitHubPullRequestBundle.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)


def parse_commit(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> GitHubCommit:
    prefix = f"Invalid GitHub commit{f' ({source})' if source else ''}"
    try:
        return GitHubCommit.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)


def parse_comment(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> GitHubComment:
    prefix = f"Invalid GitHub comment{f' ({source})' if source else ''}"
    try:
        return GitHubComment.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)


def parse_review(
    data: dict[str, Any],
    *,
    source: str | None = None,
) -> GitHubReview:
    prefix = f"Invalid GitHub review{f' ({source})' if source else ''}"
    try:
        return GitHubReview.model_validate(data)
    except ValidationError as e:
        _validation_error(prefix, e)
