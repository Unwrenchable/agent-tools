import os
import requests
import time

REALAI_API_URL = os.getenv("REALAI_API_URL")
REALAI_API_KEY = os.getenv("REALAI_API_KEY")
REALAI_MODEL = os.getenv("REALAI_MODEL", "realai-psi")

def call_realai(messages):
    start = time.time()

    payload = {
        "model": REALAI_MODEL,
        "messages": messages
    }

    headers = {
        "Authorization": f"Bearer {REALAI_API_KEY}",
        "Content-Type": "application/json"
    }

    r = requests.post(f"{REALAI_API_URL}/v1/chat/completions",
                      json=payload,
                      headers=headers)

    r.raise_for_status()
    data = r.json()

    content = data["choices"][0]["message"]["content"]
    latency = int((time.time() - start) * 1000)

    return content, latency
