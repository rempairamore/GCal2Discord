"""
GCal2Discord - Google Calendar to Discord Sync Bot

Synchronizes events from a Google Calendar to a Discord server, creating
scheduled voice channel meetings.
"""

import asyncio
import datetime
import json
import logging
import os
import traceback
from logging.handlers import RotatingFileHandler
from typing import Any, Optional

import google.auth
import requests
from discord import Intents
from discord.ext import commands, tasks
from googleapiclient.discovery import build

import var

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYNCED_EVENTS_FILE = "synced_events.json"
EVENT_LOG_FILE = "event.log"
LOG_SIZE_LIMIT = 200 * 1024 * 1024  # 200 MB
LOG_BACKUP_COUNT = 5

DISCORD_API_BASE = "https://discord.com/api/v9"
HTTP_TIMEOUT = 30  # seconds
RATE_LIMIT_PAUSE = 2  # seconds between Discord API calls

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logger = logging.getLogger("gcal2discord")
logger.setLevel(logging.INFO)

_file_handler = RotatingFileHandler(
    EVENT_LOG_FILE,
    maxBytes=LOG_SIZE_LIMIT,
    backupCount=LOG_BACKUP_COUNT,
    encoding="utf-8",
)
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
)
logger.addHandler(_file_handler)

# Also log to stdout so systemd/journalctl can capture it
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
)
logger.addHandler(_stream_handler)


# ---------------------------------------------------------------------------
# Persistence of synced events
# ---------------------------------------------------------------------------

