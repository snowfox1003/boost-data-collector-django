"""Tests for boost_mailing_list_tracker management commands."""

import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from boost_mailing_list_tracker.models import MailingListMessage, MailingListName


def _valid_email_data(
    msg_id: str = "<test-msg@example.com>",
    list_name: str | None = None,
    sent_at_str: str = "2025-01-15T10:00:00Z",
) -> dict:
    """Build a minimal valid email_data dict for _persist_email."""
    if list_name is None:
        list_name = MailingListName.BOOST_USERS.value
    return {
        "msg_id": msg_id,
        "sender_name": "Test Sender",
        "sender_address": "sender@example.com",
        "sent_at": sent_at_str,
        "parent_id": "",
        "thread_id": "",
        "subject": "Test subject",
        "content": "Test content",
        "list_name": list_name,
    }


@pytest.mark.django_db
def test_persist_email_creates_message():
    """_persist_email creates MailingListMessage and returns (True, False)."""
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _persist_email,
    )

    email_data = _valid_email_data(msg_id="<create-me@example.com>")
    was_created, skipped, persist_failed = _persist_email(email_data)
    assert was_created is True
    assert skipped is False
    assert persist_failed is False
    assert MailingListMessage.objects.filter(msg_id="<create-me@example.com>").exists()


@pytest.mark.django_db
def test_persist_email_skips_when_msg_id_empty():
    """_persist_email returns (False, True) when msg_id is missing or empty."""
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _persist_email,
    )

    email_data = _valid_email_data()
    email_data["msg_id"] = ""
    was_created, skipped, persist_failed = _persist_email(email_data)
    assert was_created is False
    assert skipped is True
    assert persist_failed is False

    email_data["msg_id"] = "   "
    was_created2, skipped2, persist_failed2 = _persist_email(email_data)
    assert was_created2 is False
    assert skipped2 is True
    assert persist_failed2 is False


@pytest.mark.django_db
def test_persist_email_skips_duplicate_msg_id():
    """_persist_email skips when message with same msg_id already exists."""
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _persist_email,
    )

    email_data = _valid_email_data(msg_id="<duplicate@example.com>")
    was_created1, skipped1, persist_failed1 = _persist_email(email_data)
    assert was_created1 is True
    assert skipped1 is False
    assert persist_failed1 is False

    was_created2, skipped2, persist_failed2 = _persist_email(email_data)
    assert was_created2 is False
    assert skipped2 is True
    assert persist_failed2 is False
    assert (
        MailingListMessage.objects.filter(msg_id="<duplicate@example.com>").count() == 1
    )


@pytest.mark.django_db
def test_persist_email_persists_with_invalid_sent_at():
    """_persist_email still creates message when sent_at is unparseable; sent_at is stored as None."""
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _persist_email,
    )

    email_data = _valid_email_data(
        msg_id="<bad-date@example.com>", sent_at_str="not-a-date"
    )
    was_created, skipped, persist_failed = _persist_email(email_data)
    assert was_created is True
    assert skipped is False
    assert persist_failed is False
    msg = MailingListMessage.objects.get(msg_id="<bad-date@example.com>")
    assert msg.sent_at is None


@pytest.mark.django_db
def test_persist_email_creates_profile_and_message():
    """_persist_email creates MailingListProfile via get_or_create_mailing_list_profile when new."""
    from cppa_user_tracker.models import MailingListProfile

    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _persist_email,
    )

    initial_profiles = MailingListProfile.objects.count()
    email_data = _valid_email_data(
        msg_id="<new-sender@example.com>",
    )
    email_data["sender_name"] = "Brand New"
    email_data["sender_address"] = "brandnew@example.com"
    was_created, skipped, persist_failed = _persist_email(email_data)
    assert was_created is True
    assert skipped is False
    assert persist_failed is False
    assert MailingListProfile.objects.filter(display_name="Brand New").exists()
    assert MailingListProfile.objects.count() >= initial_profiles + 1


@pytest.mark.django_db
def test_command_handle_dry_run_exits_cleanly(capsys):
    """Command with --dry-run runs without writing to DB and exits cleanly."""
    from django.core.management import call_command

    with patch(
        "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.fetch_all_emails",
        return_value=[],
    ):
        call_command("run_boost_mailing_list_tracker", "--dry-run")
    out, _ = capsys.readouterr()
    assert "dry run" in out.lower()


