"""
Slack Fetcher: file download, user/channel info, huddle transcript.
Uses SlackAPIClient for API calls; huddle transcript uses workspace session credentials.
"""

import os
import re
import time
import urllib.parse
import logging

import requests
from requests.exceptions import RequestException, ConnectionError, Timeout

from core.operations.file_ops import sanitize_filename

from .client import SlackAPIClient
from .tokens import get_slack_client, get_default_team_key

logger = logging.getLogger(__name__)


class SlackFetcher:
    """Slack Fetcher: user/channel/file info via SlackAPIClient; file download and huddle transcript."""

    def __init__(self, bot_token=None):
        token = (bot_token or "").strip()
        if token:
            self._client = SlackAPIClient(token)
        else:
            self._client = get_slack_client()
        self.bot_token = self._client.token
        self.team_id = get_default_team_key() or None
        logger.debug("SlackFetcher initialized")

    def get_user_info(self, user_id):
        """Get user information from Slack API using bot token."""
        try:
            data = self._client.users_info(user_id)
            if data.get("ok"):
                user = data.get("user", {})
                return {
                    "id": user_id,
                    "name": user.get("name", ""),
                    "real_name": user.get("real_name", user.get("name", "")),
                    "display_name": user.get("profile", {}).get("display_name", "")
                    or user.get("real_name", user.get("name", "")),
                }
            return {
                "id": user_id,
                "name": user_id,
                "real_name": user_id,
                "display_name": user_id,
            }
        except Exception as e:
            logger.debug("Error getting user info for %s: %s", user_id, e)
            return {
                "id": user_id,
                "name": user_id,
                "real_name": user_id,
                "display_name": user_id,
            }

    def get_channel_info(self, channel_id):
        """Get channel information from Slack API using bot token."""
        try:
            data = self._client.conversations_info(channel_id)
            if data.get("ok"):
                channel = data.get("channel", {})
                return channel.get("name", channel_id)
            return channel_id
        except Exception as e:
            logger.debug("Error getting channel info for %s: %s", channel_id, e)
            return channel_id

    def get_file_info(self, file_id, max_retries=3, retry_delay=2):
        """Get file information by file ID with retry logic."""
        for attempt in range(max_retries):
            try:
                data = self._client.files_info(file_id)
                if data.get("ok"):
                    logger.debug("File info retrieved for %s", file_id)
                    return data
                error = data.get("error", "Unknown error")
                logger.warning("Failed to get file info: %s", error)
                return data
            except (ConnectionError, Timeout, RequestException) as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    logger.debug(
                        "Network error (attempt %s/%s): %s, retrying in %s s",
                        attempt + 1,
                        max_retries,
                        e,
                        wait_time,
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        "Error getting file info after %s attempts: %s", max_retries, e
                    )
                    return None
            except Exception as e:
                logger.exception("Error getting file info: %s", e)
                return None
        return None

    def download_file(
        self, file_url, save_path=None, filename=None, max_retries=3, retry_delay=2
    ):
        """Download a file from Slack with retry logic."""
        if save_path is None:
            save_path = os.getcwd()
        os.makedirs(save_path, exist_ok=True)
        headers = {"Authorization": f"Bearer {self.bot_token}"}
        for attempt in range(max_retries):
            try:
                logger.debug("Downloading file from: %s...", file_url[:50])
                with requests.get(
                    file_url,
                    headers=headers,
                    stream=True,
                    timeout=60,
                ) as response:
                    if response.status_code != 200:
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2**attempt)
                            time.sleep(wait_time)
                            continue
                        logger.error(
                            "Failed to download file: HTTP %s", response.status_code
                        )
                        return None
                    if filename is None:
                        content_disposition = response.headers.get(
                            "Content-Disposition", ""
                        )
                        if "filename*=" in content_disposition:
                            match = re.search(
                                r"filename\*=utf-8''(.+?)(?:;|$)",
                                content_disposition,
                                re.IGNORECASE,
                            )
                            filename = (
                                urllib.parse.unquote(match.group(1))
                                if match
                                else file_url.split("/")[-1].split("?")[0]
                            )
                        elif "filename=" in content_disposition:
                            filename = (
                                content_disposition.split("filename=")[1]
                                .split(";")[0]
                                .strip("\"'")
                            )
                        else:
                            filename = (
                                file_url.split("/")[-1].split("?")[0]
                                or "downloaded_file"
                            )
                    filename = sanitize_filename(filename)
                    file_path = os.path.join(save_path, filename)
                    with open(file_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                logger.debug("File downloaded: %s", file_path)
                return file_path
            except (ConnectionError, Timeout, RequestException) as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    time.sleep(wait_time)
                else:
                    logger.error("Download failed after retries: %s", e)
                    return None
            except Exception as e:
                logger.exception("Download error: %s", e)
                return None
        return None

    def get_file_and_download(self, file_id, save_path=None):
        """Get file info and download it in one call."""
        file_info = self.get_file_info(file_id)
        if not file_info or not file_info.get("ok"):
            return None, None
        file_data = file_info.get("file", {})
        download_url = file_data.get("url_private_download") or file_data.get(
            "url_private"
        )
        if not download_url:
            logger.warning("No download URL found in file info")
            return file_info, None
        filename = sanitize_filename(file_data.get("name", "downloaded_file"))
        downloaded_path = self.download_file(download_url, save_path, filename)
        return file_info, downloaded_path


def get_slack_fetcher(bot_token=None):
    """Get a SlackFetcher instance."""
    return SlackFetcher(bot_token)


def get_file_info(file_id, bot_token=None):
    """Get file information by file ID (standalone function)."""
    fetcher = SlackFetcher(bot_token)
    return fetcher.get_file_info(file_id)


def download_file(file_url, save_path=None, filename=None, bot_token=None):
    """Download a file from Slack (standalone function)."""
    fetcher = SlackFetcher(bot_token)
    return fetcher.download_file(file_url, save_path, filename)


def fetch_huddle_transcript(file_id):
    """
    Fetch huddle transcript/file info using session credentials from workspace JSON.

    Stale credentials are refreshed automatically. On auth errors, one refresh retry
    is attempted before giving up.
    """
    from slack_event_handler.utils.slack_internal_tokens_store import (
        SLACK_TOKENS_RELOGIN_HINT,
        _extract_validate_and_return,
        get_or_load_slack_internal_token_pair,
        log_slack_internal_tokens_still_invalid,
    )
    from slack_event_handler.utils.slack_tokens import (
        is_slack_internal_token_auth_error,
    )

    team_id = get_default_team_key() or None
    pair = get_or_load_slack_internal_token_pair(team_id)
    if not pair:
        if team_id:
            logger.error(
                "Cannot fetch huddle transcript for file %s: no valid session "
                "credentials for team %s. %s",
                file_id,
                team_id,
                SLACK_TOKENS_RELOGIN_HINT,
            )
        else:
            logger.error(
                "Cannot fetch huddle transcript for file %s: no Slack team id "
                "(set SLACK_TEAM_IDS) and no valid session credentials. %s",
                file_id,
                SLACK_TOKENS_RELOGIN_HINT,
            )
        return None

    xoxc_token, xoxd_token = pair
    url = "https://slack.com/api/files.info"
    headers = {"Authorization": f"Bearer {xoxc_token}"}
    cookies = {"d": xoxd_token}
    data = {"file": file_id, "include_transcription": "true"}
    max_retries, retry_delay = 3, 2
    reextracted = False
    for attempt in range(max_retries):
        try:
            response = requests.post(
                url, headers=headers, cookies=cookies, data=data, timeout=30
            )
            response.raise_for_status()
            result = response.json()
            if result.get("ok"):
                logger.debug("Fetched file info for: %s", file_id)
                return result
            err = (result.get("error") or "").strip()
            if team_id and is_slack_internal_token_auth_error(err) and not reextracted:
                reextracted = True
                logger.info(
                    "Slack auth error (%s); refreshing session credentials",
                    err,
                )
                new_pair = _extract_validate_and_return(team_id)
                if new_pair:
                    xoxc_token, xoxd_token = new_pair
                    headers = {"Authorization": f"Bearer {xoxc_token}"}
                    cookies = {"d": xoxd_token}
                    continue
                logger.error(
                    "Cannot fetch huddle transcript for file %s: credential refresh did not "
                    "yield valid session for team %s. %s",
                    file_id,
                    team_id,
                    SLACK_TOKENS_RELOGIN_HINT,
                )
                return None
            if reextracted and team_id and is_slack_internal_token_auth_error(err):
                log_slack_internal_tokens_still_invalid(team_id)
                logger.error(
                    "Cannot fetch huddle transcript for file %s: Slack auth error (%s) "
                    "after credential refresh. %s",
                    file_id,
                    err,
                    SLACK_TOKENS_RELOGIN_HINT,
                )
                return result
            logger.warning("Slack API error: %s", err or "Unknown error")
            return result
        except (ConnectionError, Timeout, RequestException) as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2**attempt))
            else:
                logger.exception("Slack API request error: %s", e)
                return None
        except Exception as e:
            logger.exception("Unexpected error: %s", e)
            return None
    return None
