import streamlit as st
import pandas as pd
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="Firestore Cloud SCM", layout="wide")

# 2. Firestore 연결 설정 (Secrets 사용)
@st.cache_resource
def get_db():
    # Streamlit Secrets에 등록된 정보를 가져옵니다.
    key_dict = st.secrets["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = get_db()

# --- [데이터 처리 유틸리티 함수] ---
def get_df(collection_name):
    """Firestore 컬렉션 데이터를 Pandas DataFrame으로 변환"""
    docs = db.collection(collection_name).stream()
    data = [doc.to_dict() for doc in docs]
    return pd.DataFrame(data) if data else pd.DataFrame()

def generate_doc_no(prefix):
    """문서 번호 자동 생성 (유형-날짜시분초)"""
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

# 3. 사이드바 메뉴 구성
st.sidebar.title("🏢 SCM 클라우드 센터")
menu = st.sidebar.radio("메뉴 선택", 
    ["📊 실시간 재고 현황", "🛒 구매 및 입고 관리", "🚚 출고 및 처리 관리", "📋 통합 거래 이력", "⚙️ 상품 마스터 관리"])

# 공통 데이터 미리 로드
master_df = get_df("master")
inv_df = get_df("inventory")
log_df = get_df("log")

# --- [메뉴 1] 실시간 재고 현황 ---
if menu == "📊 실시간 재고 현황":
st.title("📊 실시간 재고 및 자산 현황")
    if not master_df.empty:
        res = pd.merge(master_df, inv_df, on="상품코드", how="left").fillna(0)
        res["재고금액(매입가)"] = res["매입단가"] * res["현재고"]
        
        # 메트릭 표시 (포맷팅 적용)
        c1, c2 = st.columns(2)
        total_asset = int(res['재고금액(매입가)'].sum())
        c1.metric("총 재고 자산", f"{total_asset:,}원")
        c2.metric("관리 품목 수", f"{len(res):,}개")
        
        # 데이터프레임 스타일 설정
        st.dataframe(
            res, 
            use_container_width=True,
            column_config={
                "매입단가": st.column_config.NumberColumn("매입단가", format="%d"),
                "판매단가": st.column_config.NumberColumn("판매단가", format="%d"),
                "현재고": st.column_config.NumberColumn("현재고", format="%d"),
                "재고금액(매입가)": st.column_config.NumberColumn("재고금액(매입가)", format="%d"),
            }
        )
    else:
        st.info("마스터 관리 메뉴에서 상품을 먼저 등록해 주세요.")

# --- [메뉴 2] 구매 및 입고 관리 ---
elif menu == "🛒 구매 및 입고 관리":
    st.title("🛒 구매 및 입고 프로세스")
    t1, t2 = st.tabs(["📝 신규 구매발주", "📥 입고 확정 처리"])
    
    with t1:
        if not master_df.empty:
            with st.form("po_form", clear_on_submit=True):
                item_name = st.selectbox("품목 선택", master_df["상품명"])
                qty = st.number_input("발주 수량", min_value=1, step=1)
                user = st.text_input("입력자(발주자)")
                if st.form_submit_button("구매발주 등록"):
                    item_info = master_df[master_df["상품명"] == item_name].iloc[0]
                    doc_no = generate_doc_no("PO")
                    data = {
                            "문서번호": str(doc_no),
                            "입력일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "유형": "구매발주",
                            "상품코드": str(item_info["상품코드"]),
                            "상품명": str(item_name),
                            "수량": int(qty),
                            "단가": int(item_info["매입단가"]),
                            "총액": int(qty * item_info["매입단가"]),
                            "입력자": str(user),
                            "상태": "발주완료"
                        }
                    db.collection("log").document(doc_no).set(data)
                    st.success(f"발주 완료: {doc_no}")
                    st.rerun()
        else:
            st.warning("상품 마스터가 비어 있습니다.")

    with t2:
        if not log_df.empty:
            pending = log_df[log_df["유형"] == "구매발주"]
            if not pending.empty:
                for _, row in pending.iterrows():
                    col_a, col_b = st.columns([4, 1])
                    col_a.write(f"[{row['문서번호']}] {row['상품명']} / {row['수량']:,}개 (입력자: {row['입력자']})")
                    if col_b.button("입고승인", key=row['문서번호']):
                        # 1. 재고 증가
                        inv_ref = db.collection("inventory").document(row["상품코드"])
                        inv_doc = inv_ref.get()
                        cur_stock = inv_doc.to_dict().get("현재고", 0) if inv_doc.exists else 0
                        inv_ref.set({"상품코드": row["상품코드"], "현재고": cur_stock + row["수량"]})
                        # 2. 로그 업데이트
                        db.collection("log").document(row["문서번호"]).update({"유형": "입고", "상태": "입고완료"})
                        st.success(f"{row['상품명']} 입고 완료!")
                        st.rerun()
            else:
                st.info("입고 대기 중인 발주 건이 없습니다.")

# --- [메뉴 3] 출고 및 처리 관리 ---
elif menu == "🚚 출고 및 처리 관리":
    st.title("🚚 출고 관리 프로세스")
    t1, t2 = st.tabs(["📝 출고 요청 등록", "📤 출고 승인 처리"])
    
    with t1:
        if not master_df.empty:
            with st.form("req_form", clear_on_submit=True):
                item_name = st.selectbox("출고 품목", master_df["상품명"])
                qty = st.number_input("요청 수량", min_value=1, step=1)
                user = st.text_input("요청자")
                if st.form_submit_button("출고 요청"):
                    item_info = master_df[master_df["상품명"] == item_name].iloc[0]
                    doc_no = generate_doc_no("REQ")
                    data = {
                        "문서번호": doc_no, "입력일자": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "유형": "출고요청", "상품코드": item_info["상품코드"], "상품명": item_name,
                        "수량": qty, "단가": item_info["판매단가"], "총액": qty * item_info["판매단가"],
                        "입력자": user, "상태": "대기"
                    }
                    db.collection("log").document(doc_no).set(data)
                    st.success(f"출고 요청 완료: {doc_no}")
                    st.rerun()

    with t2:
        if not log_df.empty:
            reqs = log_df[log_df["유형"] == "출고요청"]
            if not reqs.empty:
                for _, row in reqs.iterrows():
                    inv_ref = db.collection("inventory").document(row["상품코드"])
                    inv_doc = inv_ref.get()
                    cur_stock = inv_doc.to_dict().get("현재고", 0) if inv_doc.exists else 0
                    
                    col_a, col_b = st.columns([4, 1])
                    col_a.write(f"[{row['문서번호']}] {row['상품명']} {row['수량']:,}개 (현재고: {cur_stock})")
                    if col_b.button("출고승인", key=row['문서번호']):
                        if cur_stock >= row["수량"]:
                            inv_ref.update({"현재고": cur_stock - row["수량"]})
                            db.collection("log").document(row["문서번호"]).update({"유형": "출고", "상태": "출고완료"})
                            st.success("출고 처리 완료!")
                            st.rerun()
                        else:
                            st.error("재고가 부족하여 출고할 수 없습니다.")
            else:
                st.info("대기 중인 출고 요청이 없습니다.")

# --- [메뉴 4] 통합 거래 이력 ---
elif menu == "📋 통합 거래 이력":
st.title("📋 전체 전표 및 거래 이력 조회")
    if not log_df.empty:
        log_df['sort_date'] = pd.to_datetime(log_df['입력일자'])
        display_log = log_df.sort_values("sort_date", ascending=False).drop(columns=['sort_date'])
        
        # 숫자 컬럼들에 대해 콤마 포맷 적용
        formatted_log = display_log.style.format({
            "수량": "{:,}",
            "단가": "{:,}",
            "총액": "{:,}"
        })
        
        st.dataframe(formatted_log, use_container_width=True)
    else:
        st.info("기록된 거래 이력이 없습니다.")

# --- [메뉴 5] 상품 마스터 관리 ---
elif menu == "⚙️ 상품 마스터 관리":
    st.title("⚙️ 상품 마스터 관리")
    
    with st.expander("➕ 신규 상품 등록", expanded=True):
        with st.form("master_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            code = c1.text_input("상품코드 (중복불가)")
            name = c2.text_input("상품명")
            unit = c3.selectbox("단위", ["EA", "m", "kg", "box", "set", "m2", "MAE"])
            in_price = c1.number_input("매입단가", min_value=0, step=100)
            out_price = c2.number_input("판매단가", min_value=0, step=100)
            
            if st.form_submit_button("상품 저장"):
                if code and name:
                    # 마스터 데이터 저장
                    db.collection("master").document(code).set({
                        "상품코드": code, "상품명": name, "단위": unit,
                        "매입단가": in_price, "판매단가": out_price
                    })
                    # 재고 데이터 초기화 (해당 상품코드로 재고 문서가 없을 때만 0으로 생성)
                    inv_ref = db.collection("inventory").document(code)
                    if not inv_ref.get().exists:
                        inv_ref.set({"상품코드": code, "현재고": 0})
                    
                    st.success(f"상품 '{name}' 등록 완료!")
                    st.rerun()
                else:
                    st.error("상품코드와 상품명은 필수 입력 항목입니다.")

    st.subheader("📋 등록된 상품 리스트")
    if not master_df.empty:
        st.table(master_df)
    else:
        st.info("등록된 상품이 없습니다.")
        