# --- _clean_text ---


def test_clean_text_none_and_nul_bytes():
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _clean_text,
    )

    assert _clean_text(None) == ""
    assert _clean_text("ab\x00cd") == "abcd"


# --- _persist_email branches ---


@pytest.mark.django_db
def test_persist_email_missing_sender_address_logs_incomplete(
    caplog,
):
    """Missing sender_address still persists when list_name is valid; logs Incomplete email."""
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _persist_email,
    )

    caplog.set_level(logging.WARNING)
    email_data = _valid_email_data(msg_id="<no-addr@example.com>")
    email_data["sender_address"] = ""
    was_created, skipped, persist_failed = _persist_email(email_data)
    assert was_created is True
    assert skipped is False
    assert persist_failed is False
    assert MailingListMessage.objects.filter(msg_id="<no-addr@example.com>").exists()
    assert any("Incomplete email" in r.message for r in caplog.records)
    assert any("missing sender_address" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_persist_email_invalid_list_name_returns_persist_failed():
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _persist_email,
    )

    email_data = _valid_email_data(msg_id="<bad-list@example.com>")
    email_data["list_name"] = ""
    was_created, skipped, persist_failed = _persist_email(email_data)
    assert was_created is False
    assert skipped is False
    assert persist_failed is True
    assert not MailingListMessage.objects.filter(
        msg_id="<bad-list@example.com>"
    ).exists()


# --- _process_existing_workspace_json ---


@pytest.mark.django_db
def test_process_existing_workspace_json_valid_unlinks_file(tmp_path):
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _process_existing_workspace_json,
    )

    list_name = MailingListName.BOOST_USERS.value
    msg_path = (
        tmp_path / "boost_mailing_list_tracker" / list_name / "messages" / "one.json"
    )
    msg_path.parent.mkdir(parents=True)
    msg_path.write_text(
        '[{"msg_id": "<ws-one@example.com>", "list_name": "'
        + MailingListName.BOOST_USERS.value
        + '", "sent_at": "2025-01-15T10:00:00Z", "sender_address": "p@w.com", '
        '"sender_name": "P", "subject": "S", "content": "C"}]',
        encoding="utf-8",
    )
    with patch(
        "boost_mailing_list_tracker.workspace.get_workspace_path",
        side_effect=lambda slug: tmp_path / slug,
    ):
        processed, skipped = _process_existing_workspace_json(list_name)
    assert processed == 1
    assert skipped == 0
    assert not msg_path.exists()
    assert MailingListMessage.objects.filter(msg_id="<ws-one@example.com>").exists()


@pytest.mark.django_db
def test_process_existing_workspace_json_malformed_leaves_file(tmp_path):
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _process_existing_workspace_json,
    )

    list_name = MailingListName.BOOST.value
    msg_path = (
        tmp_path / "boost_mailing_list_tracker" / list_name / "messages" / "bad.json"
    )
    msg_path.parent.mkdir(parents=True)
    msg_path.write_text("{ not json", encoding="utf-8")
    with patch(
        "boost_mailing_list_tracker.workspace.get_workspace_path",
        side_effect=lambda slug: tmp_path / slug,
    ):
        processed, _skipped = _process_existing_workspace_json(list_name)
    assert processed == 0
    assert msg_path.is_file()


# --- _run_pinecone_sync ---


def test_run_pinecone_sync_skips_empty_app_type(caplog):
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _run_pinecone_sync,
    )

    caplog.set_level(logging.WARNING)
    _run_pinecone_sync(app_type="", namespace="ns")
    assert "pinecone sync skipped" in caplog.text.lower()
    assert "--pinecone-app-type" in caplog.text.lower()


def test_run_pinecone_sync_skips_empty_namespace(caplog):
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _run_pinecone_sync,
    )

    caplog.set_level(logging.WARNING)
    _run_pinecone_sync(app_type="t", namespace="")
    assert "namespace" in caplog.text.lower()


def test_run_pinecone_sync_calls_run_cppa_pinecone_sync():
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _run_pinecone_sync,
    )

    with patch(
        "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.call_command"
    ) as cc:
        _run_pinecone_sync(app_type="mailing", namespace="my-ns")
    assert cc.call_args is not None
    assert cc.call_args.args[0] == "run_cppa_pinecone_sync"


