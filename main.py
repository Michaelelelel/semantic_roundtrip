import base64
import math
import os
import requests
import time
from pathlib import Path

TEXT_TO_TEXT_MODEL_URL = "http://llama:8080/v1/chat/completions"
VLM_URL = "http://vlm:8080/completion"
COMFY_URL = "http://comfyui:8188"
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/outputs"))

# Das Modell liefert freien Text, der direkt als Bild-Prompt verwendet wird.
system_prompt = """Create one visual prompt for a text-to-image model.
Return only the prompt text, without a label, JSON, markdown, or explanation."""

test_cases = [
    ("bands", "Queen"),
    ("movies", "The Matrix"),
    ("songs", "Imagine"),
]


def wait_for_comfy_image(prompt_id, timeout=300):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        response = requests.get(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
        response.raise_for_status()
        prompt_history = response.json().get(prompt_id)

        if prompt_history:
            for output in prompt_history.get("outputs", {}).values():
                for image in output.get("images", []):
                    image_path = OUTPUT_DIR / image.get("subfolder", "") / image["filename"]
                    if image_path.is_file():
                        return image_path

            status = prompt_history.get("status", {})
            if status.get("completed"):
                raise RuntimeError("ComfyUI hat den Auftrag ohne Ausgabebild beendet.")

        time.sleep(2)

    raise TimeoutError(f"ComfyUI-Auftrag {prompt_id} war nach {timeout} Sekunden nicht fertig.")


def guess_title(image_path, domain):
    image_base64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    question = (
        f"This image represents an item from the domain '{domain}'. "
        "Guess its exact title or name. Return only your single best guess without an explanation."
    )
    prompt = (
        "A chat between a curious user and an artificial intelligence assistant. "
        "The assistant gives helpful, detailed, and polite answers to the user's questions. "
        f"USER: <__media__>\n{question}\nASSISTANT:"
    )
    payload = {
        "prompt": {
            "prompt_string": prompt,
            "multimodal_data": [image_base64],
        },
        "temperature": 0.0,
        "top_k": 1,
        "n_predict": 64,
        "n_probs": 1,
        "stop": ["USER:"],
    }

    response = requests.post(VLM_URL, json=payload, timeout=300)
    response.raise_for_status()
    result = response.json()
    guessed_title = result["content"].strip()
    token_logprobs = [
        token["logprob"]
        for token in result.get("completion_probabilities", [])
        if token.get("logprob") is not None
    ]
    confidence = None
    if token_logprobs:
        confidence = math.exp(sum(token_logprobs) / len(token_logprobs))

    return guessed_title, confidence


for domain, title in test_cases:
    prompt = f"Domain: {domain}\nTitle: {title}"
    print(f"\n--- Sende Prompt an Llama: '{prompt}' ---")
    payload = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    try:
        # 1. LLAMA: Text to Text
        response = requests.post(TEXT_TO_TEXT_MODEL_URL, json=payload, timeout=300)
        response.raise_for_status()
        result = response.json()
        raw_content = result["choices"][0]["message"]["content"]

        final_image_prompt = raw_content.strip()
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

        comfy_response = requests.post(f"{COMFY_URL}/prompt", json={"prompt": workflow}, timeout=30)
        comfy_response.raise_for_status()
        prompt_id = comfy_response.json()["prompt_id"]
        print(f"ComfyUI-Auftrag angenommen: {prompt_id}")

        image_path = wait_for_comfy_image(prompt_id)
        print("ComfyUI-Bild fertig:", image_path)

        # 3. VLM: Bild und Domain zu Titel
        print("-> Sende Bild an LLaVA 1.5...")
        guessed_title, confidence = guess_title(image_path, domain)
        exact_match = guessed_title.casefold() == title.casefold()

        print("Erwarteter Titel:", title)
        print("VLM-Antwort:", guessed_title)
        if confidence is None:
            print("Token-Confidence: nicht verfügbar")
        else:
            print(f"Token-Confidence: {confidence:.2%}")
        print("Exact Match:", exact_match)

    except Exception as e:
        print("Fehler in der Pipeline:", e)

    time.sleep(2)
