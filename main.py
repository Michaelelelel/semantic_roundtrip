import requests
import time

url = "http://llama:8080/completion"

system_prompt = """You create visual prompts for a text-to-image model.
Return exactly 3 distinct prompts as a JSON array of strings.
Do not include markdown."""

user_prompts = [
    "Domain: bands \nTitle: Queen",
    "Domain: movie \nTitle: The Matrix",
    "Domain: songs \nTitle: Imagine"
]

for prompt in user_prompts:
    print(f"Sende Prompt: '{prompt}'")
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 150
    }

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            result = response.json()
            print("Antwort:", result["content"])
        else:
            print("Fehler beim Abruf:", response.status_code)
    except Exception as e:
        print("Verbindungsfehler:", e)

    time.sleep(2)