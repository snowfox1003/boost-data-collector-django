"""Tests for cppa_user_tracker.services."""

import pytest

from cppa_user_tracker.models import (
    DiscordProfile,
    Email,
    GitHubAccount,
    GitHubAccountType,
    Identity,
    SlackUser,
    TempProfileIdentityRelation,
    WG21PaperAuthorProfile,
    YoutubeSpeaker,
)
from cppa_slack_tracker.api_schemas import SlackApiValidationError
from cppa_user_tracker import services


# --- create_identity ---


@pytest.mark.django_db
def test_create_identity_with_display_name():
    """create_identity creates Identity with display_name."""
    identity = services.create_identity(display_name="Alice")
    assert identity.id is not None
    assert identity.display_name == "Alice"
    assert identity.description == ""


@pytest.mark.django_db
def test_create_identity_with_description():
    """create_identity creates Identity with description."""
    identity = services.create_identity(
        display_name="Bob",
        description="Developer",
    )
    assert identity.description == "Developer"


@pytest.mark.django_db
def test_create_identity_empty_defaults():
    """create_identity with empty strings creates valid Identity."""
    identity = services.create_identity(display_name="", description="")
    assert identity.id is not None
    assert identity.display_name == ""
    assert identity.description == ""


# --- get_or_create_identity ---


@pytest.mark.django_db
def test_get_or_create_identity_creates_new():
    """get_or_create_identity creates new Identity and returns (obj, True)."""
    identity, created = services.get_or_create_identity(display_name="New User")
    assert created is True
    assert identity.display_name == "New User"
    assert Identity.objects.filter(display_name="New User").count() == 1


@pytest.mark.django_db
def test_get_or_create_identity_gets_existing(identity):
    """get_or_create_identity returns existing Identity and (obj, False)."""
    identity, created = services.get_or_create_identity(
        display_name=identity.display_name,
    )
    assert created is False
    assert identity.display_name == "Test Identity"


@pytest.mark.django_db
def test_get_or_create_identity_updates_description(identity):
    """get_or_create_identity updates description when not created."""
    identity, created = services.get_or_create_identity(
        display_name=identity.display_name,
        description="Updated desc",
    )
    assert created is False
    identity.refresh_from_db()
    assert identity.description == "Updated desc"


# --- create_tmp_identity ---


@pytest.mark.django_db
def test_create_tmp_identity_with_display_name():
    """create_tmp_identity creates TmpIdentity with display_name."""
    tmp = services.create_tmp_identity(display_name="Staging")
    assert tmp.id is not None
    assert tmp.display_name == "Staging"
    assert tmp.description == ""


@pytest.mark.django_db
def test_create_tmp_identity_with_description():
    """create_tmp_identity creates with description."""
    tmp = services.create_tmp_identity(
        display_name="Staging",
        description="Temporary",
    )
    assert tmp.description == "Temporary"


@pytest.mark.django_db
def test_create_tmp_identity_empty_defaults():
    """create_tmp_identity with empty strings creates valid TmpIdentity."""
    tmp = services.create_tmp_identity(display_name="", description="")
    assert tmp.id is not None


# --- add_temp_profile_identity_relation ---


@pytest.mark.django_db
def test_add_temp_profile_identity_relation_creates(github_account, tmp_identity):
    """add_temp_profile_identity_relation creates new relation and returns (rel, True)."""
    rel, created = services.add_temp_profile_identity_relation(
        github_account,
        tmp_identity,
    )
    assert created is True
    assert rel.base_profile_id == github_account.id
    assert rel.target_identity_id == tmp_identity.id


