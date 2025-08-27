from typing import List, Dict, TypedDict, Optional, Union, Any
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage, AnyMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
import json, subprocess, time, hashlib, argparse, sys, os
from pydantic import BaseModel
from run_container import run_container
from gpt_call import gpt_call
from dotenv import load_dotenv

class Item(BaseModel):
    name: str
    description: str
    price: float
    url: str

# ===== 유틸: 매물 지문(fingerprint) =====
def _fp(item: Item) -> str:
    base = f"{item.name}|{item.price}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]

# --------- 상태 ---------
class AgentState(TypedDict, total=False):
    messages: List[AnyMessage]          # LLM/툴 호출 로그 (AIMessage/ToolMessage)
    item_name: str                      # 타겟 상품명
    all_item_list: List[Item]           # 과거 거래 내역 (적정가 산출 전용)
    reasonable_price: float             # '살만하다'고 판단한 기준가(원)
    deal_candidate: Optional[Item]      # 최종 후보 매물 1건
    deal_found: bool                    # 후보 존재 여부
    inquiry_text: str                   # 선호/설정 및 생성된 문의문 등

    # --- 폴링/탐지용 추가 ---
    seen_fingerprints: List[str]        # 지금까지 본 매물 지문(중복 방지)
    sailing_item_list: List[Item]       # 현재 판매 매물 (딜 탐색 전용)
    poll_seconds: int                   # 폴링 주기(초). 예: 60
    max_polls: int                      # 최대 폴링 횟수(0 또는 None이면 무제한)
    polls_done: int                     # 누적 폴링 횟수


def _fill_tool_args(state: AgentState, ai_message: AIMessage) -> AIMessage:
    """툴 호출 인자 누락 시 state 값으로 자동 보정 + 필수 값 검증"""
    if not hasattr(ai_message, "tool_calls") or not ai_message.tool_calls:
        return ai_message
    
    valid_tool_calls = []  
    for call in ai_message.tool_calls:
        name = call.get("name")
        args = call.get("args", {})
        
        if name == "estimate_price":
            args.setdefault("item_name", state.get("item_name"))
            args.setdefault("all_item_list", [i.model_dump() for i in state.get("all_item_list", [])])

        elif name == "find_deal":
            args.setdefault("item_name", state.get("item_name"))
            args.setdefault("sailing_item_list", [i.model_dump() for i in state.get("sailing_item_list", [])])
            args.setdefault("reasonable_price", state.get("reasonable_price"))

        elif name == "compose_inquiry" and state.get("deal_candidate"):
            cand = state["deal_candidate"]
            args.setdefault("name", cand.name)
            args.setdefault("description", cand.description)
            args.setdefault("price", cand.price)
        
        if any(v in (None, "", []) for v in args.values()):
            print(f"⚠️ [인자 보정] '{name}' 호출이 필수 인자 누락으로 무시됩니다: {args}")
            continue
        
        call["args"] = args
        valid_tool_calls.append(call)
    
    ai_message.tool_calls = valid_tool_calls
    return ai_message

# --------- 툴 정의 ---------
@tool
def search_all_listings(item_name: str) -> List[Dict]:
    """
    목적:
        상품명(item_name)으로 전체 지역의 '과거 거래 완료' 매물을 모두 검색한다.
    호출 조건:
        - 실행 초기에만 호출한다.
        - 이후에는 재호출하지 않는다.
        - 이 데이터는 적정가 산출(estimate_price)용이다.
    입력:
        - item_name: 구매할 상품명 (예: "아이폰 14 프로")
    출력:
        - [{name: str, description: str, price: float, url: str}, ...]
    주의:
        - 반환 목록이 비어 있으면 이후 단계에서 적정가를 계산할 수 없다.
    """
    print(f"📦 [검색 단계] '{item_name}' 키워드로 모든 과거 매물을 검색합니다.")

    env = {"ITEM_NAME": item_name, "MODE": "ALL"}
    data = run_container("search-list", env) or []
    listings = data if isinstance(data, list) else [data]
    result = [
        {
            "name": x.get("name",""),
            "description": x.get("description",""),
            "price": float(x.get("price",0)),
            "url": x.get("url", "")
        }
        for x in listings
    ]
    print(f"🔍 [검색 결과] 총 {len(result)}건의 과거 매물을 찾았습니다.")
    return result

