import requests
import time
import json
import os

# Discord Webhook URL
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1484331891116212424/_cXCA6KAWa8Ysi9we_PZRSCpmXL6UoPLDqkFvfRahL64tKLMSptcxv0GeHC7Ej7v2Alv"

# TruckersMP player IDs to monitor
FAHRER_IDS = ["5810271", "Gruckenwasserimglas", "4611616"]

# File to persist online/offline state across restarts
STATUS_FILE = "status.json"

# How often to poll the API (in seconds)
CHECK_INTERVAL = 30


def lade_status():
    """Load the previously saved online status from disk."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warnung: Status-Datei konnte nicht gelesen werden: {e}")
    return {}


def speichere_status(status):
    """Persist the current online status to disk."""
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)
    except IOError as e:
        print(f"Warnung: Status-Datei konnte nicht gespeichert werden: {e}")


def hole_spieler_info(player_id):
    """
    Fetch player info from the TruckersMP API.
    Returns (name, is_online) on success, or (player_id, None) on error.
    """
    url = f"https://api.truckersmp.com/v2/player/{player_id}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            name = data.get("response", {}).get("name", player_id)
            online = data.get("response", {}).get("online", False)
            return name, online
        else:
            print(f"API-Fehler für {player_id}: HTTP {response.status_code}")
            return player_id, None
    except requests.RequestException as e:
        print(f"Netzwerkfehler für {player_id}: {e}")
        return player_id, None


def sende_nachricht(nachricht):
    """Send a message to the configured Discord webhook."""
    data = {"content": nachricht}
    try:
        response = requests.post(DISCORD_WEBHOOK, json=data, timeout=10)
        if response.status_code == 204:
            print(f"Nachricht gesendet: {nachricht}")
        else:
            print(f"Fehler beim Senden: {response.status_code} – {response.text}")
    except requests.RequestException as e:
        print(f"Netzwerkfehler beim Senden der Nachricht: {e}")


def main():
    print("Bot gestartet. Überwache Fahrer-Status …")
    vorheriger_status = lade_status()

    while True:
        for player_id in FAHRER_IDS:
            name, online = hole_spieler_info(player_id)

            # Skip this player if the API returned an error
            if online is None:
                continue

            war_online = vorheriger_status.get(player_id)

            # Only notify when the status actually changes
            if war_online is None:
                # First run — record current state silently so we don't
                # spam notifications for drivers who were already online
                # before the bot started.
                print(f"Erster Check für {name} ({player_id}): {'online' if online else 'offline'}")
            elif online and not war_online:
                sende_nachricht(f"Fahrer online: {name}")
            elif not online and war_online:
                sende_nachricht(f"Fahrer offline: {name}")

            vorheriger_status[player_id] = online

        speichere_status(vorheriger_status)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()

