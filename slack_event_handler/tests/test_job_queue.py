"""Tests for slack_event_handler.utils.job_queue."""

import threading
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from slack_event_handler.utils import job_queue
from slack_event_handler.utils.rate_limiter import record_posted
from slack_event_handler.utils.state import load_state


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

    with patch("slack_event_handler.utils.job_queue.wait_and_reserve_slot"):
        with patch("slack_event_handler.utils.job_queue.post_pr_comment"):
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

    with patch("slack_event_handler.utils.job_queue.wait_and_reserve_slot"):
        with patch("slack_event_handler.utils.job_queue.post_pr_comment"):
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

    with patch("slack_event_handler.utils.job_queue.wait_and_reserve_slot"):
        with patch("slack_event_handler.utils.job_queue.post_pr_comment"):
            with pytest.raises(RuntimeError, match="boom"):
                job_queue._process_job(job)


@pytest.mark.django_db
def test_process_job_clears_busy_after_slot_reserved(settings):
    settings.SLACK_PR_BOT_GITHUB_TOKEN = "tok"
    job_queue.set_slack_app(MagicMock(), "T1")
    job = {
        job_queue.KEY_JOB_ID: "jid",
        job_queue.KEY_TEAM_ID: "T1",
        job_queue.KEY_OWNER: "o",
        job_queue.KEY_REPO: "r",
        job_queue.KEY_PULL_NUMBER: 1,
        job_queue.KEY_CHANNEL: "C1",
        job_queue.KEY_MESSAGE_TS: "9.9",
        job_queue.KEY_USER_ID: "U1",
        job_queue.KEY_IS_DM: False,
    }

    with patch("slack_event_handler.utils.job_queue.wait_and_reserve_slot"):
        with patch("slack_event_handler.utils.job_queue.post_pr_comment"):
            job_queue._process_job(job)

    with job_queue._worker_busy_lock:
        assert not job_queue._worker_busy_by_team.get("T1", False)


@pytest.mark.django_db
def test_estimated_delay_sec_nonzero_with_jobs_ahead(settings, tmp_path):
    settings.SLACK_PR_BOT_COMMENTS_MAX_PER_WINDOW = 2
    settings.SLACK_PR_BOT_COMMENTS_WINDOW_SECONDS = 100
    path = tmp_path / "state.json"
    import json

    now = 1000.0
    state = {
        "postedAt": [now - 10, now - 5],
        "queue": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
    }
    path.write_text(json.dumps(state))

    with patch(
        "slack_event_handler.utils.state._get_state_file_path",
        return_value=str(path),
    ):
        with patch("slack_event_handler.utils.job_queue.time.time", return_value=now):
            d = job_queue.estimated_delay_sec("T9")
    assert d >= 0


@pytest.mark.django_db
def test_send_reply_chat_post_message_failure_logs(settings):
    mock_app = MagicMock()
    mock_app.client.chat_postMessage.side_effect = OSError("network")
    job_queue.set_slack_app(mock_app, "T1")
    job_queue._send_reply("T1", "C1", "9.9", False, "hi")
    mock_app.client.chat_postMessage.assert_called_once()


@pytest.mark.django_db
def test_process_job_dm_uses_chat_post_message_without_thread_ts(settings):
    settings.SLACK_PR_BOT_GITHUB_TOKEN = "tok"
    mock_app = MagicMock()
    job_queue.set_slack_app(mock_app, "T1")

    job = {
        job_queue.KEY_JOB_ID: "jid",
        job_queue.KEY_TEAM_ID: "T1",
        job_queue.KEY_OWNER: "o",
        job_queue.KEY_REPO: "r",
        job_queue.KEY_PULL_NUMBER: 3,
        job_queue.KEY_CHANNEL: "D1",
        job_queue.KEY_MESSAGE_TS: "9.9",
        job_queue.KEY_USER_ID: "U1",
        job_queue.KEY_IS_DM: True,
    }

    with patch("slack_event_handler.utils.job_queue.wait_and_reserve_slot"):
        with patch("slack_event_handler.utils.job_queue.post_pr_comment"):
            job_queue._process_job(job)

    kwargs = mock_app.client.chat_postMessage.call_args.kwargs
    assert "thread_ts" not in kwargs


@pytest.mark.django_db
def test_process_job_skips_reaction_when_team_id_none(settings):
    settings.SLACK_PR_BOT_GITHUB_TOKEN = "tok"
    mock_app = MagicMock()
    job_queue.set_slack_app(mock_app, "TX")

    job = {
        job_queue.KEY_JOB_ID: "jid",
        job_queue.KEY_TEAM_ID: None,
        job_queue.KEY_OWNER: "o",
        job_queue.KEY_REPO: "r",
        job_queue.KEY_PULL_NUMBER: 3,
        job_queue.KEY_CHANNEL: "C1",
        job_queue.KEY_MESSAGE_TS: "9.9",
        job_queue.KEY_USER_ID: "U1",
        job_queue.KEY_IS_DM: False,
    }

    with patch("slack_event_handler.utils.job_queue.wait_and_reserve_slot"):
        with patch("slack_event_handler.utils.job_queue.post_pr_comment"):
            job_queue._process_job(job)

    mock_app.client.reactions_add.assert_not_called()


