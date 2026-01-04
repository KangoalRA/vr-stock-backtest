import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import math

# --- 페이지 설정 ---
st.set_page_config(page_title="VR & 무한매수법 통합 백테스트", layout="wide")

st.title("📊 전략별 리스크 & 수익 정밀 분석")
st.info("💡 모든 오류를 해결한 최종 버전입니다. 티커를 선택하고 '백테스트 실행'을 눌러주세요.")

# --- 사이드바 설정 ---
st.sidebar.header("📝 기본 설정")
ticker = st.sidebar.selectbox("티커 (Ticker)", ["BITU", "TQQQ", "SOXL", "UPRO", "TSLA", "NVDA", "BITX"])
start_date = st.sidebar.date_input("시작 날짜", value=pd.to_datetime("2024-04-01"))
initial_capital = st.sidebar.number_input("초기 거치금 (USD)", value=10000, step=1000)

st.sidebar.markdown("### 💰 월 적립금 설정")
monthly_amount = st.sidebar.number_input("월 적립금 (USD)", value=1000, step=100)
deposit_day = st.sidebar.slider("매월 입금일 (일)", 1, 28, 25)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ VR 설정")
vr_target_return = st.sidebar.number_input("VR 연 목표 수익률 (%)", value=15.0)

run_btn = st.sidebar.button("백테스트 실행 🚀")

# --- [초강력] 데이터 가져오기 함수 ---
@st.cache_data
def get_data(ticker, start):
    try:
        # auto_adjust=True를 사용하여 수정주가를 바로 가져옵니다.
        df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
        
        if df.empty:
            return pd.DataFrame()

        # MultiIndex 컬럼인 경우 (최신 yfinance 대응)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # 종가 컬럼 추출
        if 'Close' in df.columns:
            df = df[['Close']].copy()
        else:
            # 컬럼이 하나만 있는 경우 그것을 Close로 간주
            df = df.iloc[:, [0]]
            df.columns = ['Close']

        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df.dropna(inplace=True)
        return df
    except Exception as e:
        st.error(f"데이터 로딩 중 오류: {e}")
        return pd.DataFrame()

# --- 휴장일 대응 입금 체크 함수 ---
def is_deposit_day(current_date, last_deposit_month, target_day):
    # 이번 달에 입금을 안 했고, 오늘이 설정한 입금일 이후면 입금 실행
    if current_date.month != last_deposit_month and current_date.day >= target_day:
        return True
    return False

# =========================================================
# 전략 로직 (입금/매매 로직 정밀 통합)
# =========================================================

def run_simple_dca(df, initial_cap, monthly_amt, dep_day):
    shares = initial_cap / df['Close'].iloc[0]
    last_month, equity = df.index[0].month, []
    
    for i in range(len(df)):
        price, date = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(date, last_month, dep_day):
            shares += monthly_amt / price
            last_month = date.month
        equity.append(shares * price)
    return equity

def run_v1(df, initial_cap, monthly_amt, dep_day):
    cash, wait_cash, shares, avg_p, last_month = initial_cap, 0, 0, 0, df.index[0].month
    splits = 40
    budget = cash / splits
    equity = []
    
    for i in range(len(df)):
        price, date = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(date, last_month, dep_day):
            wait_cash += monthly_amt
            last_month = date.month
            
        # 10% 익절 로직
        if shares > 0 and (price - avg_p)/avg_p >= 0.1:
            cash += (shares * price) + wait_cash
            shares, avg_p, wait_cash = 0, 0, 0
            budget = cash / splits
            
        # 매수 로직
        if cash >= budget:
            cnt = budget / price
            avg_p = (shares * avg_p + budget) / (shares + cnt) if shares > 0 else price
            shares += cnt
            cash -= budget
            
        equity.append(cash + wait_cash + shares * price)
    return equity