@tool
def search_target_region_listings(item_name: str) -> List[Dict]:
    """
    목적: 
        - 상품명(item_name)으로 현재 판매 중인 매물을 검색한다.
    호출 조건:
        - 초기 적정가 산출이 완료된 이후 호출한다.
        - 폴링 시점마다 신규 매물 탐색에 사용한다.
    입력:
        - item_name: 구매할 상품명
    출력:
        - [{name: str, description: str, price: float, url: str}, ...]
    """
    print(f"📦 [검색 단계] '{item_name}' 키워드로 현재 판매 중인 매물을 검색합니다.")
    #env = {"ITEM_NAME": item_name, "MODE": "CURRENT", "REGION": "중학동-6317"}
    env = {"ITEM_NAME": item_name, "MODE": "CURRENT", "REGION": "문정동-6184"}
    
    data = run_container("search-list", env) or []
    listings = data if isinstance(data, list) else [data]
    result = [
        {
            "name": x.get("name",""),
            "description": x.get("description",""),
            "price": float(x.get("price",0)),
            "url": x.get("url","")
        }
        for x in listings
    ]
    time.sleep(5)
    print(f"🔍 [검색 결과] 총 {len(result)}건의 현재 판매 중인 매물을 찾았습니다.")
    return result

@tool
def estimate_price(item_name: str, all_item_list: List[Dict]) -> float:
    """
    ...
    """
    print("💰 [가격 분석] 적정가를 계산합니다.")
    
    if not all_item_list:
        print("⚠️ [가격 분석] 매물 데이터가 없어 기준가를 계산할 수 없습니다.")
        return 0.0

    system_msg = """
너는 중고거래 가격 분석 전문가다.
주어진 가격 목록을 분석하여 **원 단위 정수값**으로 합리적인 적정가를 산출한다.
다른 단위(만원, 달러 등)로 변환하지 말고, 부가 설명 없이 숫자만 반환하라.
예: 1250000
"""

    user_prompt = f"""
다음은 '{item_name}'의 과거 판매글 목록이다.
제품 목록: {all_item_list}

조건:
- 한국 원 단위의 정수
- 통계적 평균과 최근 거래 경향 모두 고려
- 추가 설명 금지, 숫자만 출력
"""
    try:
        gpt_response = gpt_call(
            prompt=user_prompt,
            system=system_msg,
            model="gpt-4o-mini",
            temperature=0.0,
            response_format="text"
        )
        price_str = str(gpt_response).strip().replace(",", "")
        reasonable_price = float(price_str)
        print(f"📊 [가격 분석] 적정가: {reasonable_price:,.0f}원")
        return reasonable_price
    except Exception as e:
        print(f"⚠️ [가격 분석] GPT 호출 중 오류 발생: {e}")
        return 0.0

@tool
def find_deal(item_name: str, sailing_item_list: List[Dict], reasonable_price: float) -> Dict:
    """
    ...
    """
    print(f"🎯 [딜 탐색] 기준가 {reasonable_price:,.0f}원에 부합하는 매물을 찾습니다.")

    if not sailing_item_list:
        print("⚠️ [딜 탐색] 매물 목록이 비어있습니다.")
        return {}

    system_msg = """
당신은 중고거래 매물 분석 전문가다.
입력된 판매목록 중에서 가장 적합한 매물을 하나 그대로 반환하라.
- 반드시 입력 JSON 중 하나만 선택한다.

반환 형식 예시:
{
  "name": "아이폰 14 프로 256GB",
  "description": "거의 새 제품, 배터리 성능 99%",
  "price": 1250000,
  "url": "https://example.com"
}

주의:
- 반드시 JSON만 반환 (추가 설명 금지)
- 가격은 원 단위 정수
- 가격은 반드시 입력으로 제공된 값을 그대로 사용해야 한다.
- 가격을 새로 계산하거나 임의로 변경하면 안된다.
"""

    user_prompt = json.dumps({
        "기준가": reasonable_price,
        "판매목록": sailing_item_list
    }, ensure_ascii=False)

    try:
        gpt_response = gpt_call(
            prompt=user_prompt,
            system=system_msg,
            model="gpt-4o-mini",
            temperature=0.0,
            response_format="json"
        )

        # ⚡ 후처리 검증
        if not isinstance(gpt_response, dict) or not gpt_response:
            print("ℹ️ [딜 탐색] GPT가 선택한 매물이 없습니다. 다음 회차까지 대기합니다.")
            return {}

        price = gpt_response.get("price", float("inf"))

        if price > reasonable_price:
            print(f"⚠️ [딜 탐색] 기준가 초과 매물({price:,}원) → 무효 처리")
            #return {}

        print(f"✅ [딜 탐색] GPT가 선택한 매물: {gpt_response}")
        return gpt_response
    except Exception as e:
        print(f"⚠️ [딜 탐색] GPT 호출 중 오류 발생: {e}")
        return {}

