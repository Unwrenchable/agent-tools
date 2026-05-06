import os
import requests
import time

REALAI_API_URL = os.getenv("REALAI_API_URL")
REALAI_API_KEY = os.getenv("REALAI_API_KEY")
REALAI_MODEL = os.getenv("REALAI_MODEL", "realai-psi")

class RealAIProvider:
    name = "realai"

    def complete(self, prompt: str, context: dict, dry_run: bool = False):
        if dry_run:
            return {
                "response": f"[DRY RUN] RealAI would respond to: {prompt}",
                "tokens": 0
            }

        start = time.time()

        payload = {
            "model": REALAI_MODEL,
            "messages": [
                {"role": "system", "content": context.get("role", "assistant")},
                {"role": "user", "content": prompt}
            ]
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

        latency = int((time.time() - start) * 1000)

        return {
            "response": data["choices"][0]["message"]["content"],
            "tokens": data.get("usage", {}).get("total_tokens", 0),
            "latency_ms": latency
        }
