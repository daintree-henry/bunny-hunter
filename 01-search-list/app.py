import os, sys, json, re, time
from typing import Any, Dict, List
from urllib.parse import urlencode
import requests
from bs4 import BeautifulSoup

def _to_float(v: Any) -> float:
    if v is None: return 0.0
    if isinstance(v, (int, float)): return float(v)
    if isinstance(v, str):
        s = v.replace(",", "").replace("₩", "").strip()
        s = re.sub(r"[^\d\.]", "", s)
        try: return float(s)
        except: return 0.0
    return 0.0

def _as_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict): return obj
    if isinstance(obj, list) and obj: return _as_dict(obj[0])
    return {}

def main():
    item_name = (os.getenv("ITEM_NAME") or "").strip()
    mode = (os.getenv("MODE") or "CURRENT").strip().upper()
    region = (os.getenv("REGION") or "").strip()

    if mode not in ("ALL", "CURRENT"):
        mode = "CURRENT"

    base = "https://www.daangn.com/kr/buy-sell/"
    urls: List[str] = []

    if mode == "ALL":
        for p in range(1, 4):
            urls.append(f"{base}?{urlencode({'search': item_name, 'page': str(p)})}")
    else:  # CURRENT
        params = {"search": item_name}
        if region:  # 지역 있으면 추가
            params["in"] = region
        urls.append(f"{base}?{urlencode(params)}")

    result: List[Dict[str, Any]] = []
    seen = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "ko,en;q=0.9",
    }

    for url in urls:
        with requests.Session() as s:
            s.headers.update(headers)
            r = s.get(url, timeout=10)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or r.encoding
            html = r.text

        soup = BeautifulSoup(html, "lxml")
        items_data = None

        for tag in soup.select('script[type="application/ld+json"]'):
            txt = tag.string or tag.get_text() or ""
            try:
                data = json.loads(txt)
            except Exception:
                idx = max(txt.rfind("{"), txt.rfind("["))
                if idx >= 0:
                    try: data = json.loads(txt[idx:])
                    except Exception: continue
                else:
                    continue

            def is_itemlist(d):
                return isinstance(d, dict) and "ItemList" in str(d.get("@type",""))

            if is_itemlist(data):
                items_data = data; break
            if isinstance(data, list):
                for el in data:
                    if is_itemlist(el):
                        items_data = el; break
            if items_data: break

        if not items_data: continue

        for elem in items_data.get("itemListElement", []):
            if isinstance(elem, dict) and "item" in elem:
                item = _as_dict(elem.get("item"))
            elif isinstance(elem, dict):
                item = elem
            else:
                item = {}
            if not item: continue

            offers = _as_dict(item.get("offers", {}))
            seller = _as_dict(offers.get("seller", {}))
            availability = (offers.get("availability") or "").strip()
            seller_type = seller.get("@type") or seller.get("type") or ""

            if mode == "CURRENT":
                is_instock = (
                    availability == "https://schema.org/InStock"
                    or str(availability).endswith("InStock")
                    or availability == "InStock"
                )
                if not (is_instock and seller_type == "Person"):
                    continue

            key = (item.get("name",""), item.get("url",""), _to_float(offers.get("price")))
            if key in seen: continue
            seen.add(key)

            result.append({
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "url": item.get("url", ""),
                "price": _to_float(offers.get("price")),
            })

    print(json.dumps(result, ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
