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
        # 마스터와 재고 합치기
        res = pd.merge(master_df, inv_df, on="상품코드", how="left").fillna(0)
        res["재고금액(매입가)"] = res["매입단가"] * res["현재고"]
        
        c1, c2 = st.columns(2)
        c1.metric("총 재고 자산", f"{int(res['재고금액(매입가)'].sum()):,}원")
        c2.metric("관리 품목 수", len(res))
        
        st.dataframe(res, use_container_width=True)
    else:
        st.info("마스터 관리 메뉴에서 상품을 먼저 등록해 주세요.")

# --- [메뉴 2
