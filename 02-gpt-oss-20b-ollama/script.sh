# Docker build
docker build -t gpt-oss-20b-ollama .

docker run --rm \
  -e PROMPT=$'너는 중고거래에서 판매자에게 보낼 정중한 문의문을 작성하는 AI다.\n다음 매물 정보를 참고해서 문의문을 작성하라.\n\n상품명: 아이폰 14 프로\n설명: 상태 좋음, 구성품 포함\n가격: 1,300,000원\n\n조건:\n- 2~3문장\n- 존댓말 사용\n- 거래 의사를 묻는 표현 포함' \
  -v ollama_data:/root/.ollama \
  gpt-oss-20b-ollama 
