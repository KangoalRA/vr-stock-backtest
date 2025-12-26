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

# 3. 데이터 로딩 함수 (캐시 적용 및 오류 처리 강화)
@st.cache_data(ttl=300)  # 5분마다 데이터 갱신
def load_data(tickers, days):
    end_date = datetime.today()
    start_date = end_date - timedelta(days=days)
    
    # 딕셔너리로 받아서 안전하게 병합
    data_dict = {}
    for ticker in tickers:
        try:
            # 개별 다운로드로 안정성 확보
            df = yf.download(ticker, start=start_date, end=end_date, progress=False)
            if not df.empty:
                # 'Adj Close'나 'Close' 중 있는 것 사용
                if 'Adj Close' in df.columns:
                    data_dict[ticker] = df['Adj Close']
                else:
                    data_dict[ticker] = df['Close']
        except Exception as e:
            st.error(f"{ticker} 로딩 실패: {e}")
            
    if data_dict:
        # 데이터프레임 병합
        combined_df = pd.DataFrame(data_dict)
        return combined_df
    else:
        return pd.DataFrame()

# 4. 메인 로직 실행
tickers = ['UPRO', 'TQQQ', 'SOXL']
df = load_data(tickers, days_lookback)

if not df.empty:
    # 결측치 처리 (주말/휴일 등으로 인한 빈 값은 앞의 값으로 채움)
    df = df.ffill().dropna()

    # 5. 차트 그리기
    st.subheader("📈 주가 추이 비교")
    
    # 정규화 여부 체크박스 (시작점을 100으로 맞춤)
    normalize = st.checkbox("수익률 기준 비교 (시작일=0%)", value=True)
    
    plot_df = df.copy()
    if normalize:
        plot_df = (plot_df / plot_df.iloc[0] - 1) * 100
        y_label = "수익률 (%)"
    else:
        y_label = "주가 ($)"

    fig = px.line(plot_df, x=plot_df.index, y=plot_df.columns, 
                  labels={"value": y_label, "variable": "ETF", "Date": "날짜"})
    st.plotly_chart(fig, use_container_width=True)

    # 6. 최근 데이터 테이블 표시
    st.subheader("📊 최근 5일 데이터")
    st.dataframe(df.tail().sort_index(ascending=False).style.format("{:.2f}"))

else:
    st.error("데이터를 불러오지 못했습니다. 잠시 후 다시 시도하거나 티커를 확인해주세요.")

# 7. 만약 TQQQ가 여전히 안 나온다면 캐시 삭제 버튼 제공
if st.sidebar.button("데이터 강제 새로고침"):
    st.cache_data.clear()
    st.rerun()
