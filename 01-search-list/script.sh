docker build -t search-list .

# 전체 지역 과거 매물
docker run --rm \
  -e ITEM_NAME="신세계상품권 10만원 권" \
  -e MODE=ALL \
  search-list

# 타깃 지역 현재 매물만
docker run --rm \
  -e ITEM_NAME="신세계상품권 10만원 권" \
  -e MODE=CURRENT \
  search-list