@pytest.mark.django_db
def test_add_temp_profile_identity_relation_get_existing(
    github_account,
    tmp_identity,
):
    """add_temp_profile_identity_relation returns existing relation and (rel, False)."""
    services.add_temp_profile_identity_relation(github_account, tmp_identity)
    rel2, created2 = services.add_temp_profile_identity_relation(
        github_account,
        tmp_identity,
    )
    assert created2 is False
    assert (
        TempProfileIdentityRelation.objects.filter(
            base_profile=github_account,
            target_identity=tmp_identity,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_add_temp_profile_identity_relation_links_correctly(
    github_account,
    tmp_identity,
):
    """add_temp_profile_identity_relation links correct profile and tmp_identity."""
    rel, _ = services.add_temp_profile_identity_relation(
        github_account,
        tmp_identity,
    )
    assert rel.base_profile == github_account
    assert rel.target_identity == tmp_identity


# --- remove_temp_profile_identity_relation ---


@pytest.mark.django_db
def test_remove_temp_profile_identity_relation_removes_existing(
    github_account,
    tmp_identity,
):
    """remove_temp_profile_identity_relation deletes existing relation."""
    services.add_temp_profile_identity_relation(github_account, tmp_identity)
    services.remove_temp_profile_identity_relation(github_account, tmp_identity)
    assert not TempProfileIdentityRelation.objects.filter(
        base_profile=github_account,
        target_identity=tmp_identity,
    ).exists()


@pytest.mark.django_db
def test_remove_temp_profile_identity_relation_no_error_when_none(
    github_account,
    tmp_identity,
):
    """remove_temp_profile_identity_relation does not raise when relation missing."""
    services.remove_temp_profile_identity_relation(github_account, tmp_identity)
    # No exception; other relations unchanged
    assert TempProfileIdentityRelation.objects.count() == 0


@pytest.mark.django_db
def test_remove_temp_profile_identity_relation_leaves_others(
    make_github_account,
    make_tmp_identity,
):
    """remove_temp_profile_identity_relation only removes specified relation."""
    acc1 = make_github_account(github_account_id=111)
    acc2 = make_github_account(github_account_id=222)
    tmp1 = make_tmp_identity(display_name="T1")
    tmp2 = make_tmp_identity(display_name="T2")
    services.add_temp_profile_identity_relation(acc1, tmp1)
    services.add_temp_profile_identity_relation(acc2, tmp2)
    services.remove_temp_profile_identity_relation(acc1, tmp1)
    assert TempProfileIdentityRelation.objects.count() == 1
    assert TempProfileIdentityRelation.objects.filter(
        base_profile=acc2,
        target_identity=tmp2,
    ).exists()


# --- add_email ---


@pytest.mark.django_db
def test_add_email_creates_primary(github_account):
    """add_email creates email with is_primary=True."""
    email_obj = services.add_email(
        github_account,
        "primary@example.com",
        is_primary=True,
    )
    assert email_obj.email == "primary@example.com"
    assert email_obj.is_primary is True
    assert email_obj.base_profile_id == github_account.id


@pytest.mark.django_db
def test_add_email_creates_non_primary(github_account):
    """add_email creates email with is_primary=False."""
    email_obj = services.add_email(
        github_account,
        "other@example.com",
        is_primary=False,
    )
    assert email_obj.is_primary is False
    assert email_obj.is_active is True


@pytest.mark.django_db
def test_add_email_inactive(github_account):
    """add_email creates email with is_active=False."""
    email_obj = services.add_email(
        github_account,
        "inactive@example.com",
        is_active=False,
    )
    assert email_obj.is_active is False


# --- update_email ---


@pytest.mark.django_db
def test_update_email_changes_email(github_account):
    """update_email updates email field."""
    email_obj = services.add_email(github_account, "old@example.com")
    updated = services.update_email(email_obj, email="new@example.com")
    updated.refresh_from_db()
    assert updated.email == "new@example.com"


@pytest.mark.django_db
def test_update_email_changes_is_primary(github_account):
    """update_email updates is_primary."""
    email_obj = services.add_email(
        github_account,
        "e@example.com",
        is_primary=False,
    )
    services.update_email(email_obj, is_primary=True)
    email_obj.refresh_from_db()
    assert email_obj.is_primary is True


@pytest.mark.django_db
def test_update_email_changes_is_active(github_account):
    """update_email updates is_active."""
    email_obj = services.add_email(github_account, "e@example.com", is_active=True)
    services.update_email(email_obj, is_active=False)
    email_obj.refresh_from_db()
    assert email_obj.is_active is False


# --- remove_email ---


@pytest.mark.django_db
def test_remove_email_deletes_from_db(github_account):
    """remove_email deletes Email from database."""
    email_obj = services.add_email(github_account, "remove@example.com")
    pk = email_obj.pk
    services.remove_email(email_obj)
    assert not Email.objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_remove_email_other_emails_remain(github_account):
    """remove_email leaves other emails on same profile."""
    services.add_email(github_account, "keep@example.com")
    email2 = services.add_email(github_account, "remove@example.com")
    services.remove_email(email2)
    assert github_account.emails.filter(email="keep@example.com").exists()
    assert not github_account.emails.filter(email="remove@example.com").exists()


@pytest.mark.django_db
def test_remove_email_returns_none(github_account):
    """remove_email returns None (no return value)."""
    email_obj = services.add_email(github_account, "n@example.com")
    result = services.remove_email(email_obj)
    assert result is None


# --- get_or_create_github_account ---


@pytest.mark.django_db
def test_get_or_create_github_account_creates_new(identity):
    """get_or_create_github_account creates new account and returns (account, True)."""
    account, created = services.get_or_create_github_account(
        github_account_id=99999,
        username="newuser",
        display_name="New User",
        identity=identity,
    )
    assert created is True
    assert account.github_account_id == 99999
    assert account.username == "newuser"
    assert account.identity_id == identity.id


@pytest.mark.django_db
def test_get_or_create_github_account_gets_existing_and_updates(
    make_github_account,
    identity,
):
    """get_or_create_github_account returns existing and updates fields."""
    existing = make_github_account(
        identity=identity,
        github_account_id=77777,
        username="old",
        display_name="Old",
    )
    account, created = services.get_or_create_github_account(
        github_account_id=77777,
        username="newlogin",
        display_name="New Display",
    )
    assert created is False
    assert account.id == existing.id
    account.refresh_from_db()
    assert account.username == "newlogin"
    assert account.display_name == "New Display"


@pytest.mark.django_db
def test_get_or_create_github_account_with_account_type(identity):
    """get_or_create_github_account sets account_type ORGANIZATION."""
    account, created = services.get_or_create_github_account(
        github_account_id=88888,
        username="org",
        account_type=GitHubAccountType.ORGANIZATION,
        identity=identity,
    )
    assert created is True
    assert account.account_type == GitHubAccountType.ORGANIZATION


# --- get_github_account_by_username ---


@pytest.mark.django_db
def test_get_github_account_by_username_returns_account(github_account):
    """get_github_account_by_username returns the account when username exists."""
    result = services.get_github_account_by_username(github_account.username)
    assert result is not None
    assert result.id == github_account.id


@pytest.mark.django_db
def test_get_github_account_by_username_returns_none_when_missing():
    """get_github_account_by_username returns None when username is unknown."""
    assert services.get_github_account_by_username("no-such-user") is None


@pytest.mark.django_db
def test_get_github_account_by_username_empty_returns_none():
    """get_github_account_by_username returns None for blank username."""
    assert services.get_github_account_by_username("") is None
    assert services.get_github_account_by_username("   ") is None


# --- get_or_create_owner_account ---


@pytest.mark.django_db
def test_get_or_create_owner_account_returns_existing_by_username(
    github_account,
):
    """get_or_create_owner_account returns existing account when username matches."""

    class MockClient:
        def rest_request(self, path):
            return {}  # Should not be called

    client = MockClient()
    result = services.get_or_create_owner_account(client, github_account.username)
    assert result.id == github_account.id
    assert result.username == github_account.username


@pytest.mark.django_db
def test_get_or_create_owner_account_creates_from_api(identity):
    """get_or_create_owner_account creates account from API response when not in DB."""

    class MockClient:
        def rest_request(self, path):
            return {
                "id": 12345,
                "login": "apiuser",
                "name": "API User",
                "avatar_url": "https://avatar.url",
                "type": "User",
                "email": "api@example.com",
            }

    client = MockClient()
    account = services.get_or_create_owner_account(client, "apiuser")
    assert account.github_account_id == 12345
    assert account.username == "apiuser"
    assert account.display_name == "API User"
    assert account.account_type == GitHubAccountType.USER
    assert account.emails.filter(email="api@example.com").exists()


@pytest.mark.django_db
def test_get_or_create_owner_account_org_type(identity):
    """get_or_create_owner_account sets ORGANIZATION when API type is Organization."""

    class MockClient:
        def rest_request(self, path):
            return {
                "id": 999,
                "login": "myorg",
                "name": "My Org",
                "avatar_url": "",
                "type": "Organization",
                "email": None,
            }

    client = MockClient()
    account = services.get_or_create_owner_account(client, "myorg")
    assert account.account_type == GitHubAccountType.ORGANIZATION
    assert account.username == "myorg"


# --- _get_next_negative_github_account_id ---


@pytest.mark.django_db
def test_get_next_negative_github_account_id_first_returns_minus_one():
    """_get_next_negative_github_account_id returns -1 when no negative ids exist."""
    result = services._get_next_negative_github_account_id()
    assert result == -1


@pytest.mark.django_db
def test_get_next_negative_github_account_id_returns_minus_two_when_minus_one_exists(
    make_github_account,
):
    """_get_next_negative_github_account_id returns -2 when -1 exists."""
    make_github_account(github_account_id=-1)
    result = services._get_next_negative_github_account_id()
    assert result == -2


@pytest.mark.django_db
def test_get_next_negative_github_account_id_returns_next_when_several_exist(
    make_github_account,
):
    """_get_next_negative_github_account_id returns -3 when -1 and -2 exist."""
    make_github_account(github_account_id=-1)
    make_github_account(github_account_id=-2)
    result = services._get_next_negative_github_account_id()
    assert result == -3


# --- get_or_create_unknown_github_account ---


@pytest.mark.django_db
def test_get_or_create_unknown_github_account_creates_first():
    """get_or_create_unknown_github_account creates first unknown and returns (account, True)."""
    account, created = services.get_or_create_unknown_github_account(
        name="Unknown Dev",
        email="unknown@example.com",
    )
    assert created is True
    assert account.display_name == "Unknown Dev"
    assert account.github_account_id == -1
    assert account.emails.filter(email="unknown@example.com").exists()


@pytest.mark.django_db
def test_get_or_create_unknown_github_account_gets_existing():
    """get_or_create_unknown_github_account returns existing by display_name and (obj, False)."""
    services.get_or_create_unknown_github_account(name="Same Name")
    account2, created2 = services.get_or_create_unknown_github_account(name="Same Name")
    assert created2 is False
    assert (
        GitHubAccount.objects.filter(
            display_name="Same Name",
            github_account_id__lt=0,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_get_or_create_unknown_github_account_adds_email_to_existing():
    """get_or_create_unknown_github_account adds email to existing unknown account."""
    services.get_or_create_unknown_github_account(name="Unknown")
    account2, _ = services.get_or_create_unknown_github_account(
        name="Unknown",
        email="extra@example.com",
    )
    assert account2.emails.filter(email="extra@example.com").exists()


# --- get_or_create_mailing_list_profile ---


@pytest.mark.django_db
def test_get_or_create_mailing_list_profile_creates_new():
    """get_or_create_mailing_list_profile creates new profile and returns (profile, True)."""
    from cppa_user_tracker.models import MailingListProfile

    profile, created = services.get_or_create_mailing_list_profile(
        display_name="New Sender",
        email="sender@example.com",
    )
    assert created is True
    assert profile.display_name == "New Sender"
    assert profile.emails.filter(email="sender@example.com").exists()
    assert MailingListProfile.objects.filter(display_name="New Sender").count() == 1


@pytest.mark.django_db
def test_get_or_create_mailing_list_profile_gets_existing():
    """get_or_create_mailing_list_profile returns existing profile when display_name and email match."""
    services.get_or_create_mailing_list_profile(
        display_name="Existing",
        email="existing@example.com",
    )
    profile2, created2 = services.get_or_create_mailing_list_profile(
        display_name="Existing",
        email="existing@example.com",
    )
    assert created2 is False
    assert profile2.display_name == "Existing"
    assert profile2.emails.filter(email="existing@example.com").exists()


@pytest.mark.django_db
def test_get_or_create_mailing_list_profile_empty_display_name_raises():
    """get_or_create_mailing_list_profile raises ValueError for empty display_name."""
    with pytest.raises(ValueError, match="display_name must not be empty"):
        services.get_or_create_mailing_list_profile(
            display_name="", email="a@example.com"
        )
    with pytest.raises(ValueError, match="display_name must not be empty"):
        services.get_or_create_mailing_list_profile(
            display_name="   ", email="a@example.com"
        )


@pytest.mark.django_db
def test_get_or_create_mailing_list_profile_creates_without_email():
    """get_or_create_mailing_list_profile creates profile when email is empty (no email added)."""

    profile, created = services.get_or_create_mailing_list_profile(
        display_name="No Email Sender",
        email="",
    )
    assert created is True
    assert profile.display_name == "No Email Sender"
    assert profile.emails.count() == 0


@pytest.mark.django_db
def test_get_or_create_mailing_list_profile_strips_display_name_and_email():
    """get_or_create_mailing_list_profile strips whitespace from display_name and email."""
    profile, created = services.get_or_create_mailing_list_profile(
        display_name="  Trimmed  ",
        email="  trimmed@example.com  ",
    )
    assert created is True
    assert profile.display_name == "Trimmed"
    assert profile.emails.filter(email="trimmed@example.com").exists()


# --- get_mailing_list_profile_by_id / get_mailing_list_profiles_by_ids ---


@pytest.mark.django_db
def test_get_mailing_list_profile_by_id_returns_profile():
    """get_mailing_list_profile_by_id returns the profile when it exists."""
    profile, _ = services.get_or_create_mailing_list_profile(
        display_name="Lookup Me",
        email="lookup@example.com",
    )
    found = services.get_mailing_list_profile_by_id(profile.pk)
    assert found is not None
    assert found.pk == profile.pk
    assert found.display_name == "Lookup Me"


@pytest.mark.django_db
def test_get_mailing_list_profile_by_id_missing_or_invalid():
    """get_mailing_list_profile_by_id returns None for missing or invalid ids."""
    assert services.get_mailing_list_profile_by_id(999_999_999) is None
    assert services.get_mailing_list_profile_by_id(0) is None
    assert services.get_mailing_list_profile_by_id(-1) is None


@pytest.mark.django_db
def test_get_mailing_list_profiles_by_ids_bulk():
    """get_mailing_list_profiles_by_ids returns a map of existing profiles."""
    p1, _ = services.get_or_create_mailing_list_profile(
        display_name="Bulk One", email="one@example.com"
    )
    p2, _ = services.get_or_create_mailing_list_profile(
        display_name="Bulk Two", email="two@example.com"
    )
    result = services.get_mailing_list_profiles_by_ids(
        [p1.pk, p2.pk, 0, 999_999_999, p1.pk]
    )
    assert set(result.keys()) == {p1.pk, p2.pk}
    assert result[p1.pk].display_name == "Bulk One"
    assert result[p2.pk].display_name == "Bulk Two"


# --- get_or_create_wg21_paper_author_profile ---


@pytest.mark.django_db
def test_get_or_create_wg21_paper_author_profile_no_candidates_creates():
    """get_or_create_wg21_paper_author_profile creates new profile when none exist."""
    profile, created = services.get_or_create_wg21_paper_author_profile(
        display_name="New Author"
    )
    assert created is True
    assert profile.display_name == "New Author"
    assert WG21PaperAuthorProfile.objects.filter(display_name="New Author").count() == 1


@pytest.mark.django_db
def test_get_or_create_wg21_paper_author_profile_no_candidates_with_email_adds_email():
    """get_or_create_wg21_paper_author_profile adds email to new profile when provided."""
    profile, created = services.get_or_create_wg21_paper_author_profile(
        display_name="Author With Email",
        email="author@example.com",
    )
    assert created is True
    assert profile.emails.filter(email="author@example.com").exists()


@pytest.mark.django_db
def test_get_or_create_wg21_paper_author_profile_one_candidate_returns_it():
    """get_or_create_wg21_paper_author_profile returns existing profile when exactly one matches."""
    existing = WG21PaperAuthorProfile.objects.create(display_name="Solo Author")
    profile, created = services.get_or_create_wg21_paper_author_profile(
        display_name="Solo Author"
    )
    assert created is False
    assert profile.id == existing.id


@pytest.mark.django_db
def test_get_or_create_wg21_paper_author_profile_one_candidate_with_new_email_creates_new_profile():
    """One name match but email not on that profile: creates a new profile with the email.

    Disambiguation only returns an existing row when the email matches or when no email
    is passed and the candidate has no emails; otherwise a new profile is created.
    """
    existing = WG21PaperAuthorProfile.objects.create(display_name="Solo Author")
    profile, created = services.get_or_create_wg21_paper_author_profile(
        display_name="Solo Author",
        email="solo@example.com",
    )
    assert created is True
    assert profile.id != existing.id
    assert profile.display_name == "Solo Author"
    assert profile.emails.filter(email="solo@example.com").exists()
    assert (
        WG21PaperAuthorProfile.objects.filter(display_name="Solo Author").count() == 2
    )
    assert not existing.emails.filter(email="solo@example.com").exists()


@pytest.mark.django_db
def test_get_or_create_wg21_paper_author_profile_two_candidates_no_email_returns_first():
    """get_or_create_wg21_paper_author_profile returns first profile when multiple match and no email."""
    first = WG21PaperAuthorProfile.objects.create(display_name="Dup Name")
    _second = WG21PaperAuthorProfile.objects.create(display_name="Dup Name")
    profile, created = services.get_or_create_wg21_paper_author_profile(
        display_name="Dup Name"
    )
    assert created is False
    assert profile.id == first.id


@pytest.mark.django_db
def test_get_or_create_wg21_paper_author_profile_two_candidates_email_matches_second():
    """get_or_create_wg21_paper_author_profile returns profile with matching email when multiple match."""
    _first = WG21PaperAuthorProfile.objects.create(display_name="Same Name")
    second = WG21PaperAuthorProfile.objects.create(display_name="Same Name")
    services.add_email(second, "match@example.com", is_primary=True)
    profile, created = services.get_or_create_wg21_paper_author_profile(
        display_name="Same Name",
        email="match@example.com",
    )
    assert created is False
    assert profile.id == second.id


@pytest.mark.django_db
def test_get_or_create_wg21_paper_author_profile_two_candidates_email_matches_none_creates_new_profile():
    """When multiple match and email matches none, a new profile is created with that email."""
    first = WG21PaperAuthorProfile.objects.create(display_name="Other Name")
    second = WG21PaperAuthorProfile.objects.create(display_name="Other Name")
    services.add_email(second, "other@example.com", is_primary=True)
    profile, created = services.get_or_create_wg21_paper_author_profile(
        display_name="Other Name",
        email="nomatch@example.com",
    )
    assert created is True
    assert profile.id not in (first.id, second.id)
    assert profile.display_name == "Other Name"
    assert profile.emails.filter(email="nomatch@example.com").exists()


# --- get_or_create_slack_user ---


@pytest.mark.django_db
def test_get_or_create_slack_user_requires_id():
    """Reject payloads with no usable id (boundary validation or service check)."""
    with pytest.raises(SlackApiValidationError, match="Invalid Slack user"):
        services.get_or_create_slack_user({})
    with pytest.raises(ValueError, match="Slack user ID"):
        services.get_or_create_slack_user({"id": "   "})


@pytest.mark.django_db
def test_get_or_create_slack_user_updates_existing():
    """Existing SlackUser row gets username, display_name, avatar, optional email."""
    SlackUser.objects.create(
        slack_user_id="U123",
        username="old",
        display_name="Old Name",
        avatar_url="",
    )
    user, created = services.get_or_create_slack_user(
        {
            "id": "U123",
            "name": "newuser",
            "real_name": "Real New",
            "profile": {"image_72": "https://ava", "email": "slack@example.com"},
        }
    )
    assert created is False
    user.refresh_from_db()
    assert user.username == "newuser"
    assert user.display_name == "Real New"
    assert user.avatar_url == "https://ava"
    assert user.emails.filter(email="slack@example.com").exists()


# --- get_or_create_discord_profile ---


@pytest.mark.django_db
def test_get_or_create_discord_profile_updates_existing():
    """Updating paths merge username, display_name, avatar_url, is_bot."""
    DiscordProfile.objects.create(
        discord_user_id=999,
        username="u",
        display_name="d",
        avatar_url="",
        is_bot=False,
    )
    profile, created = services.get_or_create_discord_profile(
        999,
        username="newu",
        display_name="newd",
        avatar_url="http://img",
        is_bot=True,
    )
    assert created is False
    profile.refresh_from_db()
    assert profile.username == "newu"
    assert profile.display_name == "newd"
    assert profile.avatar_url == "http://img"
    assert profile.is_bot is True


# --- get_or_create_youtube_speaker ---


@pytest.mark.django_db
def test_get_or_create_youtube_speaker_requires_external_id():
    with pytest.raises(ValueError, match="external_id"):
        services.get_or_create_youtube_speaker("", display_name="x")
    with pytest.raises(ValueError, match="external_id"):
        services.get_or_create_youtube_speaker("   ", display_name="x")


@pytest.mark.django_db
def test_get_or_create_youtube_speaker_updates_display_name():
    YoutubeSpeaker.objects.create(external_id="yt1", display_name="Old Title")
    speaker, created = services.get_or_create_youtube_speaker(
        "yt1", display_name="New Title"
    )
    assert created is False
    speaker.refresh_from_db()
    assert speaker.display_name == "New Title"
