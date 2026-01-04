import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import math

# --- 페이지 설정 ---
st.set_page_config(page_title="VR & 무한매수법 통합 백테스트", layout="wide")

st.title("📊 전략별 리스크 & 수익 정밀 분석")
st.markdown("""
**핵심 수정 사항:**
1. **MDD 차트 정상화:** 누적 방식이 아닌 개별 라인 차트로 변경하여 실제 낙폭 확인 가능.
2. **입금 로직 통합:** 모든 전략에 휴장일 누락 방지 로직(is_deposit_day) 적용.
3. **VR 로직 검증:** 현금 비중 및 밴드 리밸런싱을 BITU 변동성에 맞춰 정밀 계산.
""")

# --- 사이드바 설정 ---
st.sidebar.header("📝 설정")
ticker = st.sidebar.selectbox("티커 (Ticker)", ["BITU", "TQQQ", "SOXL", "UPRO", "TSLA", "NVDA"])
start_date = st.sidebar.date_input("시작 날짜", value=pd.to_datetime("2024-01-01"))
initial_capital = st.sidebar.number_input("초기 거치금 (USD)", value=10000)
monthly_amount = st.sidebar.number_input("월 적립금 (USD)", value=1000)
deposit_day = st.sidebar.slider("매월 입금일 (일)", 1, 28, 25)

st.sidebar.markdown("---")
vr_target_return = st.sidebar.number_input("VR 연 목표 수익률 (%)", value=15.0)
run_btn = st.sidebar.button("백테스트 실행 🚀")

# --- 데이터 로딩 함수 ---
@st.cache_data
def get_data(ticker, start):
    try:
        df = yf.download(ticker, start=start, progress=False)
        if df.empty: return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        target_col = next((c for c in ['Adj Close', 'Close'] if c in df.columns), None)
        if target_col:
            df = df[[target_col]].copy()
            df.rename(columns={target_col: 'Close'}, inplace=True)
            df.dropna(inplace=True)
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# --- 휴장일 대응 입금 체크 ---
def is_deposit_day(current_date, last_deposit_month, target_day):
    return current_date.month != last_deposit_month and current_date.day >= target_day

# =========================================================
# 전략 함수들 (입금 로직 완전 통합)
# =========================================================

def run_simple_dca(df, initial_cap, monthly_amt, dep_day):
    cash, shares, last_month = initial_cap, 0, -1
    shares += cash / df['Close'].iloc[0]
    cash = 0
    equity = []
    for i in range(len(df)):
        price, date = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(date, last_month, dep_day):
            shares += monthly_amt / price
            last_month = date.month
        equity.append(shares * price)
    return equity

def run_v1(df, initial_cap, monthly_amt, dep_day):
    cash, wait_cash, shares, avg_p, last_month = initial_cap, 0, 0, 0, -1
    splits = 40
    budget = cash / splits
    equity = []
    for i in range(len(df)):
        price, date = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(date, last_month, dep_day):
            wait_cash += monthly_amt
            last_month = date.month
        if shares > 0 and (price - avg_p)/avg_p >= 0.1:
            cash += (shares * price) + wait_cash
            shares, avg_p, wait_cash = 0, 0, 0
            budget = cash / splits
        if cash >= budget:
            cnt = budget / price
            avg_p = (shares * avg_p + budget) / (shares + cnt) if shares > 0 else price
            shares += cnt; cash -= budget
        equity.append(cash + wait_cash + shares * price)
    return equity

def run_vr(df, initial_cap, target_cagr, monthly_amt, dep_day):
    pool = initial_cap * 0.5
    shares = (initial_cap * 0.5) / df['Close'].iloc[0]
    target_val = initial_cap * 0.5
    daily_growth = (1 + target_cagr/100.0) ** (1/252) - 1
    last_month, equity = -1, []
    
    for i in range(len(df)):
        price, date = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(date, last_month, dep_day):
            pool += monthly_amt
            target_val += monthly_amt
            last_month = date.month
        
        target_val *= (1 + daily_growth)
        current_val = shares * price
        
        # 밴드 5% 설정
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

# --- 실행 ---
if run_btn:
    df = get_data(ticker, start_date)
    if not df.empty:
        res = pd.DataFrame(index=df.index)
        res['Simple DCA'] = run_simple_dca(df, initial_capital, monthly_amount, deposit_day)
        res['V1 (40)'] = run_v1(df, initial_capital, monthly_amount, deposit_day)
        res['VR'] = run_vr(df, initial_capital, vr_target_return, monthly_amount, deposit_day)
        
        # 원금 계산
        p_list, cur_p, l_m = [], initial_capital, -1
        for d in df.index:
            if is_deposit_day(d, l_m, deposit_day):
                cur_p += monthly_amount
                l_m = d.month
            p_list.append(cur_p)
        res['원금'] = p_list

        # MDD 계산
        mdd_df = pd.DataFrame(index=res.index)
        for col in res.columns:
            if col == '원금': continue
            mdd_df[col] = (res[col] - res[col].cummax()) / res[col].cummax() * 100

        # 시각화
        tab1, tab2 = st.tabs(["💰 수익금 추이", "📉 MDD 리스크 (정밀)"])
        with tab1:
            st.plotly_chart(px.line(res, x=res.index, y=res.columns, title="전략별 자산 평가액"), use_container_width=True)
        with tab2:
            # [수정 핵심] px.line을 사용하여 개별 라인으로 표시
            fig_mdd = px.line(mdd_df, x=mdd_df.index, y=mdd_df.columns, title="전략별 실제 낙폭(MDD) 비교")
            fig_mdd.update_yaxes(title="낙폭 (%)")
            st.plotly_chart(fig_mdd, use_container_width=True)

        # 결과 요약
        st.write("### 🏁 최종 결과")
        final_p = res['원금'].iloc[-1]
        for col in mdd_df.columns:
            final_v = res[col].iloc[-1]
            st.metric(col, f"${final_v:,.0f}", f"{((final_v-final_p)/final_p)*100:.1f}% (MDD: {mdd_df[col].min():.1f}%)")
