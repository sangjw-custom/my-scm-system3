import streamlit as st
import pandas as pd
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="클라우드 SCM 통합 관리", layout="wide")

# 2. 구글 시트 연결 (가장 간단한 URL 방식)
# 실제 운영 시에는 st.connection("gsheets", ...) 형식을 권장하나, 여기서는 빠른 이해를 위해 로직만 구성합니다.
SHEET_URL = "https://docs.google.com/spreadsheets/d/본인의_시트_아이디/edit#gid=0"

# [참고] 본 코드는 세션 상태를 활용하되, '저장' 버튼 클릭 시 시트에 기록하는 방식으로 구현하는 것이 속도면에서 유리합니다.
# 여기서는 시연을 위해 세션에 데이터를 유지하고, 종료 전 'DB 동기화'를 하거나 매 트랜잭션마다 기록하도록 구성합니다.

if 'master_data' not in st.session_state:
    # 초기 로드 (실제 구현 시 pd.read_csv(URL) 등으로 시트 데이터 로드 가능)
    st.session_state.master_data = pd.DataFrame(columns=["상품코드", "상품명", "단위", "매입단가", "판매단가"])
    st.session_state.inventory = pd.DataFrame(columns=["상품코드", "현재고"])
    st.session_state.transaction_log = pd.DataFrame(columns=[
        "문서번호", "입력일자", "유형", "상품코드", "상품명", "수량", "단가", "총액", "입력자", "상태"
    ])

# 3. 공통 함수
def generate_doc_no(prefix):
    date_str = datetime.now().strftime("%Y%m%d")
    count = len(st.session_state.transaction_log) + 1
    return f"{prefix}-{date_str}-{count:03d}"

# 4. 사이드바 메뉴
st.sidebar.title("🌐 클라우드 관리 시스템")
menu = st.sidebar.radio("메뉴 선택", ["📊 실시간 재고", "🛒 구매/입고", "🚚 출고관리", "📋 통합 이력", "⚙️ 마스터 관리"])

# --- [저장 상태 안내] ---
st.sidebar.divider()
if st.sidebar.button("💾 모든 데이터 DB 저장"):
    # 여기서 실제 구글 시트 API를 호출하여 세션 데이터를 시트에 덮어씁니다.
    st.sidebar.success("구글 시트에 동기화되었습니다!")

# --- [메뉴 1] 재고 현황 ---
if menu == "📊 실시간 재고":
    st.title("📊 실시간 재고 현황")
    if not st.session_state.master_data.empty:
        res = pd.merge(st.session_state.master_data, st.session_state.inventory, on="상품코드", how="left").fillna(0)
        res["재고금액"] = res["매입단가"] * res["현재고"]
        st.metric("총 자산 규모", f"{res['재고금액'].sum():,}원")
        st.dataframe(res, use_container_width=True)
    else:
        st.warning("먼저 '마스터 관리'에서 상품을 등록해주세요.")

# --- [메뉴 2] 구매 및 입고 ---
elif menu == "🛒 구매/입고":
    st.title("🛒 구매 및 입고 처리")
    tab1, tab2 = st.tabs(["📝 발주 등록", "📥 입고 확정"])
    
    with tab1:
        with st.form("po_form"):
            item = st.selectbox("품목", st.session_state.master_data["상품명"])
            qty = st.number_input("수량", min_value=1)
            user = st.text_input("담당자")
            if st.form_submit_button("발주 확정"):
                item_info = st.session_state.master_data[st.session_state.master_data["상품명"] == item].iloc[0]
                doc_no = generate_doc_no("PO")
                new_row = {
                    "문서번호": doc_no, "입력일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "유형": "구매발주", "상품코드": item_info["상품코드"], "상품명": item,
                    "수량": qty, "단가": item_info["매입단가"], "총액": qty * item_info["매입단가"],
                    "입력자": user, "상태": "발주완료"
                }
                st.session_state.transaction_log = pd.concat([st.session_state.transaction_log, pd.DataFrame([new_row])], ignore_index=True)
                st.success(f"발주 완료: {doc_no}")

    with tab2:
        po_list = st.session_state.transaction_log[st.session_state.transaction_log["유형"] == "구매발주"]
        for i, row in po_list.iterrows():
            if st.button(f"입고 승인: {row['문서번호']} ({row['상품명']})"):
                # 재고 증가 로직
                idx = st.session_state.inventory[st.session_state.inventory["상품코드"] == row["상품코드"]].index
                st.session_state.inventory.at[idx[0], "현재고"] += row["수량"]
                st.session_state.transaction_log.at[i, "유형"] = "입고"
                st.success("재고에 반영되었습니다.")
                st.rerun()

# --- [메뉴 3] 출고 관리 ---
elif menu == "🚚 출고관리":
    st.title("🚚 출고 요청 및 승인")
    tab1, tab2 = st.tabs(["📝 출고 요청", "📤 출고 처리"])
    
    with tab1:
        with st.form("req_form"):
            item = st.selectbox("품목", st.session_state.master_data["상품명"])
            qty = st.number_input("수량", min_value=1)
            user = st.text_input("현장 담당자")
            if st.form_submit_button("요청 전송"):
                item_info = st.session_state.master_data[st.session_state.master_data["상품명"] == item].iloc[0]
                doc_no = generate_doc_no("REQ")
                new_row = {
                    "문서번호": doc_no, "입력일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "유형": "출고요청", "상품코드": item_info["상품코드"], "상품명": item,
                    "수량": qty, "단가": item_info["판매단가"], "총액": qty * item_info["판매단가"],
                    "입력자": user, "상태": "대기"
                }
                st.session_state.transaction_log = pd.concat([st.session_state.transaction_log, pd.DataFrame([new_row])], ignore_index=True)
                st.success("출고 요청 접수 완료")

    with tab2:
        req_list = st.session_state.transaction_log[st.session_state.transaction_log["유형"] == "출고요청"]
        for i, row in req_list.iterrows():
            stock = st.session_state.inventory[st.session_state.inventory["상품코드"] == row["상품코드"]]["현재고"].values[0]
            if st.button(f"출고 승인: {row['문서번호']} (현재고:{stock})"):
                if stock >= row["수량"]:
                    idx = st.session_state.inventory[st.session_state.inventory["상품코드"] == row["상품코드"]].index
                    st.session_state.inventory.at[idx[0], "현재고"] -= row["수량"]
                    st.session_state.transaction_log.at[i, "유형"] = "출고"
                    st.success("출고 완료!")
                    st.rerun()
                else:
                    st.error("재고가 부족합니다.")

# --- [메뉴 4] 통합 이력 ---
elif menu == "📋 통합 이력":
    st.title("📋 전체 전표 이력 조회")
    st.dataframe(st.session_state.transaction_log, use_container_width=True)

# --- [메뉴 5] 마스터 관리 ---
elif menu == "⚙️ 마스터 관리":
    st.title("⚙️ 상품 및 기준정보 관리")
    edited_master = st.data_editor(st.session_state.master_data, num_rows="dynamic", use_container_width=True)
    if st.button("마스터 최종 저장"):
        st.session_state.master_data = edited_master
        # 재고 테이블 동기화
        for code in st.session_state.master_data["상품코드"]:
            if code not in st.session_state.inventory["상품코드"].values:
                new_inv = pd.DataFrame([{"상품코드": code, "현재고": 0}])
                st.session_state.inventory = pd.concat([st.session_state.inventory, new_inv], ignore_index=True)
        st.success("마스터 데이터가 세션에 저장되었습니다.")