@tool
def compose_inquiry(name: str, description: str, price: float) -> str:
    """
    목적: 
        - 매물 정보(name, description, price)를 바탕으로 Ollama(gpt-oss:20b) 모델을 호출해 판매자에게 보낼 정중한 문의문을 생성한다.
    호출 조건:
        - find_deal에서 매물 1건이 확정된 경우에만 호출
        - 출력 문장은 2~3문장, 존댓말, 거래 의사 포함
    출력:
        - str (완성된 문의문)
    주의:
        - 결과 문자열이 비어 있으면 문의 생성 실패로 간주
    """
    print(f"✏️ [문의 작성] '{name}' 매물에 대한 판매자 문의문을 작성합니다.")

    prompt = f"""
너는 중고거래 플랫폼에서 판매자에게 보낼 정중한 문의문을 작성하는 구매자이다.
아래의 매물정보를 확인해 구매 문구를 작성한다.

[매물 정보]
- 상품명: {name}
- 설명: {description}
- 가격: {price:,.0f}원

[작성 조건]
1. 존댓말 사용
2. 2~3문장
3. 구매 의사와 거래 가능 여부를 묻는 표현 포함
4. 가격 흥정은 언급하지 말 것
5. 부가 설명, 서론 금지 — 바로 거래 의사를 전달

출력: 문의문만 작성, 따옴표 없이
"""

    result = run_container("gpt-oss-20b-ollama", {"PROMPT": prompt})
    # run_container 결과 파싱
    if isinstance(result, dict):
        inquiry_text = result.get("text") or result.get("message") or ""
    elif isinstance(result, (str, bytes)):
        inquiry_text = result.decode() if isinstance(result, bytes) else result
    elif isinstance(result, list) and result:
        inquiry_text = str(result[0])
    else:
        inquiry_text = ""
    inquiry_text = inquiry_text.strip()

    print(f"📨 [문의 작성] 작성된 문구: {inquiry_text}")
    return inquiry_text

TOOLS = [search_all_listings, search_target_region_listings, estimate_price, find_deal, compose_inquiry]
tool_node = ToolNode(TOOLS)

# --------- LLM(툴 바인딩) ---------
model = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
).bind_tools(TOOLS)

