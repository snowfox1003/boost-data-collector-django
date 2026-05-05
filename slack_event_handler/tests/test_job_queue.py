"""Tests for slack_event_handler.utils.job_queue."""

from unittest.mock import MagicMock, patch

import pytest

from slack_event_handler.utils import job_queue


@pytest.fixture(autouse=True)
def reset_job_queue_globals():
    with job_queue._slack_app_by_team_lock:
        job_queue._slack_app_by_team.clear()
    with job_queue._worker_busy_lock:
        job_queue._worker_busy_by_team.clear()
    yield
    with job_queue._slack_app_by_team_lock:
        job_queue._slack_app_by_team.clear()
    with job_queue._worker_busy_lock:
        job_queue._worker_busy_by_team.clear()


@pytest.mark.django_db
def test_enqueue_job_persists_to_state(settings, tmp_path):
    settings.SLACK_PR_BOT_COMMENTS_MAX_PER_WINDOW = 5
    path = tmp_path / "state.json"
    with patch(
        "slack_event_handler.utils.state._get_state_file_path",
        return_value=str(path),
    ):
        job = job_queue.enqueue_job(
            owner="o",
            repo="r",
            pull_number=1,
            channel="C1",
            message_ts="1.0",
            user_id="U1",
            is_dm=False,
            team_id="T9",
        )
    assert job[job_queue.KEY_OWNER] == "o"
    assert job[job_queue.KEY_TEAM_ID] == "T9"


@pytest.mark.django_db
def test_estimated_delay_sec_zero_when_empty_queue(settings, tmp_path):
    settings.SLACK_PR_BOT_COMMENTS_MAX_PER_WINDOW = 5
    settings.SLACK_PR_BOT_COMMENTS_WINDOW_SECONDS = 3600
    path = tmp_path / "state.json"
    empty = {"postedAt": [], "queue": []}
    import json

    path.write_text(json.dumps(empty))

    with patch(
        "slack_event_handler.utils.state._get_state_file_path",
        return_value=str(path),
    ):
        assert job_queue.estimated_delay_sec("T1") == 0


@pytest.mark.django_db
def test_set_slack_app_registers_team():
    app = MagicMock()
    job_queue.set_slack_app(app, "T1")
    with job_queue._slack_app_by_team_lock:
        assert job_queue._slack_app_by_team["T1"] is app


@pytest.mark.django_db
def test_send_reply_no_app_no_crash():
    job_queue._send_reply("T1", "C", "1.0", False, "hi")


@pytest.mark.django_db
def test_process_job_posts_and_replies(settings):
    settings.SLACK_PR_BOT_GITHUB_TOKEN = "tok"

    mock_app = MagicMock()
    job_queue.set_slack_app(mock_app, "T1")

    job = {
        job_queue.KEY_JOB_ID: "jid",
        job_queue.KEY_TEAM_ID: "T1",
        job_queue.KEY_OWNER: "o",
        job_queue.KEY_REPO: "r",
        job_queue.KEY_PULL_NUMBER: 3,
        job_queue.KEY_CHANNEL: "C1",
        job_queue.KEY_MESSAGE_TS: "9.9",
        job_queue.KEY_USER_ID: "U1",
        job_queue.KEY_IS_DM: False,
    }

    with patch("slack_event_handler.utils.job_queue.wait_for_slot"):
        with patch("slack_event_handler.utils.job_queue.post_pr_comment"):
            with patch("slack_event_handler.utils.job_queue.record_posted"):
                job_queue._process_job(job)

    mock_app.client.chat_postMessage.assert_called_once()
    mock_app.client.reactions_add.assert_called_once()


@pytest.mark.django_db
def test_process_job_reactions_already_reacted_swallows(settings):
    settings.SLACK_PR_BOT_GITHUB_TOKEN = "tok"
    mock_app = MagicMock()
    mock_app.client.reactions_add.side_effect = Exception(
        "error already_reacted something"
    )
    job_queue.set_slack_app(mock_app, "T1")

    job = {
        job_queue.KEY_JOB_ID: "j",
        job_queue.KEY_TEAM_ID: "T1",
        job_queue.KEY_OWNER: "o",
        job_queue.KEY_REPO: "r",
        job_queue.KEY_PULL_NUMBER: 1,
        job_queue.KEY_CHANNEL: "C",
        job_queue.KEY_MESSAGE_TS: "t",
        job_queue.KEY_USER_ID: "U",
        job_queue.KEY_IS_DM: False,
    }

    with patch("slack_event_handler.utils.job_queue.wait_for_slot"):
        with patch("slack_event_handler.utils.job_queue.post_pr_comment"):
            with patch("slack_event_handler.utils.job_queue.record_posted"):
                job_queue._process_job(job)


@pytest.mark.django_db
def test_process_job_reactions_other_error_raises(settings):
    settings.SLACK_PR_BOT_GITHUB_TOKEN = "tok"
    mock_app = MagicMock()
    mock_app.client.reactions_add.side_effect = RuntimeError("boom")
    job_queue.set_slack_app(mock_app, "T1")

    job = {
        job_queue.KEY_JOB_ID: "j",
        job_queue.KEY_TEAM_ID: "T1",
        job_queue.KEY_OWNER: "o",
        job_queue.KEY_REPO: "r",
        job_queue.KEY_PULL_NUMBER: 1,
        job_queue.KEY_CHANNEL: "C",
        job_queue.KEY_MESSAGE_TS: "t",
        job_queue.KEY_USER_ID: "U",
        job_queue.KEY_IS_DM: False,
    }

    with patch("slack_event_handler.utils.job_queue.wait_for_slot"):
        with patch("slack_event_handler.utils.job_queue.post_pr_comment"):
            with patch("slack_event_handler.utils.job_queue.record_posted"):
                with pytest.raises(RuntimeError, match="boom"):
                    job_queue._process_job(job)
