FROM python:3.11-slim

WORKDIR /app

# 의존성 설치 레이어
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY app.py /app/app.py
ENV PYTHONUNBUFFERED=1

ENV ITEM_NAME=신세계상품권10만원
ENV MODE=CURRENT
ENV REGION=중학동-6317


ENTRYPOINT ["python", "/app/app.py"]