# --------- 정책 노드(모델 호출) ---------
def policy(state: AgentState) -> AgentState:
    print("🤖 [정책 노드] 현재 상태를 바탕으로 다음 행동을 계획합니다.")
    print("    =========== 현재 상태 ===========")
    print(f"   • 타겟 상품명: {state.get('item_name')}")
    print(f"   • 전체 매물 수: {len(state.get('all_item_list') or [])}")
    print(f"   • 새롭게 검색된 매물 수: {len(state.get('sailing_item_list') or [])}")
    print(f"   • 적정가(기준가): {state.get('reasonable_price') or '미정'}")
    print(f"   • 신규 딜 발견 여부: {state.get('deal_found', False)}")
    print(f"   • 폴링 횟수: {state.get('polls_done', 0)} / 최대 {state.get('max_polls', '무제한')}")
    print("    =================================")

    print("🛠️ [정책 노드] 모델이 다음 단계에서 어떤 툴을 호출할지 판단합니다.")
    raw_msgs = state.get("messages", [])

    # === 최근 툴 호출 내역 ===
    tail: List[AnyMessage] = []
    for i in range(len(raw_msgs) - 1, -1, -1):
        m = raw_msgs[i]
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            tail = raw_msgs[i:]
            break

    # === 이전 실행 툴 히스토리 요약 ===
    tool_history = []
    for m in raw_msgs:
        if isinstance(m, ToolMessage):
            tool_history.append(m.name)
    history_str = "이전에 실행한 툴: " + (", ".join(tool_history) if tool_history else "없음")

    # === 상태 요약 ===
    state_summary = {
        "전체 매물 확보 여부": bool(state.get("all_item_list")),
        "전체 매물 수": len(state.get("all_item_list") or []),
        "새롭게 검색된 매물 수": len(state.get("sailing_item_list") or []),
        "적정가": state.get("reasonable_price"),
        "최종 딜 발견": state.get("deal_found", False),
        "최종 딜 존재 여부": bool(state.get("deal_candidate")),
        "폴링 횟수": int(state.get("polls_done", 0)),
        "최대 폴링 횟수": state.get("max_polls"),
    }

    sys = SystemMessage(content="""
너는 사용자를 대신해 중고거래 시장을 탐색하고, 합리적인 가격에 원하는 상품을 구매하려는 구매 에이전트다.
너의 목표는 다음과 같다:
1. 상품의 과거 거래를 조사해 적정 가격을 파악한다.
2. 시장을 주기적으로 살펴 신규 매물을 발견한다.
3. 기준가 대비 가치 있는 매물을 찾아내고, 거래 문의글을 작성한다.

툴 사용 가이드 (중복 실행 방지 포함):
- search_all_listings: 최초 전체 매물 리스트 확보용. 이미 전체 매물이 확보되어 있다면 더 이상 호출 가치가 없다.
- estimate_price: 기준가 산출용. 이미 적정가가 정해져 있다면 반복 호출할 필요가 없다.
- search_target_region_listings: 특정 지역 최신 매물 확인용. 새롭게 검색된 매물 수가 0건인 경우, 지속적으로 호출하면서 최신 매물이 올라왔는지 확인한다.
- find_deal: 새롭게 검색된 매물 존재할 때, 기준가 기준 살 만한 매물이 있는지 탐색한다.
- compose_inquiry: 최종 딜이 존재할 때, 문의글을 작성하여 최종 목적을 달성한다. 

항상 현재 상태 요약을 참고해, 어떤 툴이 지금 새로운 가치를 만들 수 있는지 판단하라.
툴 호출을 할 때는 반드시 필요한 모든 인자를 제공해야 한다.
툴 호출 외의 불필요한 텍스트는 출력하지 않는다.
""")

    # === NEW: 상태 요약을 HumanMessage로 전달 ===
    summary = HumanMessage(content=json.dumps({
        "goal": f"{state.get('item_name','')}를 가장 좋은 조건에 맞춰 신중하게 구매",
        "state_summary": state_summary,
        "history": history_str,
        "hint": (
            "상태를 분석하고 다음 전략적 행동을 결정하라. "
            "툴을 선택하기 전, 왜 지금 이 툴이 필요한지 내부적으로 판단한 후 호출하라."
        )
    }, ensure_ascii=False))

    call_msgs = [sys, summary, *tail] if tail else [sys, summary]

    ai = model.invoke(call_msgs)
    ai = _fill_tool_args(state, ai)
    if hasattr(ai, "tool_calls") and ai.tool_calls:
        print(f"   → AGENT 정책 모델이 선택한 툴: {[t['name'] for t in ai.tool_calls]}")
    else:
        print("   → AGENT 정책 모델이 툴 호출 없이 응답을 반환했습니다.")

    return {**state, "messages": [*raw_msgs, ai]}

# --------- 관찰 → 상태 반영 리듀서 ---------
def _parse_tool_content(content: Any):
    if isinstance(content, (dict, list, float, int)):
        return content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except Exception:
            return content
    return content

def reduce_observation(state: AgentState) -> AgentState:
    msgs = state.get("messages", [])
    last_idx = int(state.get("_last_msg_idx", 0))
    new_msgs = msgs[last_idx:]

    for m in new_msgs:
        if not isinstance(m, ToolMessage):
            continue
        
        tool_name = m.name
        state["_last_tool"] = tool_name  ### FIX: 마지막 실행 툴 기록
        
        before_state = dict(state)  # 상태 스냅샷 저장
        print(f"   • 실행된 툴: {tool_name}")
        out = _parse_tool_content(m.content)
        print(f"   • 툴 반환값: {str(out)[:100]}{'...' if len(str(out)) > 100 else ''}")
        
        if tool_name == "search_all_listings" and isinstance(out, list):
            # 과거 매물은 적정가 계산용 → fingrprint 업데이트는 하지 않음
            items: List[Item] = []
            for x in out:
                try:
                    items.append(Item.model_validate(x))
                except Exception:
                    continue
            state["all_item_list"] = items
            state["polls_done"] = int(state.get("polls_done", 0)) + 1

        elif tool_name == "search_target_region_listings" and isinstance(out, list):
            # 현재 매물은 신규 탐지 대상 → fingerprint 업데이트
            items: List[Item] = []
            for x in out:
                try:
                    items.append(Item.model_validate(x))
                except Exception:
                    continue
            state["sailing_item_list"] = items

            seen = set(state.get("seen_fingerprints") or [])
            sailing_item_list: List[Item] = []
            for it in items:
                fp = _fp(it)
                if fp not in seen:
                    sailing_item_list.append(it)
                    seen.add(fp)

            state["sailing_item_list"] = sailing_item_list
            state["seen_fingerprints"] = list(seen)
            state["polls_done"] = int(state.get("polls_done", 0)) + 1

        elif tool_name == "estimate_price" and isinstance(out, (int, float)):
            state["reasonable_price"] = float(out)

        elif tool_name == "find_deal" and isinstance(out, dict):
            try:
                state["deal_candidate"] = Item.model_validate(out)
                state["deal_found"] = True
            except Exception:
                state["deal_found"] = False
            state["sailing_item_list"] = []

        elif tool_name == "compose_inquiry" and isinstance(out, str):
            state["inquiry_text"] = out

        after_state = dict(state)
    state["_last_msg_idx"] = len(msgs)
    return state

