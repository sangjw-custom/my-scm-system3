import streamlit as st
import pandas as pd
from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime
import pytz
import io 

def get_now_kst():
    """현재 한국 시간을 반환하는 함수"""
    return datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-%d %H:%M')

def convert_df_to_excel(df):
    """데이터프레임을 엑셀 바이트로 변환하는 함수"""
    output = io.BytesIO()
    # 콤마 등이 포함된 '스타일러'가 아닌 원본 데이터프레임(res)을 넣어야 합니다.
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()
    
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
    """한국 시간 기준 문서 번호 생성"""
    kst_now = datetime.now(pytz.timezone('Asia/Seoul'))
    return f"{prefix}-{kst_now.strftime('%Y%m%d%H%M%S')}"

# 공통 데이터 미리 로드
master_df = get_df("master")
inv_df = get_df("inventory")
log_df = get_df("log")

# --- 3. 사이드바 메뉴 ---
st.sidebar.title("🏢 프로젝트별 상품 재고관리(외부)")
menu = st.sidebar.radio("메뉴 선택", [
    "📊 프로젝트별 재고 현황", 
    "🛒 구매 및 입고 관리", 
    "🚚 출고 및 처리 관리", 
    "📋 통합 거래 이력", 
    "⚙️ 상품 마스터 관리"
])

# --- [메뉴 1] 프로젝트별 재고 현황 ---
if menu == "📊 프로젝트별 재고 현황":
    st.title("📊 프로젝트별 실시간 재고 현황")
    if not inv_df.empty and not master_df.empty:
        # 재고 데이터와 마스터 데이터 결합
        res = pd.merge(inv_df, master_df, on="상품코드", how="left").fillna("-")
        
        # 숫자형 변환
        for col in ["매입단가", "판매단가", "현재고"]:
            res[col] = pd.to_numeric(res[col], errors='coerce').fillna(0).astype(int)
        
        res["재고금액"] = res["매입단가"] * res["현재고"]
        
        # 열 순서 (프로젝트 정보 전면 배치)
        ordered_cols = ["프로젝트코드", "프로젝트명", "상품유형", "상품코드", "상품명", "단위", "현재고", "재고금액"]
        res = res[ordered_cols].sort_values(["프로젝트코드", "상품코드"])
        
        # 상단 필터
        p_list = ["전체"] + sorted(res["프로젝트명"].unique().tolist())
        selected_p = st.selectbox("📂 프로젝트 필터", p_list)
        
        display_df = res if selected_p == "전체" else res[res["프로젝트명"] == selected_p]
        
        # 요약 지표
        c1, c2 = st.columns(2)
        c1.metric("선택된 프로젝트 자산", f"{int(display_df['재고금액'].sum()):,}원")
        c2.metric("보유 품목 수", f"{len(display_df):,}개")
        
        st.dataframe(display_df.style.format({
            "현재고": "{:,}", "재고금액": "{:,}"
        }), use_container_width=True, hide_index=True)
        
        st.download_button("📥 엑셀 다운로드", convert_df_to_excel(display_df), f"프로젝트재고_{get_now_kst()}.xlsx")
    else:
        st.info("등록된 재고 데이터가 없습니다.")

