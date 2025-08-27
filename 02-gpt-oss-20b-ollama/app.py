"""Ollama 서버에 프롬프트를 전달해 응답을 JSON으로 출력하는 스크립트."""

import os
import json
import requests

OLLAMA_API = "http://localhost:11434/api/chat"


def main() -> None:
    """환경변수 ``PROMPT``를 읽어 모델을 호출하고 결과를 출력한다."""

    prompt = os.getenv("PROMPT", "").strip()
    if not prompt:
        print(json.dumps({"error": "PROMPT env var is empty"}))
        return

    payload = {
        "model": "gpt-oss:20b",  # 사용할 로컬 모델 이름
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,  # 스트리밍 대신 한번에 응답받기
        "options": {
            "num_predict": 1024,  # 최대 생성 토큰 수
            "num_ctx": 1024,      # 컨텍스트 길이
            "num_batch": 16,      # 배치 크기
        },
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