def run_vr(df, initial_cap, target_cagr, monthly_amt, dep_day):
    # 현금 50%, 주식 50% 시작
    pool = initial_cap * 0.5
    shares = (initial_cap * 0.5) / df['Close'].iloc[0]
    target_val = initial_cap * 0.5
    daily_growth = (1 + target_cagr/100.0) ** (1/252) - 1
    last_month, equity = df.index[0].month, []
    
    for i in range(len(df)):
        price, date = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(date, last_month, dep_day):
            pool += monthly_amt
            target_val += monthly_amt
            last_month = date.month
        
        target_val *= (1 + daily_growth)
        current_val = shares * price
        
        # 밴드 5% 리밸런싱
        if current_val < target_val * 0.95:
            diff = (target_val * 0.95) - current_val
            buy_amt = min(diff, pool)
            shares += buy_amt / price
            pool -= buy_amt
        elif current_val > target_val * 1.05:
            diff = current_val - (target_val * 1.05)
            shares_to_sell = diff / price
            if shares >= shares_to_sell:
                shares -= shares_to_sell
                pool += diff
                
        equity.append((shares * price) + pool)
    return equity

# --- 메인 실행 ---
if run_btn:
    with st.spinner('데이터 계산 중...'):
        df = get_data(ticker, start_date)
        
        if df.empty:
            st.error("데이터를 가져오지 못했습니다. 시작 날짜나 티커를 확인하세요.")
        else:
            res = pd.DataFrame(index=df.index)
            res['Simple DCA'] = run_simple_dca(df, initial_capital, monthly_amount, deposit_day)
            res['V1 (40분할)'] = run_v1(df, initial_capital, monthly_amount, deposit_day)
            res['VR 전략'] = run_vr(df, initial_capital, vr_target_return, monthly_amount, deposit_day)
            
            # 원금 계산 (시각화용)
            p_list, cur_p, l_m = [], initial_capital, df.index[0].month
            for d in df.index:
                if is_deposit_day(d, l_m, deposit_day):
                    cur_p += monthly_amount
                    l_m = d.month
                p_list.append(cur_p)
            res['총 투입 원금'] = p_list

            # MDD 계산 (각 전략별 개별 계산)
            mdd_df = pd.DataFrame(index=res.index)
            for col in ['Simple DCA', 'V1 (40분할)', 'VR 전략']:
                rolling_max = res[col].cummax()
                mdd_df[col] = (res[col] - rolling_max) / rolling_max * 100

            # --- 결과 출력 ---
            tab1, tab2 = st.tabs(["💰 자산 추이", "📉 MDD 리스크 비교"])
            
            with tab1:
                fig1 = px.line(res, x=res.index, y=res.columns, title=f"{ticker} 전략별 수익금 비교")
                fig1.update_traces(patch={"line": {"dash": "dot", "color": "gray"}}, selector={"name": "총 투입 원금"})
                st.plotly_chart(fig1, use_container_width=True)
                
            with tab2:
                # [수정] 누적이 아닌 일반 라인 차트로 변경
                fig2 = px.line(mdd_df, x=mdd_df.index, y=mdd_df.columns, title="전략별 실제 낙폭(MDD) 비교")
                fig2.update_yaxes(title="낙폭 (%)")
                st.plotly_chart(fig2, use_container_width=True)

            # 성과 요약 카드
            st.write("### 🏁 최종 성과 요약")
            final_principal = res['총 투입 원금'].iloc[-1]
            cols = st.columns(3)
            
            for i, col_name in enumerate(['Simple DCA', 'V1 (40분할)', 'VR 전략']):
                final_val = res[col_name].iloc[-1]
                profit_pct = ((final_val - final_principal) / final_principal) * 100
                mdd_val = mdd_df[col_name].min()
                cols[i].metric(col_name, f"${final_val:,.0f}", f"{profit_pct:+.1f}%")
                cols[i].write(f"최대 낙폭: **{mdd_val:.1f}%**")
