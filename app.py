import streamlit as st
import pandas as pd
from datetime import datetime

# 1. 페이지 설정 및 스타일
st.set_page_config(page_title="클라우드 통합 발주 시스템", layout="wide")

# 2. 데이터 초기화 (실제 운영 시에는 구글 시트나 DB 연결 권장)
if 'inventory' not in st.session_state:
    st.session_state.inventory = pd.DataFrame([
        {"품목코드": "G-001", "품목명": "강화유리 A형", "현재고": 50, "단가": 15000},
        {"품목코드": "F-002", "품목명": "알루미늄 프레임", "현재고": 120, "단가": 8000},
        {"품목코드": "P-003", "품목명": "고무 패킹", "현재고": 300, "단가": 2500}
    ])

if 'order_history' not in st.session_state:
    st.session_state.order_history = pd.DataFrame(columns=["일자", "품목명", "수량", "총액", "담당자"])

# 3. 사이드바 메뉴
menu = st.sidebar.selectbox("메뉴 선택", ["재고 현황", "신규 발주 등록", "발주 이력"])

# --- 메뉴 1: 재고 현황 ---
if menu == "재고 현황":
    st.title("📦 실시간 재고 대시보드")
    
    # 상단 요약 지표
    col1, col2, col3 = st.columns(3)
    col1.metric("전체 품목", len(st.session_state.inventory))
    col2.metric("재고 총액", f"{sum(st.session_state.inventory['현재고'] * st.session_state.inventory['단가']):,}원")
    col3.metric("금일 발주건", len(st.session_state.order_history))

    st.subheader("상세 재고 리스트")
    st.dataframe(st.session_state.inventory, use_container_width=True)

# --- 메뉴 2: 신규 발주 등록 ---
elif menu == "신규 발주 등록":
    st.title("📝 신규 발주 입력")
    
    with st.form("order_form", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        with col_a:
            item_name = st.selectbox("품목 선택", st.session_state.inventory["품목명"])
            manager = st.text_input("담당자 성함")
        with col_b:
            order_qty = st.number_input("발주 수량", min_value=1, step=1)
            
        # 선택한 품목의 단가 가져오기
        unit_price = st.session_state.inventory.loc[st.session_state.inventory["품목명"] == item_name, "단가"].values[0]
        total_price = unit_price * order_qty
        
        st.info(f"선택 품목 단가: {unit_price:,}원 | **예상 총액: {total_price:,}원**")
        
        submit = st.form_submit_button("발주 확정 및 재고 반영")
        
        if submit:
            if manager:
                # 재고 수량 업데이트 (입고 처리)
                idx = st.session_state.inventory[st.session_state.inventory["품목명"] == item_name].index
                st.session_state.inventory.at[idx[0], "현재고"] += order_qty
                
                # 발주 이력 추가
                new_order = {
                    "일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "품목명": item_name,
                    "수량": order_qty,
                    "총액": f"{total_price:,}원",
                    "담당자": manager
                }
                st.session_state.order_history = pd.concat([st.session_state.order_history, pd.DataFrame([new_order])], ignore_index=True)
                
                st.success(f"✅ {item_name} {order_qty}개 발주 완료! 재고에 반영되었습니다.")
            else:
                st.error("담당자 성함을 입력해주세요.")

# --- 메뉴 3: 발주 이력 ---
elif menu == "발주 이력":
    st.title("📜 전체 발주 기록")
    if len(st.session_state.order_history) > 0:
        st.table(st.session_state.order_history)
    else:
        st.write("아직 발생한 발주 내역이 없습니다.")
