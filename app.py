import streamlit as st
import pandas as pd
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="통합 SCM 관리 시스템", layout="wide")

# 2. 데이터 초기화 (세션 상태)
if 'master_data' not in st.session_state:
    st.session_state.master_data = pd.DataFrame([

    ])

if 'inventory' not in st.session_state:
    st.session_state.inventory = pd.DataFrame([

    ])

if 'transaction_log' not in st.session_state:
    # 모든 전표 데이터를 통합 관리하는 로그 (유형: 구매발주, 입고, 출고요청, 출고)
    st.session_state.transaction_log = pd.DataFrame(columns=[
        "문서번호", "입력일자", "유형", "상품코드", "상품명", "수량", "단가", "총액", "입력자", "상태"
    ])

# 3. 공통 함수: 문서번호 생성
def generate_doc_no(prefix):
    date_str = datetime.now().strftime("%Y%m%d")
    count = len(st.session_state.transaction_log) + 1
    return f"{prefix}-{date_str}-{count:03d}"

# 4. 사이드바 메뉴
st.sidebar.title("🏢 업무 프로세스")
menu = st.sidebar.radio("메뉴 선택", ["📊 재고 현황", "🛒 구매발주 및 입고", "🚚 출고요청 및 출고", "⚙️ 상품 마스터 관리"])

# --- [메뉴 1] 재고 현황 ---
if menu == "📊 재고 현황":
    st.title("📊 실시간 재고 및 자산 현황")
    res = pd.merge(st.session_state.master_data, st.session_state.inventory, on="상품코드")
    res["재고금액(매입가)"] = res["매입단가"] * res["현재고"]
    
    col1, col2 = st.columns(2)
    col1.metric("총 재고 자산", f"{res['재고금액(매입가)'].sum():,}원")
    col2.metric("관리 품목", len(res))
    
    st.dataframe(res, use_container_width=True)

# --- [메뉴 2] 구매발주 및 입고 ---
elif menu == "🛒 구매발주 및 입고":
    st.title("🛒 구매 및 입고 관리")
    
    tab1, tab2 = st.tabs(["📝 신규 구매발주", "📥 입고 처리(승인)"])
    
    with tab1:
        with st.form("po_form", clear_on_submit=True):
            st.subheader("발주서 작성")
            col1, col2 = st.columns(2)
            with col1:
                item_name = st.selectbox("발주 품목", st.session_state.master_data["상품명"])
                qty = st.number_input("발주 수량", min_value=1)
            with col2:
                user_name = st.text_input("입력자(발주자)")
            
            if st.form_submit_button("구매발주 등록"):
                item_info = st.session_state.master_data[st.session_state.master_data["상품명"] == item_name].iloc[0]
                doc_no = generate_doc_no("PO")
                new_log = {
                    "문서번호": doc_no, "입력일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "유형": "구매발주", "상품코드": item_info["상품코드"], "상품명": item_name,
                    "수량": qty, "단가": item_info["매입단가"], "총액": qty * item_info["매입단가"],
                    "입력자": user_name, "상태": "발주완료"
                }
                st.session_state.transaction_log = pd.concat([st.session_state.transaction_log, pd.DataFrame([new_log])], ignore_index=True)
                st.success(f"발주 등록 완료: {doc_no}")

    with tab2:
        st.subheader("입고 대기 목록")
        po_list = st.session_state.transaction_log[st.session_state.transaction_log["유형"] == "구매발주"]
        if not po_list.empty:
            for i, row in po_list.iterrows():
                if st.button(f"입고 확정 ({row['문서번호']})"):
                    # 재고 반영
                    idx = st.session_state.inventory[st.session_state.inventory["상품코드"] == row["상품코드"]].index
                    st.session_state.inventory.at[idx[0], "현재고"] += row["수량"]
                    # 로그 업데이트 (유형 변경 혹은 상태변경 가능하나 여기선 입고 로그 생성)
                    st.session_state.transaction_log.at[i, "유형"] = "입고"
                    st.session_state.transaction_log.at[i, "입력일자"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    st.success(f"{row['상품명']} {row['수량']}개 입고 처리되었습니다.")
                    st.rerun()

# --- [메뉴 3] 출고요청 및 출고 ---
elif menu == "🚚 출고요청 및 출고":
    st.title("🚚 출고 관리")
    
    tab1, tab2 = st.tabs(["📝 출고 요청 등록", "📤 출고 승인/처리"])
    
    with tab1:
        with st.form("out_form", clear_on_submit=True):
            item_name = st.selectbox("출고 품목", st.session_state.master_data["상품명"])
            qty = st.number_input("요청 수량", min_value=1)
            user_name = st.text_input("입력자(요청자)")
            
            if st.form_submit_button("출고 요청 전송"):
                item_info = st.session_state.master_data[st.session_state.master_data["상품명"] == item_name].iloc[0]
                doc_no = generate_doc_no("REQ")
                new_log = {
                    "문서번호": doc_no, "입력일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "유형": "출고요청", "상품코드": item_info["상품코드"], "상품명": item_name,
                    "수량": qty, "단가": item_info["판매단가"], "총액": qty * item_info["판매단가"],
                    "입력자": user_name, "상태": "대기"
                }
                st.session_state.transaction_log = pd.concat([st.session_state.transaction_log, pd.DataFrame([new_log])], ignore_index=True)
                st.success(f"요청 등록 완료: {doc_no}")

    with tab2:
        req_list = st.session_state.transaction_log[st.session_state.transaction_log["유형"] == "출고요청"]
        for i, row in req_list.iterrows():
            cur_stock = st.session_state.inventory[st.session_state.inventory["상품코드"] == row["상품코드"]]["현재고"].values[0]
            st.info(f"문서: {row['문서번호']} | 품목: {row['상품명']} | 요청: {row['수량']} (현재고: {cur_stock})")
            if st.button(f"출고 승인 (ID:{i})"):
                if cur_stock >= row["수량"]:
                    idx = st.session_state.inventory[st.session_state.inventory["상품코드"] == row["상품코드"]].index
                    st.session_state.inventory.at[idx[0], "현재고"] -= row["수량"]
                    st.session_state.transaction_log.at[i, "유형"] = "출고"
                    st.session_state.transaction_log.at[i, "상태"] = "출고완료"
                    st.success("출고 처리가 완료되었습니다.")
                    st.rerun()
                else:
                    st.error("재고가 부족합니다.")

# --- [메뉴 4] 마스터 관리 ---
elif menu == "⚙️ 상품 마스터 관리":
    st.title("⚙️ 상품 마스터 관리")
    # (이전 단계에서 만든 마스터 관리 코드 포함)
    new_master = st.data_editor(st.session_state.master_data, num_rows="dynamic", use_container_width=True)
    if st.button("마스터 정보 저장"):
        st.session_state.master_data = new_master
        # 재고 테이블에도 없는 코드가 있으면 추가
        for code in st.session_state.master_data["상품코드"]:
            if code not in st.session_state.inventory["상품코드"].values:
                new_inv = pd.DataFrame([{"상품코드": code, "현재고": 0}])
                st.session_state.inventory = pd.concat([st.session_state.inventory, new_inv], ignore_index=True)
        st.success("마스터 정보가 반영되었습니다.")
