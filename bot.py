import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

TWITCH_CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
TWITCH_CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]

TWITCH_CHANNEL = "binmino"
STATE_FILE = "state.json"


def request_json(url, method="GET", data=None, headers=None):
    req = urllib.request.Request(
        url,
        data=data,
        headers=headers or {},
        method=method
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_twitch_token():
    data = urllib.parse.urlencode({
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }).encode()

    result = request_json(
        "https://id.twitch.tv/oauth2/token",
        method="POST",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    return result["access_token"]


def twitch_get(path, token):
    return request_json(
        "https://api.twitch.tv/helix/" + path,
        headers={
            "Client-Id": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}"
        }
    )


def get_broadcaster(token):
    result = twitch_get(
        "users?login=" + urllib.parse.quote(TWITCH_CHANNEL),
        token
    )

    if not result["data"]:
        raise RuntimeError(
            f"Twitch-Kanal '{TWITCH_CHANNEL}' wurde nicht gefunden."
        )

    return result["data"][0]


def send_to_discord(clip):
    payload = {
        "username": "Twitch Clips",
        "embeds": [
            {
                "title": "🎬 Neuer Twitch-Clip!",
                "description": f"**{clip['title']}**",
                "url": clip["url"],
                "fields": [
                    {
                        "name": "Kanal",
                        "value": clip["broadcaster_name"],
                        "inline": True
                    },
                    {
                        "name": "Clip erstellt von",
                        "value": clip["creator_name"],
                        "inline": True
                    }
                ],
                "thumbnail": {
                    "url": clip["thumbnail_url"]
                }
            }
        ]
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status not in (200, 204):
            raise RuntimeError(
                f"Discord antwortete mit HTTP {response.status}"
            )


def load_state():
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_state(timestamp):
    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(
            {"last_check": timestamp},
            file,
            indent=2
        )


def main():
    print("Twitch → Discord Bot startet...")

    token = get_twitch_token()
    broadcaster = get_broadcaster(token)

    broadcaster_id = broadcaster["id"]

    state = load_state()

    now = datetime.now(timezone.utc)

    # Beim allerersten Start werden vorhandene alte Clips
    # NICHT nachträglich auf Discord gepostet.
    if state is None:
        save_state(now.isoformat())
        print("Erster Start: vorhandene Clips werden übersprungen.")
        return

    last_check = datetime.fromisoformat(state["last_check"])

    # Kleiner Puffer gegen Zeitunterschiede.
    start_time = last_check - timedelta(seconds=30)

    params = urllib.parse.urlencode({
        "broadcaster_id": broadcaster_id,
        "started_at": start_time.isoformat().replace("+00:00", "Z"),
        "ended_at": now.isoformat().replace("+00:00", "Z"),
        "first": 100
    })

    result = twitch_get(
        "clips?" + params,
        token
    )

    clips = result.get("data", [])

    # Älteste zuerst posten.
    clips.sort(key=lambda clip: clip["created_at"])

    sent = 0

    for clip in clips:
        created_at = datetime.fromisoformat(
            clip["created_at"].replace("Z", "+00:00")
        )

        if created_at <= last_check:
            continue

        print(f"Neuer Clip: {clip['url']}")

        send_to_discord(clip)
        sent += 1

    save_state(now.isoformat())

    print(f"Fertig. {sent} neue Clips gepostet.")


if __name__ == "__main__":
    main()
