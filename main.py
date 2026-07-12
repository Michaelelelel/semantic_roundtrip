import requests
import time
import json
import urllib.request

TEXT_TO_TEXT_MODEL_URL = "http://llama:8080/v1/chat/completions"
COMFY_URL = "http://comfyui:8188/prompt"

# Wir zwingen das Modell zu striktem JSON mit einem einzigen Key "prompt"
system_prompt = """You create visual prompts for a text-to-image model.
Return exactly ONE distinct prompt as a JSON object with the key "prompt".
Do not include markdown."""

user_prompts = [
    "Domain: bands \nTitle: Queen",
    "Domain: movie \nTitle: The Matrix",
    "Domain: songs \nTitle: Imagine"
]

for prompt in user_prompts:
    print(f"\n--- Sende Prompt an Llama: '{prompt}' ---")
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    try:
        # 1. LLAMA: Text to Text
        response = requests.post(TEXT_TO_TEXT_MODEL_URL, json=payload)
        if response.status_code == 200:
            result = response.json()
            raw_content = result["choices"][0]["message"]["content"]

            # JSON parsen
            json_data = json.loads(raw_content)
            final_image_prompt = json_data["prompt"]
            print("Llama hat generiert:", final_image_prompt)

            # 2. COMFYUI: Text zu Bild Standard Settings
            print("-> Sende an ComfyUI...")
            workflow = {
                "3": {"class_type": "KSampler",
                      "inputs": {"cfg": 8, "denoise": 1, "latent_image": ["5", 0], "model": ["4", 0],
                                 "negative": ["7", 0], "positive": ["6", 0], "sampler_name": "euler",
                                 "scheduler": "normal", "seed": 8566257, "steps": 20}},
                "4": {"class_type": "CheckpointLoaderSimple",
                      "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"}},
                "5": {"class_type": "EmptyLatentImage", "inputs": {"batch_size": 1, "height": 512, "width": 512}},
                "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": final_image_prompt}},
                "7": {"class_type": "CLIPTextEncode",
                      "inputs": {"clip": ["4", 1], "text": "text, watermark, bad quality, blurry"}},
                "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
                "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "LlamaGenerated", "images": ["8", 0]}}
            }

            comfy_payload = {"prompt": workflow}
            req = urllib.request.Request(COMFY_URL, data=json.dumps(comfy_payload).encode('utf-8'))
            comfy_response = urllib.request.urlopen(req)
            print("ComfyUI generiert das Bild! (Schau in den /outputs Ordner)")

        else:
            print("Fehler beim Abruf von Llama:", response.status_code)

    except Exception as e:
        print("Verbindungsfehler:", e)

    time.sleep(2)