import os, json
from typing import Dict, Any, Literal
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def gpt_call(
    *,
    prompt: str,
    system: str | None = None,
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    response_format: Literal["text","json"] = "text"
) -> Any:
    """
    공통 GPT 호출 래퍼
    - text 모드: 문자열 반환
    - json 모드: JSON 파싱 후 dict 반환
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    if response_format == "json":
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=messages,
        )
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)
    else:
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
        )
        return (resp.choices[0].message.content or "").strip()
