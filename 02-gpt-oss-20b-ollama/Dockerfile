FROM python:3.11-slim

# Install Ollama
RUN apt-get update && apt-get install -y curl \
    && curl -fsSL https://ollama.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip install --no-cache-dir requests

WORKDIR /app
COPY app.py .

ENV OLLAMA_NUM_PARALLEL=1 \
    OLLAMA_MAX_LOADED_MODELS=1 \
    OLLAMA_NO_MLOCK=1

CMD /bin/sh -lc '\
  ollama serve & \
  # 서버 ready 대기
  for i in $(seq 1 60); do \
    curl -sf http://127.0.0.1:11434/ >/dev/null && break; \
    sleep 1; \
  done; \
  # 모델 다운로드
  ollama pull gpt-oss:20b || exit 1; \
  # app.py 실행
  python app.py \
'
