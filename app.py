import streamlit as st
import pandas as pd
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="통합 발주/재고 관리 시스템", layout="wide")

# 2. 세션 상태 데이터 초기화 (서버 실행 시 1회 설정)
if 'master' not in st.session_state:
    # 상품 마스터 정보
    st.session_state.master = pd.DataFrame([
        {"상품코드": "G-101", "상품명": "강화유리 5T", "단가": 25000},
        {"상품코드": "G-102", "상품명": "복층유리 16T", "단가": 45000},
        {"상품코드": "I-201", "상품명": "알루미늄 샷시", "단가": 12000}
    ])

if 'inventory' not in st.session_state:
    # 현재 실재고 현황
    st.session_state.inventory = pd.DataFrame([
        {"상품코드": "G-101", "현재고": 100},
        {"상품코드": "G-102", "현재고": 50},
        {"상품코드": "I-201", "현재고": 200}
    ])

if 'orders' not in st.session_state:
    # 발주 및 입고 이력 (Inbound)
    st.session_state.orders = pd.DataFrame(columns=["일시", "유형", "상품코드", "수량", "상태"])

if 'outbounds' not in st.session_state:
    # 출고 요청 및 처리 이력 (Outbound)
    st.session_state.outbounds = pd.DataFrame(columns=["일시", "상품코드", "요청수량", "담당자", "상태"])

# 3. 사이드바 메뉴 구성
st.sidebar.title("🏢 SCM 관리 센터")
menu = st.sidebar.radio("업무 프로세스", 
    ["📊 대시보드", "🛒 발주 요청/입고", "🚚 출고 요청/처리", "📋 전체 이력 조회"])

# --- 공통 함수: 재고 업데이트 ---
def update_stock(code, qty):
    idx = st.session_state.inventory[st.session_state.inventory["상품코드"] == code].index
    st.session_state.inventory.at[idx[0], "현재고"] += qty

# --- [메뉴 1] 대시보드 (재고 현황) ---
if menu == "📊 대시보드":
    st.title("📊 실시간 재고 현황")
    # 마스터 정보와 재고 합쳐서 표시
    status_df = pd.merge(st.session_state.master, st.session_state.inventory, on="상품코드")
    status_df["재고금액"] = status_df["단가"] * status_df["현재고"]
    
    col1, col2 = st.columns(2)
    col1.metric("총 재고 자산", f"{status_df['재고금액'].sum():,}원")
    col2.metric("관리 품목 수", len(status_df))
    
    st.table(status_df.style.format({"단가": "{:,}", "현재고": "{:,}", "재고금액": "{:,}"}))

# --- [메뉴 2] 발주 요청 및 입고 처리 ---
elif menu == "🛒 발주 요청/입고":
    st.title("🛒 발주 및 입고 관리")
    
    with st.expander("➕ 신규 발주(입고) 등록", expanded=True):
        with st.form("inbound_form"):
            item = st.selectbox("품목 선택", st.session_state.master["상품명"])
            item_code = st.session_state.master[st.session_state.master["상품명"] == item]["상품코드"].values[0]
            qty = st.number_input("입고 수량", min_value=1)
            if st.form_submit_button("입고 확정"):
                # 1. 재고 반영
                update_stock(item_code, qty)
                # 2. 이력 기록
                new_log = {"일시": datetime.now().strftime("%Y-%m-%d %H:%M"), "유형": "입고", 
                           "상품코드": item_code, "수량": qty, "상태": "완료"}
                st.session_state.orders = pd.concat([st.session_state.orders, pd.DataFrame([new_log])], ignore_index=True)
                st.success(f"{item} {qty}개 입고 완료!")
                st.rerun()

# --- [메뉴 3] 출고 요청 및 처리 ---
elif menu == "🚚 출고 요청/처리":
    st.title("🚚 출고 관리 프로세스")
    
    tab1, tab2 = st.tabs(["📝 출고 요청", "✅ 출고 승인/처리"])
    
    with tab1:
        with st.form("outbound_form"):
            item = st.selectbox("출고 품목 선택", st.session_state.master["상품명"])
            item_code = st.session_state.master[st.session_state.master["상품명"] == item]["상품코드"].values[0]
            qty = st.number_input("요청 수량", min_value=1)
            person = st.text_input("요청자명")
            if st.form_submit_button("출고 요청 전송"):
                new_req = {"일시": datetime.now().strftime("%Y-%m-%d %H:%M"), "상품코드": item_code, 
                           "요청수량": qty, "담당자": person, "상태": "대기"}
                st.session_state.outbounds = pd.concat([st.session_state.outbounds, pd.DataFrame([new_req])], ignore_index=True)
                st.success("출고 요청이 대기 리스트에 등록되었습니다.")

    with tab2:
        pending = st.session_state.outbounds[st.session_state.outbounds["상태"] == "대기"]
        if not pending.empty:
            for i, row in pending.iterrows():
                # 현재고 확인
                cur_stock = st.session_state.inventory[st.session_state.inventory["상품코드"] == row["상품코드"]]["현재고"].values[0]
                st.warning(f"[{row['상품코드']}] 요청수량: {row['요청수량']} / 현재고: {cur_stock}")
                
                if st.button(f"승인 및 출고 (No.{i})"):
                    if cur_stock >= row["요청수량"]:
                        update_stock(row["상품코드"], -row["요청수량"]) # 재고 차감
                        st.session_state.outbounds.at[i, "상태"] = "출고완료"
                        st.success("출고가 처리되었습니다.")
                        st.rerun()
                    else:
                        st.error("재고가 부족합니다!")
        else:
            st.info("처리할 대기 요청이 없습니다.")

# --- [메뉴 4] 전체 이력 조회 ---
elif menu == "📋 전체 이력 조회":
    st.title("📋 통합 거래 이력")
    st.subheader("📥 입고(발주) 이력")
    st.dataframe(st.session_state.orders, use_container_width=True)
    
    st.subheader("📤 출고 이력")
    st.dataframe(st.session_state.outbounds, use_container_width=True)
