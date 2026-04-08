import streamlit as st
import pandas as pd
from google.cloud import firestore
from google.oauth2 import service_account
import json
from datetime import datetime
import pytz
import io

# --- 1. 환경 설정 및 DB 연결 ---
st.set_page_config(page_title="클라우드 SCM 시스템", layout="wide")

# 한국 시간 설정 함수
def get_now_kst():
    return datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M')

# 엑셀 변환 함수
def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# Firestore 연결
if "db" not in st.session_state:
    key_dict = json.loads(st.secrets["textkey"])
    creds = service_account.Credentials.from_service_account_info(key_dict)
    st.session_state.db = firestore.Client(credentials=creds)

db = st.session_state.db

# --- 2. 데이터 로드 함수 ---
def load_data(collection_name):
    docs = db.collection(collection_name).stream()
    data = [doc.to_dict() for doc in docs]
    return pd.DataFrame(data)

def generate_doc_no(prefix):
    kst_now = datetime.now(pytz.timezone('Asia/Seoul'))
    return f"{prefix}-{kst_now.strftime('%Y%m%d%H%M%S')}"

# 데이터 실시간 로드
master_df = load_data("master")
log_df = load_data("log")
inv_df = load_data("inventory")

# --- 3. 사이드바 메뉴 ---
st.sidebar.title("📦 SCM 매니저")
menu = st.sidebar.radio("메뉴 선택", [
    "📊 실시간 재고 현황", 
    "🛒 구매 및 입고 관리", 
    "🚚 출고 및 처리 관리", 
    "📋 통합 거래 이력", 
    "⚙️ 상품 마스터 관리"
])

# --- [메뉴 1] 실시간 재고 현황 ---
if menu == "📊 실시간 재고 현황":
    st.title("📊 실시간 재고 및 자산 현황")
    if not master_df.empty:
        res = pd.merge(master_df, inv_df, on="상품코드", how="left").fillna(0)
        
        # 숫자형 변환 및 계산
        num_cols = ["매입단가", "판매단가", "현재고"]
        for col in num_cols:
            res[col] = pd.to_numeric(res[col], errors='coerce').fillna(0).astype(int)
        res["재고금액(매입가)"] = res["매입단가"] * res["현재고"]
        
        # 열 순서 조정
        ordered_cols = ["상품코드", "상품유형", "상품명", "단위", "판매단가", "매입단가", "현재고", "재고금액(매입가)"]
        res = res[ordered_cols]
        
        # 요약 지표
        c1, c2 = st.columns(2)
        total_asset = int(res['재고금액(매입가)'].sum())
        c1.metric("총 재고 자산", f"{total_asset:,}원")
        c2.metric("관리 품목 수", f"{len(res):,}개")
        
        # 데이터프레임 출력
        st.dataframe(res.style.format({
            "판매단가": "{:,}", "매입단가": "{:,}", "현재고": "{:,}", "재고금액(매입가)": "{:,}"
        }), use_container_width=True, hide_index=True)
        
        # 엑셀 다운로드
        st.download_button("📥 재고현황 엑셀 다운로드", convert_df_to_excel(res), f"재고현황_{get_now_kst()}.xlsx")
    else:
        st.info("마스터 데이터를 등록해주세요.")

# --- [메뉴 2] 구매 및 입고 관리 ---
elif menu == "🛒 구매 및 입고 관리":
    st.title("🛒 구매 및 입고 관리")
    t1, t2 = st.tabs(["🆕 신규 구매발주", "📥 입고 확정 처리"])
    
    with t1:
        if not master_df.empty:
            with st.form("po_form", clear_on_submit=True):
                item_name = st.selectbox("발주 품목", master_df["상품명"])
                qty = st.number_input("발주 수량", min_value=1, step=1)
                user = st.text_input("발주 담당자")
                if st.form_submit_button("구매발주 등록"):
                    item_info = master_df[master_df["상품명"] == item_name].iloc[0]
                    doc_no = generate_doc_no("PO")
                    data = {
                        "문서번호": doc_no, "입력일자": get_now_kst(), "유형": "구매발주",
                        "상품코드": str(item_info["상품코드"]), "상품명": str(item_name),
                        "수량": int(qty), "단가": int(item_info["매입단가"]),
                        "총액": int(qty * item_info["매입단가"]), "입력자": str(user), "상태": "발주완료"
                    }
                    db.collection("log").document(doc_no).set(data)
                    st.success(f"발주 완료: {doc_no}"); st.rerun()
    
    with t2:
        st.subheader("📥 입고 대기 목록")
        pending = log_df[log_df["유형"] == "구매발주"].copy() if not log_df.empty else pd.DataFrame()
        if not pending.empty:
            cols = st.columns([1.5, 2, 1, 2, 1.5, 1.5])
            headers = ["문서번호", "상품명", "수량", "발주일자", "발주자", "액션"]
            for col, h in zip(cols, headers): col.write(f"**{h}**")
            st.divider()
            for _, row in pending.iterrows():
                r = st.columns([1.5, 2, 1, 2, 1.5, 1.5])
                r[0].write(row['문서번호']); r[1].write(row['상품명'])
                r[2].write(f"{int(row['수량']):,}"); r[3].write(row['입력일자']); r[4].write(row.get('입력자','-'))
                if r[5].button("✅ 입고", key=row['문서번호']):
                    inv_ref = db.collection("inventory").document(row["상품코드"])
                    cur = inv_ref.get().to_dict().get("현재고", 0) if inv_ref.get().exists else 0
                    inv_ref.set({"상품코드": row["상품코드"], "현재고": int(cur) + int(row["수량"])})
                    db.collection("log").document(row["문서번호"]).update({"유형": "입고", "확정일자": get_now_kst()})
                    st.rerun()

