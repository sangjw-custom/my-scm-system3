import streamlit as st
import pandas as pd
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="Firestore SCM System", layout="wide")

# 2. Firestore 연결 설정 (Secrets 사용)
@st.cache_resource
def get_db():
    key_dict = st.secrets["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = get_db()

# --- [공통 데이터 처리 함수] ---
def get_collection_df(collection_name):
    docs = db.collection(collection_name).stream()
    data = [doc.to_dict() for doc in docs]
    return pd.DataFrame(data) if data else pd.DataFrame()

def generate_doc_no(prefix):
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

# 3. 사이드바 메뉴
st.sidebar.title("🔥 Firestore Cloud SCM")
menu = st.sidebar.radio("메뉴 선택", 
    ["📊 실시간 재고", "🛒 구매 및 입고", "🚚 출고 관리", "📋 통합 이력 조회", "⚙️ 마스터 관리"])

# 데이터 로드
master_df = get_collection_df("master")
inv_df = get_collection_df("inventory")
log_df = get_collection_df("log")

# --- [메뉴 1] 실시간 재고 ---
if menu == "📊 실시간 재고":
    st.title("📊 실시간 재고 및 자산 현황")
    if not master_df.empty and not inv_df.empty:
        res = pd.merge(master_df, inv_df, on="상품코드", how="left").fillna(0)
        res["재고금액"] = res["매입단가"] * res["현재고"]
        
        c1, c2 = st.columns(2)
        c1.metric("총 자산 규모", f"{res['재고금액'].sum():,}원")
        c2.metric("품목 수", len(res))
        st.dataframe(res, use_container_width=True)
    else:
        st.info("데이터가 없습니다. 마스터 등록 및 입고를 먼저 진행하세요.")

# --- [메뉴 2] 구매 및 입고 ---
elif menu == "🛒 구매 및 입고":
    st.title("🛒 구매 및 입고 관리")
    t1, t2 = st.tabs(["📝 신규 발주", "📥 입고 확정"])
    
    with t1:
        if not master_df.empty:
            with st.form("po_form", clear_on_submit=True):
                item_name = st.selectbox("품목 선택", master_df["상품명"])
                qty = st.number_input("발주 수량", min_value=1)
                user = st.text_input("담당자")
                if st.form_submit_button("발주서 발행"):
                    item_info = master_df[master_df["상품명"] == item_name].iloc[0]
                    doc_no = generate_doc_no("PO")
                    data = {
                        "문서번호": doc_no, "입력일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "유형": "구매발주", "상품코드": item_info["상품코드"], "상품명": item_name,
                        "수량": qty, "단가": item_info["매입단가"], "총액": qty * item_info["매입단가"],
                        "입력자": user, "상태": "발주완료"
                    }
                    db.collection("log").document(doc_no).set(data)
                    st.success(f"발주 완료: {doc_no}")
                    st.rerun()
        else:
            st.warning("마스터 데이터를 먼저 등록하세요.")

    with t2:
        if not log_df.empty:
            pending = log_df[log_df["유형"] == "구매발주"]
            for _, row in pending.iterrows():
                if st.button(f"입고 확정: {row['문서번호']} ({row['상품명']})"):
                    # 재고 업데이트
                    inv_ref = db.collection("inventory").document(row["상품코드"])
                    inv_doc = inv_ref.get()
                    new_stock = (inv_doc.to_dict().get("현재고", 0) if inv_doc.exists else 0) + row["수량"]
                    inv_ref.set({"상품코드": row["상품코드"], "현재고": new_stock})
                    # 로그 상태 변경
                    db.collection("log").document(row["문서번호"]).update({"유형": "입고"})
                    st.success("입고 처리가 완료되었습니다.")
                    st.rerun()

# --- [메뉴 3] 출고 관리 ---
elif menu == "🚚 출고 관리":
    st.title("🚚 출고 요청 및 승인")
    t1, t2 = st.tabs(["📝 출고 요청", "✅ 출고 승인"])
    
    with t1:
        if not master_df.empty:
            with st.form("req_form"):
                item_name = st.selectbox("출고 품목", master_df["상품명"])
                qty = st.number_input("요청 수량", min_value=1)
                user = st.text_input("요청자")
                if st.form_submit_button("요청 등록"):
                    item_info = master_df[master_df["상품명"] == item_name].iloc[0]
                    doc_no = generate_doc_no("REQ")
                    data = {
                        "문서번호": doc_no, "입력일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "유형": "출고요청", "상품코드": item_info["상품코드"], "상품명": item_name,
                        "수량": qty, "단가": item_info["판매단가"], "총액": qty * item_info["판매단가"],
                        "입력자": user, "상태": "대기"
                    }
                    db.collection("log").document(doc_no).set(data)
                    st.success("요청 완료")
                    st.rerun()

    with t2:
        if not log_df.empty:
            reqs = log_df[log_df["유형"] == "출고요청"]
            for _, row in reqs.iterrows():
                inv_ref = db.collection("inventory").document(row["상품코드"])
                inv_doc = inv_ref.get()
                cur_stock = inv_doc.to_dict().get("현재고", 0) if inv_doc.exists else 0
                
                if st.button(f"출고 승인: {row['문서번호']} (재고:{cur_stock})"):
                    if cur_stock >= row["수량"]:
                        inv_ref.update({"현재고": cur_stock - row["수량"]})
                        db.collection("log").document(row["문서번호"]).update({"유형": "출고", "상태": "출고완료"})
                        st.success("출고 처리 완료")
                        st.rerun()
                    else:
                        st.error("재고가 부족합니다.")

# --- [메뉴 4] 통합 이력 조회 ---
elif menu == "📋 통합 이력 조회":
    st.title("📋 전체 전표 이력")
    if not log_df.empty:
        st.dataframe(log_df.sort_values("입력일자", ascending=False), use_container_width=True)
    else:
        st.info("기록된 이력이 없습니다.")

# --- [메뉴 5] 마스터 관리 ---
elif menu == "⚙️ 마스터 관리":
    st.title("⚙️ 상품 마스터 관리")
    # Firestore는 Editor로 전체 덮어쓰기보다 개별 등록/수정이 안정적임
    with st.expander("➕ 신규 상품 추가"):
        with st.form("new_master"):
            c1, c2, c3 = st.columns(3)
            code = c1.text_input("상품코드")
            name = c2.text_input("상품명")
            unit = c3.text_input("단위")
            in_p = c1.number_input("매입단가", min_value=0)
            out_p = c2.number_input("판매단가", min_value=0)
            if st.form_submit_button("마스터 저장"):
                db.collection("master").document(code).set({
                    "상품코드": code, "상품명": name, "단위": unit, 
                    "매입단가": in_p, "판매단가": out_p
                })
                # 재고 초기화 (최초 1회)
                inv_ref = db.collection("inventory").document(code)
                if not inv_ref.get().exists:
                    inv_ref.set({"상품코드": code, "현재고": 0})
                st.success("등록 완료!")
                st.rerun()

    st.subheader("📋 현재 마스터 리스트")
    if not master_df.empty:
        st.table(master_df)
