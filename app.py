import streamlit as st
import pandas as pd
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="유리/인테리어 자재 통합 관리", layout="wide")

# 2. 마스터 데이터 및 상태 초기화
if 'master_data' not in st.session_state:
    # 상품 마스터 (수정 불가능한 기본 정보)
    st.session_state.master_data = pd.DataFrame([
        {"상품코드": "G-001", "상품명": "강화유리 5T", "규격": "1200*2400", "단가": 25000},
        {"상품코드": "G-002", "상품명": "복층유리 16T", "규격": "1000*1500", "단가": 45000},
        {"상품코드": "I-001", "상품명": "알루미늄 샷시", "규격": "블랙/3m", "단가": 12000}
    ])

if 'inventory' not in st.session_state:
    # 실시간 재고 데이터 (마스터 기반)
    st.session_state.inventory = pd.DataFrame([
        {"상품코드": "G-001", "현재고": 100, "안전재고": 20},
        {"상품코드": "G-002", "현재고": 50, "안전재고": 10},
        {"상품코드": "I-001", "현재고": 200, "안전재고": 30}
    ])

if 'outbound_requests' not in st.session_state:
    # 출고 요청 이력
    st.session_state.outbound_requests = pd.DataFrame(columns=["요청일시", "상품코드", "상품명", "요청수량", "담당자", "상태"])

# 3. 사이드바 메뉴
menu = st.sidebar.radio("업무 선택", ["📦 재고 및 마스터 조회", "📝 출고 요청 등록", "🚚 출고 처리(승인)"])

# --- 메뉴 1: 재고 및 마스터 조회 ---
if menu == "📦 재고 및 마스터 조회":
    st.title("📊 통합 재고 현황")
    # 마스터와 재고 합치기 (Join)
    display_df = pd.merge(st.session_state.master_data, st.session_state.inventory, on="상품코드")
    st.dataframe(display_df, use_container_width=True)

# --- 메뉴 2: 출고 요청 등록 ---
elif menu == "📝 출고 요청 등록":
    st.title("📝 현장 출고 요청")
    with st.form("request_form"):
        # 마스터 데이터에서 상품 선택
        selected_item_name = st.selectbox("출고 품목", st.session_state.master_data["상품명"])
        item_info = st.session_state.master_data[st.session_state.master_data["상품명"] == selected_item_name].iloc[0]
        
        req_qty = st.number_input("요청 수량", min_value=1)
        requester = st.text_input("요청자(현장담당)")
        
        if st.form_submit_button("출고 요청 전송"):
            new_req = {
                "요청일시": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "상품코드": item_info["상품코드"],
                "상품명": item_info["상품명"],
                "요청수량": req_qty,
                "담당자": requester,
                "상태": "대기"
            }
            st.session_state.outbound_requests = pd.concat([st.session_state.outbound_requests, pd.DataFrame([new_req])], ignore_index=True)
            st.success(f"[{item_info['상품명']}] 출고 요청이 접수되었습니다.")

# --- 메뉴 3: 출고 처리(승인) ---
elif menu == "🚚 출고 처리(승인)":
    st.title("🚚 출고 승인 및 재고 반영")
    pending_reqs = st.session_state.outbound_requests[st.session_state.outbound_requests["상태"] == "대기"]
    
    if len(pending_reqs) == 0:
        st.info("현재 대기 중인 출고 요청이 없습니다.")
    else:
        for i, row in pending_reqs.iterrows():
            with st.expander(f"요청번호 {i} : {row['상품명']} ({row['요청수량']}개)"):
                st.write(f"요청자: {row['담당자']} | 요청시간: {row['요청일시']}")
                
                # 재고 확인
                current_stock = st.session_state.inventory.loc[st.session_state.inventory["상품코드"] == row["상품코드"], "현재고"].values[0]
                st.write(f"현재 창고 재고: **{current_stock}**개")
                
                if current_stock >= row["요청수량"]:
                    if st.button(f"출고 승인 (ID:{i})"):
                        # 1. 재고 차감
                        idx = st.session_state.inventory[st.session_state.inventory["상품코드"] == row["상품코드"]].index
                        st.session_state.inventory.at[idx[0], "현재고"] -= row["요청수량"]
                        # 2. 상태 변경
                        st.session_state.outbound_requests.at[i, "상태"] = "출고완료"
                        st.success("재고가 차감되고 출고가 완료되었습니다.")
                        st.rerun()
                else:
                    st.error("재고가 부족하여 출고할 수 없습니다.")
