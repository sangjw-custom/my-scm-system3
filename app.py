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

# 3. 사이드바 메뉴 구성
st.sidebar.title("🏢 외부 재고 관리")
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
        # 1. 데이터 병합 및 계산
        res = pd.merge(master_df, inv_df, on="상품코드", how="left").fillna(0)
        
        # 2. 숫자형 강제 변환 (콤마 표시를 위함)
        num_cols = ["매입단가", "판매단가", "현재고"]
        for col in num_cols:
            res[col] = pd.to_numeric(res[col], errors='coerce').fillna(0).astype(int)
            
        res["재고금액(매입가)"] = res["매입단가"] * res["현재고"]
        
        # 3. 요청하신 순서대로 열 재배열
        ordered_cols = [
            "상품유형", "상품코드", "상품명", "단위", 
            "판매단가", "매입단가", "현재고", 
            "재고금액(매입가)"
        ]
        res = res[ordered_cols]
        
        # 4. 상단 요약 지표 (Metric)
        c1, c2 = st.columns(2)
        total_asset = int(res['재고금액(매입가)'].sum())
        c1.metric("총 재고 자산", f"{total_asset:,}원")
        c2.metric("관리 품목 수", f"{len(res):,}개")
        
        # 5. 스타일러를 이용한 표 출력 (천 단위 콤마 적용)
        st.write("##### 📋 상세 재고 리스트")
        st.dataframe(
            res.style.format({
                "판매단가": "{:,}",
                "매입단가": "{:,}",
                "현재고": "{:,}",
                "재고금액(매입가)": "{:,}"
            }),
            use_container_width=True,
            hide_index=True
        )
        # 엑셀 다운로드 버튼 생성
        excel_data = convert_df_to_excel(res) # res는 순수 숫자 데이터가 있는 DF
        st.download_button(
            label="Excel 파일 다운로드",
            data=excel_data,
            file_name=f"실시간재고현황_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
                            "입력일자": get_now_kst(),
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
        st.subheader("📥 입고 대기 목록")
        if not log_df.empty:
            # 구매발주 상태인 데이터만 필터링
            pending = log_df[log_df["유형"] == "구매발주"].copy()
            
            if not pending.empty:
                # 1. 표 헤더 설정
                cols = st.columns([2, 2, 1, 2, 1.5, 1.5])
                cols[0].write("**문서번호**")
                cols[1].write("**상품명**")
                cols[2].write("**수량**")
                cols[3].write("**발주일자**")
                cols[4].write("**담당자**")
                cols[5].write("**액션**")
                st.divider()

                # 2. 데이터 행 반복 생성
                for _, row in pending.iterrows():
                    r_cols = st.columns([2, 2, 1, 2, 1.5, 1.5])
                    
                    # 데이터 추출 및 콤마 포맷팅
                    doc_no = row['문서번호']
                    item_name = row['상품명']
                    # 수량을 정수로 변환 후 콤마 추가
                    qty_formatted = f"{int(row['수량']):,}"
                    date_str = row['입력일자']
                    user_str = row['입력자']
                    
                    r_cols[0].write(doc_no)
                    r_cols[1].write(item_name)
                    r_cols[2].write(f"**{qty_formatted}**") # 수량 강조
                    r_cols[3].write(date_str)
                    r_cols[4].write(user_str)
                    
                    # 승인 버튼
                    if r_cols[5].button("✅ 입고승인", key=f"btn_{doc_no}"):
                        with st.spinner("처리 중..."):
                            # A. 재고 업데이트
                            inv_ref = db.collection("inventory").document(row["상품코드"])
                            inv_doc = inv_ref.get()
                            cur_stock = inv_doc.to_dict().get("현재고", 0) if inv_doc.exists else 0
                            
                            # 안전하게 숫자로 변환 후 계산
                            new_stock = int(cur_stock) + int(row["수량"])
                            inv_ref.set({"상품코드": row["상품코드"], "현재고": new_stock})
                            
                            # B. 로그 상태 변경
                            db.collection("log").document(doc_no).update({
                                "유형": "입고",
                                "상태": "입고완료",
                                "확정일자": datetime.now().strftime("%Y-%m-%d %H:%M")
                            })
                            
                        st.success(f"[{item_name}] {qty_formatted}개 입고 완료!")
                        st.rerun()
            else:
                st.info("입고 대기 중인 발주 내역이 없습니다.")

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
                    # 1. 마스터 정보 찾기
                    selected_items = master_df[master_df["상품명"] == item_name]
                    if not selected_items.empty:
                        item_info = selected_items.iloc[0]
                        doc_no = generate_doc_no("REQ")
                        
                        # 2. [핵심] Firestore 전송용 데이터 구성 (강제 형변환)
                        data = {
                            "문서번호": str(doc_no),
                            "입력일자": get_now_kst(),
                            "유형": "출고요청",
                            "상품코드": str(item_info["상품코드"]),
                            "상품명": str(item_name),
                            "수량": int(qty),
                            "단가": int(item_info["판매단가"]),
                            "총액": int(qty * item_info["판매단가"]),
                            "입력자": str(user),
                            "상태": "대기"
                        }
                        
                        # 3. 데이터 저장
                        db.collection("log").document(doc_no).set(data)
                        st.success(f"출고 요청 완료: {doc_no}")
                        st.rerun()
                    else:
                        st.error("상품 정보를 찾을 수 없습니다.")

    with t2:
        st.subheader("📤 출고 대기 및 승인")
        if not log_df.empty:
            # 출고요청 상태인 데이터만 필터링
            reqs = log_df[log_df["유형"] == "출고요청"].copy()
            
            if not reqs.empty:
                # 1. 표 헤더 설정
                cols = st.columns([1.5, 2, 0.8, 0.8, 1.8, 1.2, 1.2])
                cols[0].write("**문서번호**")
                cols[1].write("**상품명**")
                cols[2].write("**요청수량**")
                cols[3].write("**현재고**")
                cols[4].write("**요청일자**")
                cols[5].write("**요청자**")
                cols[6].write("**액션**")
                st.divider()

                # 2. 데이터 행 반복 생성
                for _, row in reqs.iterrows():
                    # 현재 재고 상태 확인
                    inv_ref = db.collection("inventory").document(row["상품코드"])
                    inv_doc = inv_ref.get()
                    cur_stock = int(inv_doc.to_dict().get("현재고", 0)) if inv_doc.exists else 0
                    
                    req_qty = int(row["수량"])
                    
                    r_cols = st.columns([1.5, 2, 0.8, 0.8, 1.8, 1.2, 1.2])
                    
                    # 데이터 포맷팅 (콤마 추가)
                    r_cols[0].write(row['문서번호'])
                    r_cols[1].write(row['상품명'])
                    r_cols[2].write(f"**{req_qty:,}**") # 요청수량
                    
                    # 재고 부족 시 빨간색 표시
                    if cur_stock < req_qty:
                        r_cols[3].write(f":red[{cur_stock:,}]") 
                    else:
                        r_cols[3].write(f"{cur_stock:,}")
                    
                    r_cols[4].write(row['입력일자'])
                    r_cols[5].write(row.get('입자', '-'))
                    
                    # 3. 승인 버튼 (재고 부족 시 작동 방지)
                    if cur_stock >= req_qty:
                        if r_cols[6].button("🚚 출고승인", key=f"out_{row['문서번호']}"):
                            with st.spinner("처리 중..."):
                                # A. 재고 차감
                                inv_ref.update({"현재고": cur_stock - req_qty})
                                
                                # B. 로그 상태 업데이트
                                db.collection("log").document(row["문서번호"]).update({
                                    "유형": "출고",
                                    "상태": "출고완료",
                                    "확정일자": get_now_kst()
                                })
                            st.success(f"[{row['상품명']}] {req_qty:,}개 출고 완료!")
                            st.rerun()
                    else:
                        r_cols[5].button("⚠️ 재고부족", key=f"out_{row['문서번호']}", disabled=True)
            else:
                st.info("대기 중인 출고 요청이 없습니다.")
        else:
            st.info("거래 기록이 존재하지 않습니다.")

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
