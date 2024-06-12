import datetime
import requests
import google.auth
from googleapiclient.discovery import build
from discord import Intents
from discord.ext import tasks, commands
import var
import asyncio
import json
import os
import tarfile
import time

# Path to the file that stores synchronized events
SYNCED_EVENTS_FILE = 'synced_events.json'
EVENT_LOG_FILE = 'event.log'
LOG_SIZE_LIMIT = 200 * 1024 * 1024  # 200 MB

# Load synchronized events from file
def load_synced_events():
    if os.path.exists(SYNCED_EVENTS_FILE):
        with open(SYNCED_EVENTS_FILE, 'r') as f:
            return json.load(f)
    return {"events": []}

# Save synchronized events to file
def save_synced_events(synced_events):
    with open(SYNCED_EVENTS_FILE, 'w') as f:
        json.dump(synced_events, f, indent=4)

# Log an event
def log_event(message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"{timestamp} {message}\n"
    with open(EVENT_LOG_FILE, 'a') as log_file:
        log_file.write(log_message)
    check_log_size()

# Check the size of the log file and compress if needed
def check_log_size():
    if os.path.exists(EVENT_LOG_FILE) and os.path.getsize(EVENT_LOG_FILE) > LOG_SIZE_LIMIT:
        timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        tar_filename = f"{timestamp}.tar.gz"
        with tarfile.open(tar_filename, "w:gz") as tar:
            tar.add(EVENT_LOG_FILE)
        os.remove(EVENT_LOG_FILE)
        log_event(f"Log file compressed to {tar_filename} and reset.")

# Set up Google Calendar API
def get_google_calendar_service():
    credentials, _ = google.auth.load_credentials_from_file(var.GOOGLE_CREDENTIALS_JSON)
    service = build('calendar', 'v3', credentials=credentials)
    return service

# Fetch upcoming events from Google Calendar
def get_upcoming_events(service):
    log_event(f"Requesting events from Google Calendar for the next {var.DAYS_IN_FUTURE} days.")
    now = datetime.datetime.utcnow()
    time_min = now.strftime('%Y-%m-%dT%H:%M:%S') + 'Z'
    time_max = (now + datetime.timedelta(days=var.DAYS_IN_FUTURE)).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

    events_result = service.events().list(
        calendarId=var.GOOGLE_CALENDAR_ID, timeMin=time_min, timeMax=time_max,
        maxResults=100, singleEvents=True,
        orderBy='startTime').execute()
    return events_result.get('items', [])

# Fetch existing Discord events
def get_discord_events():
    log_event("Requesting events from Discord.")
    url = f"https://discord.com/api/v9/guilds/{var.DISCORD_GUILD_ID}/scheduled-events"
    headers = {
        "Authorization": f"Bot {var.DISCORD_BOT_TOKEN}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        log_event(f"Failed to fetch Discord events: {response.content}")
        return []

# Create or update Discord event
def create_or_update_discord_event(event, discord_event_id=None):
    url = f"https://discord.com/api/v9/guilds/{var.DISCORD_GUILD_ID}/scheduled-events"
    method = requests.post if discord_event_id is None else requests.patch

    headers = {
        "Authorization": f"Bot {var.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    start_time = event['start'].get('dateTime', event['start'].get('date'))
    end_time = event['end'].get('dateTime', event['end'].get('date'))

    if 'date' in event['start']:
        start_time += 'T00:00:00Z'
        end_time += 'T23:59:59Z'

    data = {
        "name": event['summary'],
        "description": event.get('description', ''),
        "scheduled_start_time": start_time,
        "scheduled_end_time": end_time,
        "privacy_level": 2,
        "entity_type": 2,
        "channel_id": var.DISCORD_CHANNEL_ID,
    }

    response = method(url, json=data, headers=headers)
    time.sleep(2)
    if response.status_code in (200, 201):
        log_event(f"Event {event['summary']} {'updated' if discord_event_id else 'created'} on Discord")
        return response.json().get('id')
    else:
        log_event(f"Failed to {'update' if discord_event_id else 'create'} event {event['summary']} on Discord: {response.content}")
        return None

# Delete Discord event
def delete_discord_event(event_id):
    url = f"https://discord.com/api/v9/guilds/{var.DISCORD_GUILD_ID}/scheduled-events/{event_id}"
    headers = {
        "Authorization": f"Bot {var.DISCORD_BOT_TOKEN}"
    }
    response = requests.delete(url, headers=headers)
    time.sleep(2)
    if response.status_code == 204:
        log_event(f"Event {event_id} deleted from Discord")
    else:
        log_event(f"Failed to delete event {event_id} from Discord: {response.content}")

# Set up Discord bot
intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

synced_events = load_synced_events()

@bot.event
async def on_ready():
    log_event("Bot logged in and ready.")
    sync_events_loop.start()

@tasks.loop(seconds=var.SYNC_INTERVAL)
async def sync_events_loop():
    try:
        service = get_google_calendar_service()
        events = get_upcoming_events(service)
        discord_events = get_discord_events()
        global synced_events

        # Create a set of current Discord event IDs for quick lookup
        discord_event_ids = {event['id'] for event in discord_events}

        for event in events:
            time.sleep(2)
            event_id = event['id']
            event_data = {
                "date": event['start'].get('dateTime', event['start'].get('date')),
                "title": event['summary'],
                "channel": var.DISCORD_CHANNEL_ID,
                "notes": event.get('description', '')
            }

            if any(e["google_event_id"] == event_id for e in synced_events["events"]):
                for synced_event in synced_events["events"]:
                    if synced_event["google_event_id"] == event_id:
                        discord_event_id = synced_event["discord_event_id"]
                        if discord_event_id not in discord_event_ids:
                            log_event(f"Event {event['summary']} is missing on Discord, recreating")
                            discord_event_id = create_or_update_discord_event(event, discord_event_id)
                            if discord_event_id:
                                synced_event["discord_event_id"] = discord_event_id
                                synced_event.update(event_data)
                                save_synced_events(synced_events)
                        break
            else:
                discord_event_id = create_or_update_discord_event(event)
                if discord_event_id:
                    synced_events["events"].append({
                        "google_event_id": event_id,
                        "discord_event_id": discord_event_id,
                        **event_data
                    })
                    save_synced_events(synced_events)

        # Remove events from synced_events if they no longer exist in Google Calendar
        google_event_ids = {event['id'] for event in events}
        for synced_event in list(synced_events["events"]):
            time.sleep(2)
            if synced_event["google_event_id"] not in google_event_ids:
                delete_discord_event(synced_event["discord_event_id"])
                synced_events["events"].remove(synced_event)
                save_synced_events(synced_events)

    except Exception as e:
        log_event(f"Error in sync_events_loop: {e}")

bot.run(var.DISCORD_BOT_TOKEN)