def test_run_pinecone_sync_logs_warning_when_call_command_raises(caplog):
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _run_pinecone_sync,
    )

    caplog.set_level(logging.WARNING)
    with patch(
        "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.call_command",
        side_effect=RuntimeError("no sync"),
    ):
        _run_pinecone_sync(app_type="mailing", namespace="ns")
    assert any("pinecone" in r.message.lower() for r in caplog.records)


# --- BoostMailingListTrackerCollector.run ---


@pytest.mark.django_db
def test_collector_run_writes_raw_and_removes_message_json(tmp_path):
    from django.core.management import call_command

    email_row = {
        "msg_id": "<collector-run@example.com>",
        "sender_name": "User",
        "sender_address": "user@example.com",
        "sent_at": "2025-01-15T10:00:00Z",
        "parent_id": "",
        "thread_id": "",
        "subject": "Sub",
        "content": "Body",
        "list_name": MailingListName.BOOST_USERS.value,
    }
    msg_json = tmp_path / "msg.json"
    raw_json = tmp_path / "raw.json"

    with patch(
        "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.fetch_all_emails",
        return_value=[email_row],
    ):
        with patch(
            "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.get_message_json_path",
            return_value=msg_json,
        ):
            with patch(
                "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.get_raw_json_path",
                return_value=raw_json,
            ):
                with patch(
                    "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker._run_pinecone_sync"
                ):
                    call_command("run_boost_mailing_list_tracker")

    assert raw_json.is_file()
    assert not msg_json.exists()
    assert MailingListMessage.objects.filter(
        msg_id="<collector-run@example.com>"
    ).exists()


@pytest.mark.django_db
def test_collector_run_keeps_message_json_when_persist_fails(tmp_path):
    from django.core.management import call_command

    email_row = _valid_email_data(msg_id="<persist-fail@example.com>")
    msg_json = tmp_path / "msg.json"
    raw_json = tmp_path / "raw.json"

    with patch(
        "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.fetch_all_emails",
        return_value=[email_row],
    ):
        with patch(
            "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.get_message_json_path",
            return_value=msg_json,
        ):
            with patch(
                "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.get_raw_json_path",
                return_value=raw_json,
            ):
                with patch(
                    "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker._persist_email",
                    return_value=(False, False, True),
                ):
                    with patch(
                        "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker._run_pinecone_sync"
                    ):
                        call_command("run_boost_mailing_list_tracker")

    assert msg_json.is_file()
    assert not MailingListMessage.objects.filter(
        msg_id="<persist-fail@example.com>"
    ).exists()


@pytest.mark.django_db
def test_collector_run_skips_empty_msg_id_and_duplicate(tmp_path):
    from django.core.management import call_command

    existing = _valid_email_data(msg_id="<dup-collector@example.com>")
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _persist_email,
    )

    _persist_email(existing)

    rows = [
        {
            "msg_id": "",
            "list_name": MailingListName.BOOST.value,
            "sender_address": "a@b.com",
            "sender_name": "A",
            "sent_at": "2025-01-15T10:00:00Z",
            "subject": "",
            "content": "",
        },
        _valid_email_data(msg_id="<dup-collector@example.com>"),
    ]
    msg_json = tmp_path / "m.json"
    raw_json = tmp_path / "r.json"
    with patch(
        "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.fetch_all_emails",
        return_value=rows,
    ):
        with patch(
            "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.get_message_json_path",
            return_value=msg_json,
        ):
            with patch(
                "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.get_raw_json_path",
                return_value=raw_json,
            ):
                with patch(
                    "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker._run_pinecone_sync"
                ):
                    call_command("run_boost_mailing_list_tracker")

    assert (
        MailingListMessage.objects.filter(msg_id="<dup-collector@example.com>").count()
        == 1
    )


