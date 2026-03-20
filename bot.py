import requests
import time

# Discord Webhook URL hier einfügen
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1484331891116212424/_cXCA6KAWa8Ysi9we_PZRSCpmXL6UoPLDqkFvfRahL64tKLMSptcxv0GeHC7Ej7v2Alv"

# Liste deiner Fahrer
fahrer_liste = ["5810271", "Gruckenwasserimglas", "4611616"]

def sende_nachricht(nachricht):
    data = {"content": nachricht}
    response = requests.post(DISCORD_WEBHOOK, json=data)
    if response.status_code == 204:
        print("Nachricht gesendet!")
    else:
        print("Fehler beim Senden:", response.text)

def main():
    while True:
        for fahrer in fahrer_liste:
            sende_nachricht(f"Fahrer online: {fahrer}")
        time.sleep(300)  # alle 5 Minuten

if __name__ == "__main__":
    main()
