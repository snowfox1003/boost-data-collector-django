"""Smoke tests for Discord admin registrations and list_display fields."""


def test_discord_server_admin_registered():
    from django.contrib import admin
    from discord_activity_tracker.models import DiscordServer

    ma = admin.site._registry.get(DiscordServer)
    assert ma is not None


def test_discord_channel_admin_list_display_includes_category():
    from discord_activity_tracker.admin import DiscordChannelAdmin

    assert "category_name" in DiscordChannelAdmin.list_display
    assert "channel_id" in DiscordChannelAdmin.list_display


def test_discord_message_admin_list_display_includes_new_fields():
    from discord_activity_tracker.admin import DiscordMessageAdmin

    assert "message_type" in DiscordMessageAdmin.list_display
    assert "is_pinned" in DiscordMessageAdmin.list_display


def test_discord_message_admin_list_filter_includes_new_fields():
    from discord_activity_tracker.admin import DiscordMessageAdmin

    assert "message_type" in DiscordMessageAdmin.list_filter
    assert "is_pinned" in DiscordMessageAdmin.list_filter