@pytest.mark.django_db
def test_process_existing_workspace_json_keeps_file_when_persist_failed(tmp_path):
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _process_existing_workspace_json,
    )

    list_name = MailingListName.BOOST_USERS.value
    msg_path = (
        tmp_path / "boost_mailing_list_tracker" / list_name / "messages" / "fail.json"
    )
    msg_path.parent.mkdir(parents=True)
    msg_path.write_text('[{"msg_id": "<x@y>"}]', encoding="utf-8")
    with patch(
        "boost_mailing_list_tracker.workspace.get_workspace_path",
        side_effect=lambda slug: tmp_path / slug,
    ):
        with patch(
            "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker._persist_email",
            return_value=(False, False, True),
        ):
            processed, skipped = _process_existing_workspace_json(list_name)
    assert processed == 1
    assert skipped == 1
    assert msg_path.is_file()


@pytest.mark.django_db
def test_process_existing_workspace_json_keeps_file_when_persist_raises(tmp_path):
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _process_existing_workspace_json,
    )

    list_name = MailingListName.BOOST_USERS.value
    msg_path = (
        tmp_path / "boost_mailing_list_tracker" / list_name / "messages" / "raise.json"
    )
    msg_path.parent.mkdir(parents=True)
    msg_path.write_text('[{"msg_id": "<x@y>"}]', encoding="utf-8")
    with patch(
        "boost_mailing_list_tracker.workspace.get_workspace_path",
        side_effect=lambda slug: tmp_path / slug,
    ):
        with patch(
            "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker._persist_email",
            side_effect=RuntimeError("persist boom"),
        ):
            processed, skipped = _process_existing_workspace_json(list_name)
    assert processed == 1
    assert skipped == 1
    assert msg_path.is_file()


@pytest.mark.django_db
def test_collector_run_skips_malformed_email_write():
    from django.core.management import call_command

    email_row = {
        "msg_id": "<bad-write@example.com>",
        "sender_name": "U",
        "sender_address": "u@example.com",
        "sent_at": "2025-01-15T10:00:00Z",
        "parent_id": "",
        "thread_id": "",
        "subject": "S",
        "content": "C",
        "list_name": MailingListName.BOOST_USERS.value,
    }
    msg_json = MagicMock()
    msg_json.parent.mkdir = MagicMock()
    raw_json = MagicMock()
    raw_json.parent.mkdir = MagicMock()

    def _raise_bad_write(*a, **kw):
        raise ValueError("cannot serialize")

    msg_json.write_text.side_effect = _raise_bad_write

    with patch(
        "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.fetch_all_emails",
        return_value=[email_row],
    ):
        with patch(
            "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.get_message_json_path",
            return_value=msg_json,
        ):
            with patch(
                "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker.get_raw_json_path",
                return_value=raw_json,
            ):
                with patch(
                    "boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker._run_pinecone_sync"
                ):
                    call_command("run_boost_mailing_list_tracker")

    assert not MailingListMessage.objects.filter(
        msg_id="<bad-write@example.com>"
    ).exists()


@pytest.mark.django_db
def test_persist_email_unknown_sender_display_from_email_local_part():
    """Unknown Sender + valid address uses local-part as display when creating profile."""
    from cppa_user_tracker.models import MailingListProfile

    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        _persist_email,
    )

    email_data = _valid_email_data(msg_id="<localpart@example.com>")
    email_data["sender_name"] = ""
    email_data["sender_address"] = "someone@example.org"
    was_created, skipped, persist_failed = _persist_email(email_data)
    assert was_created is True
    assert skipped is False
    assert persist_failed is False
    profile = MailingListProfile.objects.filter(
        emails__email="someone@example.org",
        display_name="someone",
    ).first()
    assert profile is not None


@pytest.mark.django_db
def test_get_collector_uses_settings_for_empty_pinecone_args(settings):
    from boost_mailing_list_tracker.management.commands.run_boost_mailing_list_tracker import (
        Command,
    )

    settings.BOOST_MAILING_LIST_PINECONE_APP_TYPE = "from-settings-type"
    settings.BOOST_MAILING_LIST_PINECONE_NAMESPACE = "from-settings-ns"
    cmd = Command(stdout=StringIO(), stderr=StringIO())
    collector = cmd.get_collector(
        start_date="",
        end_date="",
        dry_run=True,
        pinecone_app_type="",
        pinecone_namespace="",
    )
    assert collector.pinecone_app_type == "from-settings-type"
    assert collector.pinecone_namespace == "from-settings-ns"
