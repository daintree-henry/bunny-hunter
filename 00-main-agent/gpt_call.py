"""OpenAI 챗GPT 모델 호출을 위한 간단한 래퍼 모듈."""

import os
import json
from typing import Any, Literal

from dotenv import load_dotenv
from openai import OpenAI

# .env 파일에 저장된 API 키 로드
load_dotenv()

# 환경변수에서 읽은 API 키로 OpenAI 클라이언트 초기화
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def gpt_call(
    *,
    prompt: str,
    system: str | None = None,
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    response_format: Literal["text", "json"] = "text",
) -> Any:
    """GPT 모델을 호출해 응답을 반환한다.

    Args:
        prompt: 사용자 프롬프트 텍스트
        system: 시스템 역할 지침(옵션)
        model: 사용할 모델 이름
        temperature: 생성 무작위성
        response_format: ``text``면 문자열, ``json``이면 dict 반환

    Returns:
        모델 응답 문자열 또는 JSON(dict)
    """

    messages = []  # OpenAI ChatCompletion 형식 메시지 배열
    if system:
        # 시스템 메시지로 모델의 기본 역할을 지정
        messages.append({"role": "system", "content": system})
    # 사용자 입력을 메시지에 추가
    messages.append({"role": "user", "content": prompt})

    if response_format == "json":
        # 모델에게 JSON 객체를 기대한다고 명시
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
        # 앞뒤 공백을 제거해 깔끔한 문자열을 반환
        return (resp.choices[0].message.content or "").strip()