# --- [메뉴 3] 출고 및 처리 관리 ---
elif menu == "🚚 출고 및 처리 관리":
    st.title("🚚 출고 및 처리 관리")
    t1, t2 = st.tabs(["📤 출고 요청 등록", "✅ 출고 승인 처리"])
    
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
                        "문서번호": doc_no, "입력일자": get_now_kst(), "유형": "출고요청",
                        "상품코드": str(item_info["상품코드"]), "상품명": str(item_name),
                        "수량": int(qty), "단가": int(item_info["판매단가"]),
                        "총액": int(qty * item_info["판매단가"]), "입력자": str(user), "상태": "대기"
                    }
                    db.collection("log").document(doc_no).set(data)
                    st.success("요청 완료"); st.rerun()

    with t2:
        st.subheader("📤 출고 대기 및 승인")
        reqs = log_df[log_df["유형"] == "출고요청"].copy() if not log_df.empty else pd.DataFrame()
        if not reqs.empty:
            cols = st.columns([1.5, 2, 0.8, 0.8, 1.8, 1.2, 1.2])
            headers = ["문서번호", "상품명", "요청", "재고", "요청일자", "요청자", "액션"]
            for col, h in zip(cols, headers): col.write(f"**{h}**")
            st.divider()
            for _, row in reqs.iterrows():
                inv_ref = db.collection("inventory").document(row["상품코드"])
                cur_stock = int(inv_ref.get().to_dict().get("현재고", 0)) if inv_ref.get().exists else 0
                r = st.columns([1.5, 2, 0.8, 0.8, 1.8, 1.2, 1.2])
                r[0].write(row['문서번호']); r[1].write(row['상품명']); r[2].write(f"{int(row['수량']):,}")
                r[3].write(f":red[{cur_stock:,}]" if cur_stock < int(row["수량"]) else f"{cur_stock:,}")
                r[4].write(row['입력일자']); r[5].write(row.get('입력자','-'))
                if cur_stock >= int(row["수량"]):
                    if r[6].button("🚚 승인", key=row['문서번호']):
                        inv_ref.update({"현재고": cur_stock - int(row["수량"])})
                        db.collection("log").document(row["문서번호"]).update({"유형": "출고", "확정일자": get_now_kst()})
                        st.rerun()
                else: r[6].button("⚠️ 부족", key=row['문서번호'], disabled=True)

# --- [메뉴 4] 통합 거래 이력 ---
elif menu == "📋 통합 거래 이력":
    st.title("📋 통합 거래 이력")
    if not log_df.empty:
        log_df = log_df.sort_values("입력일자", ascending=False)
        st.dataframe(log_df.style.format({"수량": "{:,}", "단가": "{:,}", "총액": "{:,}"}), use_container_width=True)
        st.download_button("📥 이력 엑셀 다운로드", convert_df_to_excel(log_df), "거래이력.xlsx")

# --- [메뉴 5] 상품 마스터 관리 ---
elif menu == "⚙️ 상품 마스터 관리":
    st.title("⚙️ 상품 마스터 관리")
    t1, t2 = st.tabs(["➕ 개별 등록", "📁 엑셀 대량 등록"])
    
    with t1:
        with st.form("m_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            code = c1.text_input("상품코드")
            name = c2.text_input("상품명")
            p_type = c3.selectbox("상품유형", ["완제품", "반제품", "원자재", "부자재", "소모품"])
            unit = c1.selectbox("단위", ["EA", "m", "kg", "box", "set"])
            in_p = c2.number_input("매입단가", min_value=0)
            out_p = c3.number_input("판매단가", min_value=0)
            if st.form_submit_button("상품 저장"):
                db.collection("master").document(code).set({
                    "상품코드": str(code), "상품명": str(name), "상품유형": str(p_type),
                    "단위": str(unit), "매입단가": int(in_p), "판매단가": int(out_p)
                })
                db.collection("inventory").document(code).set({"상품코드": code, "현재고": 0}, merge=True)
                st.success("등록 완료"); st.rerun()

    with t2:
        template = pd.DataFrame(columns=["상품코드", "상품명", "상품유형", "단위", "매입단가", "판매단가"])
        st.download_button("📥 양식 다운로드", convert_df_to_excel(template), "양식.xlsx")
        up_file = st.file_uploader("엑셀 업로드", type="xlsx")
        if up_file and st.button("🔥 일괄 저장"):
            df = pd.read_excel(up_file)
            batch = db.batch()
            for _, r in df.iterrows():
                ref = db.collection("master").document(str(r['상품코드']))
                batch.set(ref, {
                    "상품코드": str(r['상품코드']), "상품명": str(r['상품명']), "상품유형": str(r['상품유형']),
                    "단위": str(r['단위']), "매입단가": int(r['매입단가']), "판매단가": int(r['판매단가'])
                })
                db.collection("inventory").document(str(r['상품코드'])).set({"상품코드": str(r['상품코드']), "현재고": 0}, merge=True)
            batch.commit(); st.success("대량 등록 완료"); st.rerun()

    if not master_df.empty:
        st.subheader("📋 등록된 상품 리스트")
        st.dataframe(master_df.style.format({"매입단가": "{:,}", "판매단가": "{:,}"}), use_container_width=True)
        
       # 엑셀 다운로드 버튼 생성
        excel_data = convert_df_to_excel(master_display) 
        st.download_button(
            label="Excel 파일 다운로드",
            data=excel_data,
            file_name=f"상품마스터_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
