import requests
import time
import threading
import json
import math
from datetime import datetime, timezone
from flask import Flask, jsonify, send_from_directory

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1484331891116212424/_cXCA6KAWa8Ysi9we_PZRSCpmXL6UoPLDqkFvfRahL64tKLMSptcxv0GeHC7Ej7v2Alv"

# TruckersMP player IDs or usernames to track
FAHRER_LISTE = ["5810271", "Gruckenwasserimglas", "4611616"]

# How often the bot polls TruckersMP and posts to Discord (seconds)
POLL_INTERVAL = 30

# ---------------------------------------------------------------------------
# Shared state — written by the bot thread, read by the Flask thread
# ---------------------------------------------------------------------------

driver_state: dict[str, dict] = {}   # keyed by player identifier
state_lock = threading.Lock()

# ---------------------------------------------------------------------------
# TruckersMP API helpers
# ---------------------------------------------------------------------------

TRUCKERSMP_API = "https://api.truckersmp.com/v2"


def fetch_player(identifier: str) -> dict | None:
    """Fetch a single player from the TruckersMP API.

    The identifier can be a numeric player ID or a username string.
    Returns the parsed JSON dict on success, or None on any error.
    """
    url = f"{TRUCKERSMP_API}/player/{identifier}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # The API wraps the payload in {"error": false, "response": {...}}
        if not data.get("error") and "response" in data:
            return data["response"]
    except Exception as exc:
        print(f"[API] Error fetching player {identifier!r}: {exc}")
    return None


def build_static_map_url(lat: float, lon: float, zoom: int = 7) -> str:
    """Return an OpenStreetMap static-image URL centred on the given coords.

    Uses the free staticmap.openstreetmap.de service — no API key required.
    The red marker pin is placed at the driver's exact position.
    """
    base = "https://staticmap.openstreetmap.de/staticmap.php"
    return (
        f"{base}?center={lat},{lon}&zoom={zoom}&size=600x300"
        f"&markers={lat},{lon},red-pushpin"
    )


def build_embed(player: dict, online: bool) -> dict:
    """Build a Discord embed dict for a single driver."""
    name = player.get("name", "Unknown")
    mpid = player.get("id", "?")
    avatar_url = player.get("avatar", "")

    # Location data lives inside player["patreon"] on some API versions;
    # the primary location fields are at the top level when the player is
    # currently in-game.
    lat = player.get("latitude") or player.get("lat")
    lon = player.get("longitude") or player.get("lon")
    server = player.get("server", {})
    server_name = server.get("name", "—") if isinstance(server, dict) else str(server)

    if online and lat is not None and lon is not None:
        colour = 0x2ECC71          # green
        status_text = "🟢 Online"
        location_text = f"`{lat:.4f}, {lon:.4f}`"
        map_url = build_static_map_url(lat, lon)
        image_block = {"url": map_url}
    else:
        colour = 0xE74C3C          # red
        status_text = "🔴 Offline"
        location_text = "—"
        image_block = None

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    embed: dict = {
        "title": f"🚛 {name}",
        "url": f"https://truckersmp.com/user/{mpid}",
        "color": colour,
        "thumbnail": {"url": avatar_url} if avatar_url else {},
        "fields": [
            {"name": "Status",   "value": status_text,    "inline": True},
            {"name": "Server",   "value": server_name,    "inline": True},
            {"name": "Location", "value": location_text,  "inline": True},
        ],
        "footer": {"text": f"TransNord Convoy Tracker • {now_utc}"},
    }

    if image_block:
        embed["image"] = image_block

    return embed


# ---------------------------------------------------------------------------
# Discord webhook sender
# ---------------------------------------------------------------------------

def send_embeds(embeds: list[dict]) -> None:
    """POST up to 10 embeds to the Discord webhook in one request."""
    if not embeds:
        return
    payload = {"embeds": embeds[:10]}
    try:
        resp = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        if resp.status_code == 204:
            print(f"[Discord] Sent {len(embeds)} embed(s).")
        else:
            print(f"[Discord] Unexpected status {resp.status_code}: {resp.text}")
    except Exception as exc:
        print(f"[Discord] Error sending embeds: {exc}")


# ---------------------------------------------------------------------------
# Bot polling loop (runs in its own thread)
# ---------------------------------------------------------------------------

def bot_loop() -> None:
    print("[Bot] Starting polling loop …")
    while True:
        embeds = []
        new_state: dict[str, dict] = {}

        for identifier in FAHRER_LISTE:
            player = fetch_player(identifier)
            if player is None:
                # Keep last known state so the map doesn't lose the marker
                with state_lock:
                    if identifier in driver_state:
                        new_state[identifier] = driver_state[identifier]
                continue

            online = bool(player.get("online", False))
            lat = player.get("latitude") or player.get("lat")
            lon = player.get("longitude") or player.get("lon")
            server = player.get("server", {})
            server_name = (
                server.get("name", "—") if isinstance(server, dict) else str(server)
            )

            new_state[identifier] = {
                "id":          player.get("id"),
                "name":        player.get("name", identifier),
                "online":      online,
                "lat":         lat,
                "lon":         lon,
                "server":      server_name,
                "avatar":      player.get("avatar", ""),
                "updated_at":  datetime.now(timezone.utc).isoformat(),
            }

            embeds.append(build_embed(player, online))

        with state_lock:
            driver_state.clear()
            driver_state.update(new_state)

        send_embeds(embeds)
        print(f"[Bot] Next update in {POLL_INTERVAL}s …")
        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Flask web server
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder=".", static_url_path="")


@app.route("/map")
def serve_map():
    """Serve the interactive Leaflet map page."""
    return send_from_directory(".", "map.html")


@app.route("/api/drivers")
def api_drivers():
    """Return current driver positions as JSON."""
    with state_lock:
        payload = list(driver_state.values())
    return jsonify(payload)


@app.route("/")
def index():
    """Redirect root to /map for convenience."""
    return serve_map()


# ---------------------------------------------------------------------------
# Entry point — start both threads
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Bot polling runs in a daemon thread so it dies with the main process
    bot_thread = threading.Thread(target=bot_loop, daemon=True, name="bot-loop")
    bot_thread.start()

    # Flask runs in the main thread (blocking)
    print("[Web] Starting Flask on port 8000 …")
    app.run(host="0.0.0.0", port=8000, use_reloader=False)