@pytest.mark.django_db
def test_process_job_logs_when_rate_limited(settings):
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

    with patch("slack_event_handler.utils.job_queue.compute_delay", return_value=5.0):
        with patch("slack_event_handler.utils.job_queue.wait_and_reserve_slot"):
            with patch("slack_event_handler.utils.job_queue.post_pr_comment"):
                with patch("slack_event_handler.utils.job_queue.logger") as log:
                    job_queue._process_job(job)
    assert log.debug.called


@pytest.mark.django_db
def test_worker_processes_job_then_exits_on_sleep(settings):
    settings.SLACK_PR_BOT_GITHUB_TOKEN = "tok"
    job_queue.set_slack_app(MagicMock(), "T1")

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

    loads = [
        {"queue": [job], "postedAt": []},
        {"queue": [], "postedAt": []},
    ]

    @contextmanager
    def fake_modify(team_id=None):
        state = loads.pop(0) if loads else {"queue": [], "postedAt": []}
        yield state

    def sleep_side_effect(_sec):
        raise RuntimeError("stop_worker_loop")

    load_peeks = [
        {"queue": [job], "postedAt": []},
        {"queue": [], "postedAt": []},
    ]

    def load_side_effect(team_id=None):
        if load_peeks:
            return load_peeks.pop(0)
        return {"queue": [], "postedAt": []}

    with patch.object(job_queue, "modify_state", fake_modify):
        with patch.object(job_queue, "load_state", side_effect=load_side_effect):
            with patch.object(job_queue, "wait_and_reserve_slot"):
                with patch.object(job_queue, "post_pr_comment"):
                    with patch.object(
                        job_queue.time, "sleep", side_effect=sleep_side_effect
                    ):
                        with pytest.raises(RuntimeError, match="stop_worker_loop"):
                            job_queue._worker("T1")


@pytest.mark.django_db
def test_worker_process_job_failure_sends_error_reply(settings):
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

    loads = [
        {"queue": [job], "postedAt": []},
        {"queue": [], "postedAt": []},
    ]

    @contextmanager
    def fake_modify(team_id=None):
        state = loads.pop(0) if loads else {"queue": [], "postedAt": []}
        yield state

    def sleep_side_effect(_sec):
        raise RuntimeError("stop_worker_loop")

    load_peeks = [
        {"queue": [job], "postedAt": []},
        {"queue": [], "postedAt": []},
    ]

    def load_side_effect(team_id=None):
        if load_peeks:
            return load_peeks.pop(0)
        return {"queue": [], "postedAt": []}

    with patch.object(job_queue, "modify_state", fake_modify):
        with patch.object(job_queue, "load_state", side_effect=load_side_effect):
            with patch.object(
                job_queue, "post_pr_comment", side_effect=RuntimeError("gh")
            ):
                with patch.object(job_queue, "wait_and_reserve_slot"):
                    with patch.object(
                        job_queue.time, "sleep", side_effect=sleep_side_effect
                    ):
                        with pytest.raises(RuntimeError, match="stop_worker_loop"):
                            job_queue._worker("T1")

    texts = [
        (ca.kwargs.get("text") or "")
        for ca in mock_app.client.chat_postMessage.call_args_list
    ]
    assert any("Could not post" in t for t in texts)


@pytest.mark.django_db
def test_concurrent_enqueue_preserves_all_jobs(settings, tmp_path):
    settings.SLACK_PR_BOT_COMMENTS_MAX_PER_WINDOW = 5
    path = tmp_path / "state_T9.json"
    n = 30
    barrier = threading.Barrier(n)
    job_ids: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker():
        try:
            barrier.wait(timeout=10)
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
            with lock:
                job_ids.append(job[job_queue.KEY_JOB_ID])
        except BaseException as e:
            with lock:
                errors.append(e)

    with patch(
        "slack_event_handler.utils.state._get_state_file_path",
        return_value=str(path),
    ):
        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert all(not t.is_alive() for t in threads)

        assert not errors
        loaded = load_state("T9")
        assert len(loaded["queue"]) == n
        assert len(set(job_ids)) == n


@pytest.mark.django_db
def test_concurrent_enqueue_and_record_posted(settings, tmp_path):
    settings.SLACK_PR_BOT_COMMENTS_MAX_PER_WINDOW = 10
    path = tmp_path / "state_T9.json"
    n_enqueue = 15
    n_posted = 15
    n_total = n_enqueue + n_posted
    barrier = threading.Barrier(n_total)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def enqueue_worker():
        try:
            barrier.wait(timeout=10)
            job_queue.enqueue_job(
                owner="o",
                repo="r",
                pull_number=1,
                channel="C1",
                message_ts="1.0",
                user_id="U1",
                team_id="T9",
            )
        except BaseException as e:
            with lock:
                errors.append(e)

    def posted_worker():
        try:
            barrier.wait(timeout=10)
            record_posted("T9")
        except BaseException as e:
            with lock:
                errors.append(e)

    with patch(
        "slack_event_handler.utils.state._get_state_file_path",
        return_value=str(path),
    ):
        with patch(
            "slack_event_handler.utils.rate_limiter.time.time", return_value=42.0
        ):
            threads = [
                threading.Thread(target=enqueue_worker) for _ in range(n_enqueue)
            ]
            threads += [threading.Thread(target=posted_worker) for _ in range(n_posted)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)
            assert all(not t.is_alive() for t in threads)

            assert not errors
            loaded = load_state("T9")
            assert len(loaded["queue"]) == n_enqueue
            assert len(loaded["postedAt"]) == n_posted
