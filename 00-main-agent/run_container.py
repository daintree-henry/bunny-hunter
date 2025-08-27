"""Docker 컨테이너를 실행해 JSON 결과를 받아오는 헬퍼 함수."""

from typing import Dict, List, Union
import subprocess
import json


def run_container(image: str, env_vars: Dict[str, str]) -> Union[List, Dict]:
    """지정한 이미지를 실행하고, stdout을 JSON으로 파싱한다.

    Args:
        image: 실행할 Docker 이미지 이름
        env_vars: 컨테이너에 전달할 환경변수

    Returns:
        컨테이너가 출력한 JSON 리스트/딕셔너리. 파싱 실패 시 빈 리스트.
    """

    # 기본 docker run 명령어 구성
    cmd = ["docker", "run"]
    # cmd = ["docker", "run", "--rm"]  # 필요 시 컨테이너 자동 삭제

    # Ollama 모델 이미지인 경우에만 모델 데이터를 볼륨으로 공유
    if "gpt-oss-20b-ollama" in image:
        cmd.extend(["-v", "ollama_data:/root/.ollama"])

    # 환경변수 추가 (-e KEY=VALUE)
    for k, v in env_vars.items():
        cmd.extend(["-e", f"{k}={v}"])
    cmd.append(image)

    try:
        # 컨테이너 실행 및 결과 획득
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw = result.stdout.strip()
        try:
            # 1차: 그대로 JSON 파싱 시도
            return json.loads(raw)
        except json.JSONDecodeError:
            # 2차: stdout에 다른 로그가 섞인 경우 뒤에서부터 JSON 부분을 추출
            start = max(raw.rfind("{"), raw.rfind("["))
            if start != -1:
                try:
                    return json.loads(raw[start:])
                except json.JSONDecodeError:
                    return []
            return []
    except Exception:
        # 실행 실패 또는 파싱 실패 시 빈 리스트 반환
        return []



