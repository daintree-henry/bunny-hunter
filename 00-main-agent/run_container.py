from typing import Dict, List, Union
import subprocess
import json

def run_container(image: str, env_vars: Dict[str, str]) -> Union[List, Dict]:
    """
    컨테이너는 stdout으로 JSON을 출력한다고 가정.
    비즈니스 로직은 컨테이너 내부에 있으므로 여기선 호출/파싱만.
    """
    cmd = ["docker", "run"]
    # cmd = ["docker", "run", "--rm"]

    # Ollama 모델 이미지인 경우에만 볼륨 마운트
    if "gpt-oss-20b-ollama" in image:
        cmd.extend(["-v", "ollama_data:/root/.ollama"])

    for k, v in env_vars.items():
        cmd.extend(["-e", f"{k}={v}"])
    cmd.append(image)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw = result.stdout.strip()
        try:
            # 1차: 그대로 파싱 시도
            return json.loads(raw)
        except json.JSONDecodeError:
            # 2차: 뒤에서부터 { 또는 [ 찾아서 자르기
            start = max(raw.rfind("{"), raw.rfind("["))
            if start != -1:
                try:
                    return json.loads(raw[start:])
                except json.JSONDecodeError:
                    return []
            return []
    except Exception as e:
        return []



