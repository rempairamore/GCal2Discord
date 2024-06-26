# Google Calendar to Discord Sync Bot

This bot syncs events from a Google Calendar to a Discord server. It periodically checks for new events, updates existing ones, and ensures events deleted from Discord are recreated if they still exist in Google Calendar. Google Calendar has authoritative control over the events.

## Features

- Sync events from Google Calendar to Discord.
- Creates, updates, and deletes events based on Google Calendar changes.
- Ensures events deleted from Discord are recreated if they still exist in Google Calendar.
- Logs all operations to `event.log` and compresses the log if it exceeds 200 MB.

## Prerequisites

- Python 3.7+
- Google Calendar API credentials
- Discord bot token

## Setup

### Clone the repository:

```bash
git clone https://github.com/rempairamore/GCal2Discord.git
cd GCal2Discord
```

Install the required packages:

```bash

pip install -r requirements.txt
```

## Setting Up Google Calendar API

1. **Go to the [Google Cloud Console](https://console.cloud.google.com/)**

2. **Create a new project:**
    - Click on the project dropdown at the top of the page.
    - Click "New Project."
    - Enter a name for your project and click "Create."

3. **Enable the Google Calendar API:**
    - In the project dashboard, click on "Enable APIs and Services."
    - Search for "Google Calendar API" and click on it.
    - Click "Enable."

4. **Create credentials for the API:**
    - Go to the "Credentials" tab on the left sidebar.
    - Click "Create Credentials" and select "Service Account."
    - Enter a name for the service account and click "Create."
    - Assign a role to the service account (e.g., "Editor") and click "Continue."
    - Click "Done."

5. **Create a key for the service account:**
    - In the "Credentials" tab, click on the service account you created.
    - Go to the "Keys" section and click "Add Key" > "Create new key."
    - Select "JSON" and click "Create." A JSON file will be downloaded to your computer.

6. **Share your Google Calendar with the service account:**
    - Open Google Calendar.
    - Go to the "Settings and sharing" of the calendar you want to sync.
    - In the "Share with specific people" section, add the service account's email address (found in the JSON file) and provide appropriate permissions (e.g., "Make changes to events").

7. **Save the JSON credentials file:**
    - Save the JSON file in your project directory and update the `GOOGLE_CREDENTIALS_JSON` path in `var.py`.


## Obtaining Discord IDs and Token

To configure the bot, you'll need the Discord bot token, the guild ID (server ID), and the channel ID where the bot will post the events. Here’s how you can obtain them:
1. **Create a Discord Bot**

   - Go to the Discord Developer Portal.
   - Click on "New Application" and give it a name.
   - Go to the "Bot" tab on the left sidebar and click "Add Bot".
   - Click "Yes, do it!" to confirm.
   - Under the "TOKEN" section, click "Copy" to copy your bot token. Save this token as you'll need it for the DISCORD_BOT_TOKEN variable in var.py.

2. **Get Your Guild ID**

    Enable Developer Mode in Discord:
       - Go to your Discord app.
       - Click on the gear icon (User Settings) next to your username.
       - Go to "Advanced" and enable "Developer Mode".
    Right-click on your server icon in Discord and click "Copy ID". Save this ID as you'll need it for the DISCORD_GUILD_ID variable in var.py.

3. **Get Your Channel ID**

    In Discord, right-click on the channel where you want the bot to post events and click "Copy ID". Save this ID as you'll need it for the DISCORD_CHANNEL_ID variable in var.py.


### Create the var.py file:

You can find a *var.py_example* file in the project. Simply modify this file with your credentials and rename it to var.py:

```bash
mv var.py_example var.py
```

Populate it with your credentials and configuration:

```python
# var.py
GOOGLE_CREDENTIALS_JSON = 'path/to/your/google-credentials.json'
GOOGLE_CALENDAR_ID = 'your-google-calendar-id'
DISCORD_BOT_TOKEN = 'your-discord-bot-token'
DISCORD_GUILD_ID = 'your-discord-guild-id'
DISCORD_CHANNEL_ID = 'your-discord-channel-id'  # ID of the voice channel where the meetings will be held
SYNC_INTERVAL = 300  # Interval in seconds to sync events (5 minutes)
DAYS_IN_FUTURE = 10  # Number of days in the future to fetch events
```


## Running the Bot

1. **Run the bot:**

    ```bash
    python main.py
    ```

## Logging

The bot logs all its operations to `event.log`. If the log file exceeds 200 MB, it will be compressed into a `.tar.gz` file and a new log file will be started.

## Running as a systemd Service

To run the bot as a systemd service, follow these steps:

1. **Create a systemd service file:**

    Create a file named `google-calendar-discord-bot.service` in the `/etc/systemd/system/` directory with the following content:

    ```ini
    [Unit]
    Description=Google Calendar to Discord Sync Bot
    After=network.target

    [Service]
    User=yourusername
    WorkingDirectory=/path/to/your/project
    ExecStart=/path/to/your/project/venv/bin/python /path/to/your/project/main.py
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

    Replace `yourusername` with your system username and `/path/to/your/project` with the path to your project directory.

2. **Reload systemd and start the service:**

    ```bash
    sudo systemctl daemon-reload
    sudo systemctl start google-calendar-discord-bot
    ```

3. **Enable the service to start on boot:**

    ```bash
    sudo systemctl enable google-calendar-discord-bot
    ```


## License

This project is licensed under the Creative Commons Attribution (CC BY 4.0) license.

