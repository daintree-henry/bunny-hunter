import os
import json
import requests

OLLAMA_API = "http://localhost:11434/api/chat"

def main():
    prompt = os.getenv("PROMPT", "").strip()
    if not prompt:
        print(json.dumps({"error": "PROMPT env var is empty"}))
        return

    payload = {
        "model": "gpt-oss:20b",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "options": {
            "num_predict": 1024,
            "num_ctx": 1024,
            "num_batch": 16
        }
    }

    try:
        resp = requests.post(OLLAMA_API, json=payload, timeout=600)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "").strip()
        # 결과를 stdout으로 JSON 형태로 출력
        print(json.dumps({"text": content}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()