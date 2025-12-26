import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# 1. 페이지 기본 설정
st.set_page_config(page_title="3x 레버리지 대시보드", layout="wide")

st.title("🚀 UPRO / TQQQ / SOXL 모니터링")

# 2. 사이드바 설정 (기간 선택)
st.sidebar.header("설정")
days_lookback = st.sidebar.slider("조회 기간 (일)", 30, 3650, 365) # 기본 1년

# 3. 데이터 로딩 함수 (오류 해결 버전)
@st.cache_data(ttl=300)  # 5분마다 데이터 갱신
def load_data(tickers, days):
    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)
    
    series_list = [] # 데이터를 담을 리스트
    
    for ticker in tickers:
        try:
            # multi_level_index=False: 최신 yfinance 버그 방지용 (필수)
            df = yf.download(ticker, start=start_date, end=end_date, progress=False, multi_level_index=False)
            
            if not df.empty:
                # 'Adj Close' 우선 사용, 없으면 'Close' 사용
                col_name = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
                
                # 데이터 시리즈 추출 및 이름(티커) 지정
                series = df[col_name]
                series.name = ticker 
                
                series_list.append(series)
            else:
                st.warning(f"{ticker} 데이터가 비어있습니다.")
                
        except Exception as e:
            st.error(f"{ticker} 로딩 실패: {e}")
            
    if series_list:
        # 리스트에 있는 시리즈들을 날짜 기준으로 합침 (pd.concat 사용으로 안정성 확보)
        combined_df = pd.concat(series_list, axis=1)
        return combined_df
    else:
        return pd.DataFrame()

# 4. 메인 로직 실행
tickers = ['UPRO', 'TQQQ', 'SOXL']
df = load_data(tickers, days_lookback)

if not df.empty:
    # 결측치 처리 (주말/휴일은 전날 데이터로 채움)
    df = df.ffill().dropna()

    # 5. 차트 그리기
    st.subheader("📈 주가 추이 비교")
    
    # 정규화 여부 체크박스 (시작점을 0%로 맞춤)
    normalize = st.checkbox("수익률 기준 비교 (시작일=0%)", value=True)
    
    plot_df = df.copy()
    if normalize:
        # 첫 날짜 기준 수익률 계산
        plot_df = (plot_df / plot_df.iloc[0] - 1) * 100
        y_label = "수익률 (%)"
    else:
        y_label = "주가 ($)"

    # Plotly 차트 생성
    fig = px.line(plot_df, x=plot_df.index, y=plot_df.columns, 
                  labels={"value": y_label, "variable": "ETF", "Date": "날짜"})
    st.plotly_chart(fig, use_container_width=True)

    # 6. 최근 데이터 테이블 표시
    st.subheader("📊 최근 5일 데이터")
    # 날짜를 읽기 쉽게 포맷팅하고 내림차순 정렬
    display_df = df.tail().sort_index(ascending=False)
    st.dataframe(display_df.style.format("{:.2f}"))

else:
    st.error("데이터를 불러오지 못했습니다. 잠시 후 다시 시도하거나 티커를 확인해주세요.")

# 7. 데이터 꼬임 방지용 초기화 버튼
if st.sidebar.button("데이터 강제 새로고침"):
    st.cache_data.clear()
    st.rerun()
