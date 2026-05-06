import os
import requests
import time

class RealAIProvider:
    name = "realai"

    # scoring so router can rank it
    cost_score = 2
    speed_score = 3
    context_score = 3

    def available(self) -> bool:
        return bool(os.getenv("REALAI_API_KEY"))

    def complete(self, prompt: str, context: dict, dry_run: bool) -> dict[str, any]:
        if dry_run:
            return {
                "response": f"[DRY RUN] RealAI would respond to: {prompt}",
                "tokens": 0
            }

        api_url = os.getenv("REALAI_API_URL")
        api_key = os.getenv("REALAI_API_KEY")
        model = os.getenv("REALAI_MODEL", "realai-psi")

        if not api_url or not api_key:
            raise RuntimeError("RealAI provider missing REALAI_API_URL or REALAI_API_KEY")

        start = time.time()

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": context.get("role", "assistant")},
                {"role": "user", "content": prompt}
            ]
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        r = requests.post(f"{api_url}/v1/chat/completions", json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

        latency = int((time.time() - start) * 1000)

        return {
            "response": data["choices"][0]["message"]["content"],
            "tokens": data.get("usage", {}).get("total_tokens", 0),
            "latency_ms": latency
        }