# --- [메뉴 2] 구매 및 입고 관리 ---
elif menu == "🛒 구매 및 입고 관리":
    st.title("🛒 구매 및 입고 관리")
    t1, t2 = st.tabs(["🆕 신규 구매발주", "📥 입고 확정 처리"])
    
    with t1:
        with st.form("po_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            p_code = c1.text_input("프로젝트 코드 (필수)")
            p_name = c2.text_input("프로젝트 명 (필수)")
            item_name = st.selectbox("발주 품목", master_df["상품명"]) if not master_df.empty else []
            qty = st.number_input("발주 수량", min_value=1, step=1)
            user = st.text_input("발주 담당자")
            if st.form_submit_button("구매발주 등록"):
                if p_code and p_name:
                    item_info = master_df[master_df["상품명"] == item_name].iloc[0]
                    doc_no = generate_doc_no("PO")
                    data = {
                        "문서번호": doc_no, "입력일자": get_now_kst(), "유형": "구매발주",
                        "프로젝트코드": str(p_code), "프로젝트명": str(p_name),
                        "상품코드": str(item_info["상품코드"]), "상품명": str(item_name),
                        "수량": int(qty), "단가": int(item_info["매입단가"]),
                        "총액": int(qty * item_info["매입단가"]), "입력자": str(user), "상태": "발주완료"
                    }
                    db.collection("log").document(doc_no).set(data)
                    st.success("발주 등록 완료"); st.rerun()
                else: st.error("프로젝트 정보를 입력해주세요.")
    
    with t2:
        pending = log_df[log_df["유형"] == "구매발주"].copy() if not log_df.empty else pd.DataFrame()
        if not pending.empty:
            for _, row in pending.iterrows():
                with st.expander(f"📦 {row['프로젝트명']} | {row['상품명']} ({row['수량']}개)"):
                    st.write(f"발주일자: {row['입력일자']} / 발주자: {row['입력자']}")
                    if st.button("✅ 입고 확정", key=f"in_{row['문서번호']}"):
                        # 프로젝트별 재고 ID 생성 (상품코드_프로젝트코드)
                        inv_id = f"{row['상품코드']}_{row['프로젝트코드']}"
                        inv_ref = db.collection("inventory").document(inv_id)
                        inv_doc = inv_ref.get()
                        
                        cur_stock = inv_doc.to_dict().get("현재고", 0) if inv_doc.exists else 0
                        inv_ref.set({
                            "상품코드": row["상품코드"],
                            "프로젝트코드": row["프로젝트코드"],
                            "프로젝트명": row["프로젝트명"],
                            "현재고": int(cur_stock) + int(row["수량"])
                        }, merge=True)
                        
                        db.collection("log").document(row["문서번호"]).update({"유형": "입고", "확정일자": get_now_kst()})
                        st.rerun()
        else:
            st.info("구매발주 내역이 없습니다.")
            
# --- [메뉴 3] 출고 및 처리 관리 ---
elif menu == "🚚 출고 및 처리 관리":
    st.title("🚚 출고 및 처리 관리")
    t1, t2 = st.tabs(["📤 출고 요청 등록", "✅ 출고 승인 처리"])
    
    with t1:
        with st.form("req_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            p_code = c1.text_input("프로젝트 코드 (필수)")
            p_name = c2.text_input("프로젝트 명 (필수)")
            item_name = st.selectbox("출고 품목", master_df["상품명"]) if not master_df.empty else []
            qty = st.number_input("요청 수량", min_value=1, step=1)
            user = st.text_input("요청자")
            if st.form_submit_button("출고 요청"):
                item_info = master_df[master_df["상품명"] == item_name].iloc[0]
                doc_no = generate_doc_no("REQ")
                data = {
                    "문서번호": doc_no, "입력일자": get_now_kst(), "유형": "출고요청",
                    "프로젝트코드": str(p_code), "프로젝트명": str(p_name),
                    "상품코드": str(item_info["상품코드"]), "상품명": str(item_name),
                    "수량": int(qty), "단가": int(item_info["판매단가"]),
                    "총액": int(qty * item_info["판매단가"]), "입력자": str(user), "상태": "대기"
                }
                db.collection("log").document(doc_no).set(data)
                st.success("출고 요청 완료"); st.rerun()

    with t2:
        reqs = log_df[log_df["유형"] == "출고요청"].copy() if not log_df.empty else pd.DataFrame()
        if not reqs.empty:
            for _, row in reqs.iterrows():
                inv_id = f"{row['상품코드']}_{row['프로젝트코드']}"
                inv_doc = db.collection("inventory").document(inv_id).get()
                cur_stock = inv_doc.to_dict().get("현재고", 0) if inv_doc.exists else 0
                
                with st.expander(f"🚚 {row['프로젝트명']} | {row['상품명']} (요청:{row['수량']} / 재고:{cur_stock})"):
                    if cur_stock >= int(row["수량"]):
                        if st.button("🚀 출고 승인", key=f"out_{row['문서번호']}"):
                            db.collection("inventory").document(inv_id).update({"현재고": int(cur_stock) - int(row["수량"])})
                            db.collection("log").document(row["문서번호"]).update({"유형": "출고", "확정일자": get_now_kst()})
                            st.rerun()
                    else:
                        st.error("해당 프로젝트에 재고가 부족합니다.")
        else:
            st.info("출고요청 내역이 없습니다.")

# --- [메뉴 4] 통합 거래 이력 ---
elif menu == "📋 통합 거래 이력":
    st.title("📋 전체 전표 및 거래 이력 조회")
    if not log_df.empty:
        log_df['sort_date'] = pd.to_datetime(log_df['입력일자'])
        display_log = log_df.sort_values("sort_date", ascending=False).drop(columns=['sort_date'])
        
       # 마스터 데이터와 병합하여 '단위' 정보 가져오기 (선택 사항)
        if not master_df.empty:
            display_log = pd.merge(log_df, master_df[['상품코드', '단위']], on="상품코드", how="left")
        else:
            display_log = log_df.copy()
            display_log['단위'] = "-"

        # 요청하신 순서대로 열 재배열
        # 데이터에 해당 컬럼이 없을 경우를 대비해 reindex 사용
        history_cols = [
            "유형", "상태", "프로젝트명", 
            "상품명", "수량", "단위", "단가", 
            "총액", "입력자", "문서번호", "입력일자", "확정일자", 
        ]
       
        # 데이터 정리 (결측치 처리 및 순서 고정)
        display_log = display_log.reindex(columns=history_cols).fillna("-")

        # 4. 숫자형 데이터 콤마 포맷팅 및 표 출력
        st.dataframe(
            display_log.style.format({
                "수량": "{:,}",
                "단가": "{:,}",
                "총액": "{:,}"
            }),
            use_container_width=True,
            hide_index=True
        )
        
        # 엑셀 다운로드 버튼 생성
        excel_data = convert_df_to_excel(display_log) 
        st.download_button(
            label="Excel 파일 다운로드",
            data=excel_data,
            file_name=f"통합거래이력_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("기록된 거래 이력이 없습니다.")

# --- [메뉴 5] 상품 마스터 관리 ---
elif menu == "⚙️ 상품 마스터 관리":
    st.title("⚙️ 상품 마스터 관리")
    
    # 탭 구성: 개별 등록 / 엑셀 대량 등록
    tab1, tab2 = st.tabs(["➕ 개별 등록", "📁 엑셀 대량 등록"])
    
    with tab1: 
       with st.form("master_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            code = c1.text_input("상품코드 (중복불가)")
            name = c2.text_input("상품명")
            # 1. 상품유형 추가 (원하는 카테고리로 수정 가능)
            p_type = c3.selectbox("상품유형", ["타일", "인조대리석", "빅슬랩"])
            
            unit = c1.selectbox("단위", ["EA", "m", "kg", "box", "set", "m2", "MAE"])
            in_price = c2.number_input("매입단가", min_value=0, step=100)
            out_price = c3.number_input("판매단가", min_value=0, step=100)
            
            if st.form_submit_button("상품 저장"):
                if code and name:
                    # 2. Firestore 저장 데이터에 상품유형 포함
                    db.collection("master").document(code).set({
                        "상품유형": str(p_type), # 추가
                        "상품코드": str(code), 
                        "상품명": str(name), 
                        "단위": str(unit),
                        "매입단가": int(in_price), 
                        "판매단가": int(out_price)
                    })
                    
                    inv_ref = db.collection("inventory").document(code)
                    if not inv_ref.get().exists:
                        inv_ref.set({"상품코드": str(code), "현재고": 0})
                    
                    st.success(f"[{p_type}] {name} 등록 완료!")
                    st.rerun()
                else:
                    st.error("상품코드와 상품명은 필수 입력 항목입니다.")
                    
    with tab2:
        st.subheader("📁 엑셀 파일을 이용한 일괄 등록")
        
        # 1. 업로드 양식 제공
        template_data = pd.DataFrame(columns=["상품코드", "상품명", "상품유형", "단위", "매입단가", "판매단가"])
        template_excel = convert_df_to_excel(template_data)
        st.download_button(
            label="📥 업로드 양식(Excel) 다운로드",
            data=template_excel,
            file_name="상품마스터_업로드양식.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.divider()
        
        # 2. 파일 업로드
        uploaded_file = st.file_uploader("양식에 맞게 작성된 엑셀 파일을 업로드하세요.", type=["xlsx"])
        
        if uploaded_file:
            df_upload = pd.read_excel(uploaded_file)
            st.write("▲ 업로드 데이터 미리보기")
            st.dataframe(df_upload, use_container_width=True)
            
            if st.button("🔥 데이터 일괄 저장 실행"):
                with st.spinner("데이터를 저장 중입니다..."):
                    try:
                        batch = db.batch() # 일괄 처리를 위한 배치 생성
                        count = 0
                        
                        for _, row in df_upload.iterrows():
                            # 필수 데이터 확인
                            if pd.isna(row['상품코드']) or pd.isna(row['상품명']):
                                continue
                                
                            code = str(row['상품코드'])
                            # master 컬렉션 저장 데이터
                            master_ref = db.collection("master").document(code)
                            batch.set(master_ref, {
                                "상품코드": code,
                                "상품명": str(row['상품명']),
                                "상품유형": str(row['상품유형']) if not pd.isna(row['상품유형']) else "미분류",
                                "단위": str(row['단위']) if not pd.isna(row['단위']) else "EA",
                                "매입단가": int(row['매입단가']) if not pd.isna(row['매입단가']) else 0,
                                "판매단가": int(row['판매단가']) if not pd.isna(row['판매단가']) else 0
                            })
                            
                            # inventory 컬렉션 초기화 (재고가 없을 때만 0으로 설정)
                            inv_ref = db.collection("inventory").document(code)
                            batch.set(inv_ref, {"상품코드": code, "현재고": 0}, merge=True)
                            
                            count += 1
                            
                            # Firestore 배치는 한 번에 최대 500개까지만 가능
                            if count % 400 == 0:
                                batch.commit()
                                batch = db.batch()
                        
                        batch.commit() # 남은 데이터 저장
                        st.success(f"✅ 총 {count}개의 상품이 성공적으로 등록되었습니다!")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ 저장 중 오류 발생: {e}")

    # (하단 등록된 상품 리스트 표시 코드는 기존과 동일하게 유지)

    st.subheader("📋 등록된 상품 리스트")
    if not master_df.empty:
        # 3. 열 순서 재배치 (유형을 앞쪽으로)
        master_display = master_df.copy()
        for col in ["매입단가", "판매단가"]:
            master_display[col] = pd.to_numeric(master_display[col], errors='coerce').fillna(0).astype(int)
        
        # 보기 좋은 순서로 열 정렬
        m_cols = ["상품유형", "상품코드", "상품명", "단위", "매입단가", "판매단가"]
        master_display = master_display[m_cols]

        st.dataframe(
            master_display.style.format({"매입단가": "{:,}", "판매단가": "{:,}"}),
            use_container_width=True,
            hide_index=True
        )
       # 엑셀 다운로드 버튼 생성
        excel_data = convert_df_to_excel(master_display) 
        st.download_button(
            label="Excel 파일 다운로드",
            data=excel_data,
            file_name=f"상품마스터_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
       st.info("등록된 상품 내역이 없습니다.")