# --------- 대기 노드(폴링 템포) ---------
def wait_tick(state: AgentState) -> AgentState:
    sec = int(state.get("poll_seconds", 10) or 10)
    print(f"⏳ [대기 단계] {sec}초 동안 기다립니다. 다음 검색 시점을 준비합니다.")
    time.sleep(sec)
    return state

# --------- 종료 판단 ---------
def should_end(state: AgentState) -> bool:
    has_deal = bool(state.get("deal_found") and state.get("deal_candidate"))
    has_inquiry = bool(state.get("inquiry_text"))
    max_polls = int(state.get("max_polls") or 0)

    if has_deal and has_inquiry:
        print("🏁 [종료] 딜과 문의문구가 준비되어 종료합니다.")
        return True
    if max_polls > 0 and int(state.get("polls_done", 0)) >= max_polls:
        print("🏁 [종료] 최대 폴링 횟수에 도달하여 종료합니다.")
        return True
    return False

def _next_after_reduce(s: AgentState) -> str:
    if should_end(s):
        return "END"
    last_tool = s.get("_last_tool")

    # 지역 매물 검색 했는데 딜 없으면 → wait (다시 poll)
    if last_tool == "search_target_region_listings" and not s.get("deal_found"):
        return "wait"
    return "policy"

# --------- 그래프 ---------
g = StateGraph(AgentState)
g.add_node("policy", policy)
g.add_node("tools", tool_node)
g.add_node("reduce", reduce_observation)
g.add_node("wait", wait_tick)

g.add_edge(START, "policy")
g.add_conditional_edges("policy", tools_condition, {"tools": "tools", "__end__": "wait"})
g.add_edge("tools", "reduce")
g.add_conditional_edges("reduce", _next_after_reduce, {"END": END, "policy": "policy", "wait": "wait"})
g.add_edge("wait", "policy")

app = g.compile()

# ===== CLI 엔트리포인트 =====
def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="중고거래 에이전트 (Tool-calling + Polling, one-shot CLI)")
    parser.add_argument("item_name", help="조회할 상품명 (예: '아이패드 에어 5')")
    parser.add_argument("--poll-seconds", type=int, default=10, help="폴링 주기(초). 기본 60")
    parser.add_argument("--max-polls", type=int, default=120, help="최대 폴링 횟수(0=무제한). 기본 10")
    args = parser.parse_args()

    init_state: AgentState = {
        "item_name": args.item_name,
        "messages": [],
        "all_item_list": [],
        "reasonable_price": 0.0,
        "deal_candidate": None,
        "deal_found": False,
        "seen_fingerprints": [],
        "sailing_item_list": [],
        "poll_seconds": args.poll_seconds,
        "max_polls": args.max_polls,
        "polls_done": 0,
    }

    # LangGraph 실행: stream으로 진행 상황을 소비(원하면 로그 추가 가능)
    state = app.invoke(init_state, config={"recursion_limit": 1000})
    # 결과 출력
    print("\n[done] 실행 종료.")
    rp = state.get("reasonable_price")
    if rp:
        print(f" - 적정가(기준가): {rp:,.0f}원")
    else:
        print(" - 적정가 산출 실패/미정")

    if state.get("deal_found") and state.get("deal_candidate"):

        cand = state["deal_candidate"]
        print(f"   · 이름: {cand.name}")
        print(f"   · 설명: {cand.description}")
        print(f"   · 가격: {cand.price:,.0f}원")
        print(f"   · URL: {cand.url}")
        if state.get("inquiry_text"):
            print("\n[문의 문구]")
            print(state["inquiry_text"])
    else:
        print(" - 이번 실행에서 딜을 찾지 못했습니다.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[interrupt] 사용자 중단으로 종료합니다.")
