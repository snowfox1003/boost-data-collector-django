"""Frozen DTOs implementing :mod:`core.protocols` for Reddit activity tracker."""

from __future__ import annotations

from dataclasses import dataclass

from core.protocol_dto import IncrementalStateDataclass


@dataclass(frozen=True, repr=False)
class RedditIncrementalState(IncrementalStateDataclass):
    """Checkpoint between Reddit runs with per-subreddit cursors."""

    @classmethod
    def from_subreddit_cursors(
        cls,
        *,
        submissions: dict[str, int],
        comments: dict[str, int],
    ) -> RedditIncrementalState:
        subreddit_names = sorted(set(submissions) | set(comments))
        token_parts = [f"reddit:{','.join(subreddit_names)}"]
        marker_parts = []
        for name in subreddit_names:
            sub_ts = submissions.get(name, 0)
            com_ts = comments.get(name, 0)
            if sub_ts or com_ts:
                marker_parts.append(f"{name}:s{sub_ts}/c{com_ts}")
        return cls(
            checkpoint_token=":".join(token_parts),
            human_readable_marker="; ".join(marker_parts) or None,
            extras={
                "submission_cursors": dict(submissions),
                "comment_cursors": dict(comments),
            },
        )
