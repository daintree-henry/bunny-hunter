# 검색 서비스용 Docker 이미지 빌드 및 실행 예시

docker build -t search-list .

# 전체 지역의 과거 매물 검색
docker run --rm \
  -e ITEM_NAME="신세계상품권" \
  -e MODE=ALL \
  search-list

# 특정 지역의 현재 매물 검색
docker run --rm \
  -e ITEM_NAME="신세계상품권" \
  -e MODE=CURRENT \
  search-list