def load_synced_events() -> dict:
    """Load the list of previously synchronized events from disk."""
    if os.path.exists(SYNCED_EVENTS_FILE):
        try:
            with open(SYNCED_EVENTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s: %s. Starting fresh.", SYNCED_EVENTS_FILE, exc)
    return {"events": []}


def save_synced_events(synced_events: dict) -> None:
    """Persist the list of synchronized events to disk."""
    tmp_path = SYNCED_EVENTS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(synced_events, f, indent=4)
    os.replace(tmp_path, SYNCED_EVENTS_FILE)  # atomic on POSIX


# ---------------------------------------------------------------------------
# Google Calendar helpers (synchronous, run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def get_google_calendar_service():
    """Build and return an authenticated Google Calendar API service."""
    credentials, _ = google.auth.load_credentials_from_file(var.GOOGLE_CREDENTIALS_JSON)
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def fetch_upcoming_events() -> list[dict]:
    """Fetch upcoming events from Google Calendar within the configured window."""
    logger.info("Requesting events from Google Calendar for the next %d days.", var.DAYS_IN_FUTURE)
    service = get_google_calendar_service()

    now = datetime.datetime.utcnow()
    time_min = now.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    time_max = (now + datetime.timedelta(days=var.DAYS_IN_FUTURE)).strftime("%Y-%m-%dT%H:%M:%S") + "Z"

    events_result = (
        service.events()
        .list(
            calendarId=var.GOOGLE_CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=100,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return events_result.get("items", [])


def filter_events_by_whitelist(events: list[dict]) -> list[dict]:
    """Keep only events whose title contains at least one whitelist term.

    If the whitelist is empty (or not defined in var.py), return events unchanged.
    Matching is case-insensitive and looks for a substring in the event summary.
    """
    whitelist = [term.lower() for term in getattr(var, "TITLE_WHITELIST", []) if term]
    if not whitelist:
        return events

    filtered = []
    for event in events:
        title = (event.get("summary") or "").lower()
        if any(term in title for term in whitelist):
            filtered.append(event)

    logger.info(
        "Whitelist active (%d term(s)): kept %d/%d events.",
        len(whitelist), len(filtered), len(events),
    )
    return filtered


# ---------------------------------------------------------------------------
# Discord API helpers (synchronous, run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _discord_headers(json_body: bool = False) -> dict:
    headers = {"Authorization": f"Bot {var.DISCORD_BOT_TOKEN}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def fetch_discord_events() -> list[dict]:
    """Fetch existing scheduled events from the Discord server."""
    logger.info("Requesting scheduled events from Discord.")
    url = f"{DISCORD_API_BASE}/guilds/{var.DISCORD_GUILD_ID}/scheduled-events"
    try:
        response = requests.get(url, headers=_discord_headers(), timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Network error while fetching Discord events: %s", exc)
        return []

    if response.status_code == 200:
        return response.json()

    logger.error("Failed to fetch Discord events (%s): %s", response.status_code, response.text)
    return []


def discord_event_exists(event_id: str) -> Optional[bool]:
    """Verify whether a specific Discord scheduled event still exists.

    Returns:
        True  -> confirmed present on Discord
        False -> confirmed gone (404)
        None  -> could not determine (network or unexpected error)

    Used to avoid duplicate creations when the list endpoint omits an event
    (e.g. transient API hiccup, or event transitioning to ACTIVE state).
    """
    url = f"{DISCORD_API_BASE}/guilds/{var.DISCORD_GUILD_ID}/scheduled-events/{event_id}"
    try:
        response = requests.get(url, headers=_discord_headers(), timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Network error while verifying Discord event %s: %s", event_id, exc)
        return None

    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False

    logger.error(
        "Unexpected status while verifying event %s (%s): %s",
        event_id, response.status_code, response.text,
    )
    return None


def _build_event_payload(event: dict) -> dict:
    """Translate a Google Calendar event into the Discord scheduled-event payload."""
    start_time = event["start"].get("dateTime", event["start"].get("date"))
    end_time = event["end"].get("dateTime", event["end"].get("date"))

    # All-day events use plain dates; Discord requires a full ISO timestamp.
    if "date" in event["start"]:
        start_time += "T00:00:00Z"
        end_time += "T23:59:59Z"

    return {
        "name": event["summary"],
        "description": event.get("description", ""),
        "scheduled_start_time": start_time,
        "scheduled_end_time": end_time,
        "privacy_level": 2,
        "entity_type": 2,
        "channel_id": var.DISCORD_CHANNEL_ID,
    }


def create_or_update_discord_event(
    event: dict, discord_event_id: Optional[str] = None
) -> Optional[str]:
    """Create or update a scheduled event on Discord. Returns the Discord event ID."""
    if discord_event_id is None:
        url = f"{DISCORD_API_BASE}/guilds/{var.DISCORD_GUILD_ID}/scheduled-events"
        method = requests.post
        action_verb = "create"
    else:
        url = f"{DISCORD_API_BASE}/guilds/{var.DISCORD_GUILD_ID}/scheduled-events/{discord_event_id}"
        method = requests.patch
        action_verb = "update"

    payload = _build_event_payload(event)

    try:
        response = method(url, json=payload, headers=_discord_headers(json_body=True), timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Network error while trying to %s event '%s': %s", action_verb, event.get("summary"), exc)
        return None

    if response.status_code in (200, 201):
        logger.info("Event '%s' %sd on Discord.", event["summary"], action_verb)
        return response.json().get("id")

    logger.error(
        "Failed to %s event '%s' on Discord (%s): %s",
        action_verb, event.get("summary"), response.status_code, response.text,
    )
    return None


def delete_discord_event(event_id: str) -> bool:
    """Delete a scheduled event from Discord. Returns True on success."""
    url = f"{DISCORD_API_BASE}/guilds/{var.DISCORD_GUILD_ID}/scheduled-events/{event_id}"
    try:
        response = requests.delete(url, headers=_discord_headers(), timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        logger.error("Network error while deleting Discord event %s: %s", event_id, exc)
        return False

    if response.status_code == 204:
        logger.info("Event %s deleted from Discord.", event_id)
        return True

    # 404 means it's already gone — treat as success so we clean up our state.
    if response.status_code == 404:
        logger.info("Event %s was already missing on Discord; cleaning up local state.", event_id)
        return True

    logger.error(
        "Failed to delete event %s from Discord (%s): %s",
        event_id, response.status_code, response.text,
    )
    return False


# ---------------------------------------------------------------------------
# Discord bot setup
# ---------------------------------------------------------------------------

intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

synced_events: dict = load_synced_events()


def _find_synced_entry(google_event_id: str) -> Optional[dict]:
    """Return the local sync record for a given Google event ID, or None."""
    for entry in synced_events["events"]:
        if entry["google_event_id"] == google_event_id:
            return entry
    return None


def _event_summary(event: dict) -> dict:
    """Compact representation of an event kept alongside the sync record."""
    return {
        "date": event["start"].get("dateTime", event["start"].get("date")),
        "title": event["summary"],
        "channel": var.DISCORD_CHANNEL_ID,
        "notes": event.get("description", ""),
    }


async def _sync_single_event(event: dict, discord_event_ids: set[str]) -> None:
    """Handle one Google Calendar event: create, update, or recreate on Discord."""
    google_id = event["id"]
    entry = _find_synced_entry(google_id)

    if entry is None:
        # Never seen before → create on Discord
        new_id = await asyncio.to_thread(create_or_update_discord_event, event)
        if new_id:
            synced_events["events"].append(
                {"google_event_id": google_id, "discord_event_id": new_id, **_event_summary(event)}
            )
            save_synced_events(synced_events)
        return

    discord_id = entry["discord_event_id"]
    if discord_id not in discord_event_ids:
        # Discord's list endpoint says it's gone — but verify directly before
        # recreating, otherwise transient API hiccups (or events transitioning
        # to ACTIVE state) silently produce duplicates.
        await asyncio.sleep(RATE_LIMIT_PAUSE)
        exists = await asyncio.to_thread(discord_event_exists, discord_id)

        if exists is True:
            logger.info(
                "Event '%s' was reported missing but actually exists; updating instead.",
                event["summary"],
            )
            updated_id = await asyncio.to_thread(create_or_update_discord_event, event, discord_id)
            if updated_id:
                entry.update(_event_summary(event))
                save_synced_events(synced_events)
        elif exists is False:
            logger.info("Event '%s' is missing on Discord, recreating.", event["summary"])
            new_id = await asyncio.to_thread(create_or_update_discord_event, event)
            if new_id:
                entry["discord_event_id"] = new_id
                entry.update(_event_summary(event))
                save_synced_events(synced_events)
        else:
            logger.warning(
                "Could not verify status of event '%s'; skipping this cycle to avoid duplicates.",
                event["summary"],
            )
    else:
        # It still exists on Discord → update in place
        updated_id = await asyncio.to_thread(create_or_update_discord_event, event, discord_id)
        if updated_id:
            entry.update(_event_summary(event))
            save_synced_events(synced_events)


async def _cleanup_removed_events(google_event_ids: set[str]) -> None:
    """Delete Discord events whose source has disappeared from Google Calendar."""
    for entry in list(synced_events["events"]):
        if entry["google_event_id"] in google_event_ids:
            continue

        await asyncio.sleep(RATE_LIMIT_PAUSE)
        success = await asyncio.to_thread(delete_discord_event, entry["discord_event_id"])
        if success:
            synced_events["events"].remove(entry)
            save_synced_events(synced_events)


@tasks.loop(seconds=var.SYNC_INTERVAL)
async def sync_events_loop() -> None:
    """Periodically reconcile Google Calendar events with Discord scheduled events."""
    try:
        google_events = await asyncio.to_thread(fetch_upcoming_events)
        google_events = filter_events_by_whitelist(google_events)
        discord_events = await asyncio.to_thread(fetch_discord_events)
        discord_event_ids = {e["id"] for e in discord_events}

        for event in google_events:
            await asyncio.sleep(RATE_LIMIT_PAUSE)
            await _sync_single_event(event, discord_event_ids)

        google_event_ids = {e["id"] for e in google_events}
        await _cleanup_removed_events(google_event_ids)

    except Exception as exc:
        logger.error("Error in sync_events_loop: %s\n%s", exc, traceback.format_exc())


@sync_events_loop.before_loop
async def _before_sync_loop() -> None:
    # Make sure the bot is fully connected before the first sync cycle.
    await bot.wait_until_ready()


@bot.event
async def on_ready() -> None:
    logger.info("Bot logged in as %s (id=%s).", bot.user, bot.user.id if bot.user else "?")
    if not sync_events_loop.is_running():
        sync_events_loop.start()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        bot.run(var.DISCORD_BOT_TOKEN, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")
    except Exception as exc:
        logger.critical("Bot crashed: %s\n%s", exc, traceback.format_exc())
        raise


if __name__ == "__main__":
    main()