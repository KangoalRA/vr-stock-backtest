import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import math
import numpy as np
from datetime import datetime

# --- [0. 페이지 설정] ---
st.set_page_config(page_title="라오어 무매 & VR 통합 백테스트", layout="wide")

st.title("📊 전 전략 통합 분석 (DCA, 무매 3종, VR 2종)")
st.info("💡 모든 무한매수법 버전과 DCA, VR 2종을 통합했습니다. G값과 밴드는 VR 전략에 공통 적용됩니다.")

# --- [1. 사이드바 설정] ---
st.sidebar.header("📝 기본 설정")
ticker = st.sidebar.selectbox("대상 티커 (Asset)", ["TQQQ", "SOXL", "BITU", "UPRO", "TSLA", "NVDA"])
benchmark = "^NDX"  # 나스닥 지수 (안전장치용)
start_date = st.sidebar.date_input("시작 날짜", value=pd.to_datetime("2023-01-01"))
initial_capital = st.sidebar.number_input("초기 거치금 (USD)", value=10000, step=1000)
monthly_amount = st.sidebar.number_input("월 적립금 (USD)", value=1000, step=100)
deposit_day = st.sidebar.slider("매월 입금일 (일)", 1, 28, 25)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 전략 세부 설정")
split_v1_v2 = st.sidebar.number_input("무매 V1/V2.2 분할 수", value=40)
split_v3 = st.sidebar.number_input("무매 V3.0 분할 수", value=20)

st.sidebar.markdown("---")
st.sidebar.header("⚖️ 공통 VR 파라미터")
common_g = st.sidebar.radio("공통 G값 (기울기)", [10, 20], index=0, horizontal=True)
common_band = st.sidebar.slider("공통 밴드폭 (%)", 5, 20, 15) / 100

st.sidebar.markdown("---")
st.sidebar.header("🛡️ ISA-VR 안전장치")
fng_fixed = st.sidebar.slider("백테스트용 고정 FnG 지수", 0, 100, 30)

run_btn = st.sidebar.button("백테스트 실행 🚀")

# --- [2. 공통 유틸리티 함수] ---
@st.cache_data
def get_combined_data(ticker, bench, start):
    try:
        df = yf.download([ticker, bench], start=start, progress=False, auto_adjust=True)
        if df.empty: return pd.DataFrame()
        close_df = df['Close'].copy()
        close_df = close_df.rename(columns={ticker: 'Asset', bench: 'Nasdaq'})
        close_df['Nasdaq_200MA'] = close_df['Nasdaq'].rolling(window=200).mean()
        close_df.dropna(inplace=True)
        return close_df
    except: return pd.DataFrame()

def is_deposit_day(current_date, last_deposit_month, target_day):
    return current_date.month != last_deposit_month and current_date.day >= target_day

# =========================================================
# [3. 전략 함수 정의]
# =========================================================

# 0. Simple DCA
def run_simple_dca(df, initial_cap, monthly_amt, dep_day):
    shares, last_m, equity = initial_cap / df['Asset'].iloc[0], -1, []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, dep_day):
            shares += monthly_amt / p; last_m = d.month
        equity.append(shares * p)
    return equity

# 1. 무한매수법 V1.0 (평단LOC + 시장가)
def run_v1(df, initial_cap, splits, monthly_amt, dep_day):
    cash, wait_cash, shares, avg_p, last_m = initial_cap, 0, 0, 0, -1
    budget = cash / splits
    equity = []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, dep_day): wait_cash += monthly_amt; last_m = d.month
        if shares > 0 and (p - avg_p)/avg_p >= 0.1: # +10% 익절
            cash += (shares * p) + wait_cash; shares, avg_p, wait_cash = 0, 0, 0
            budget = cash / splits
        if cash >= budget:
            cnt = budget / p
            avg_p = (shares * avg_p + budget) / (shares + cnt) if shares > 0 else p
            shares += cnt; cash -= budget
        equity.append(cash + wait_cash + shares * p)
    return equity

# 2. 무한매수법 V2.2 (T값 기반)
def run_v22(df, initial_cap, splits, monthly_amt, dep_day):
    cash, wait_cash, shares, avg_p, last_m, acc_buy = initial_cap, 0, 0, 0, -1, 0
    budget = cash / splits
    equity = []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, dep_day): wait_cash += monthly_amt; last_m = d.month
        t_val = acc_buy / budget if budget > 0 else 0
        if shares > 0 and (p - avg_p)/avg_p >= 0.1: # 익절
            cash += (shares * p) + wait_cash; shares, avg_p, wait_cash, acc_buy = 0, 0, 0, 0
            budget = cash / splits
        loc_p = avg_p * (1 + (10 - t_val/2)/100) if avg_p > 0 else p * 1.1
        buy_amt = budget if p <= loc_p else 0
        if cash >= buy_amt and buy_amt > 0:
            cnt = buy_amt / p
            avg_p = (shares * avg_p + buy_amt) / (shares + cnt) if shares > 0 else p
            shares += cnt; cash -= buy_amt; acc_buy += buy_amt
        equity.append(cash + wait_cash + shares * p)
    return equity

# 3. 무한매수법 V3.0 (전/후반전 & 쿼터매도)
def run_v3(df, initial_cap, splits, monthly_amt, dep_day, ticker_name):
    cash, wait_cash, shares, avg_p, last_m, acc_buy = initial_cap, 0, 0, 0, -1, 0
    budget = cash / splits
    target_pct = 0.15 if any(x in ticker_name for x in ["TQQQ", "SOXL", "BITU"]) else 0.20
    equity = []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, dep_day): wait_cash += monthly_amt; last_m = d.month
        t_val = acc_buy / budget if budget > 0 else 0
        if shares > 0:
            if (p - avg_p) / avg_p >= target_pct: # 졸업
                cash += (shares * p) + wait_cash; shares, avg_p, wait_cash, acc_buy = 0, 0, 0, 0
                budget = cash / splits
            elif t_val >= splits / 2 and p >= avg_p: # 쿼터 매도 (탈출)
                sell_q = shares * 0.25
                cash += sell_q * p; shares -= sell_q; acc_buy -= (sell_q * avg_p)
                if acc_buy < 0: acc_buy = 0
        star_pct = 15 if t_val < splits / 2 else max(0, 15 - (t_val - splits/2))
        buy_p = avg_p * (1 + star_pct/100) if avg_p > 0 else p * 1.2
        buy_amt = budget if p <= buy_p else 0
        if cash >= buy_amt and buy_amt > 0:
            cnt = buy_amt / p
            avg_p = (shares * avg_p + buy_amt) / (shares + cnt) if shares > 0 else p
            shares += cnt; cash -= buy_amt; acc_buy += buy_amt
        equity.append(cash + wait_cash + shares * p)
    return equity

# 4. 표준 VR (라오어 5.0 공식)
def run_standard_vr(df, initial_cap, g_val, band_val, monthly_amt, dep_day):
    pool, shares, v_target = initial_cap * 0.5, (initial_cap * 0.5) / df['Asset'].iloc[0], initial_cap * 0.5
    last_m, equity = -1, []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, dep_day): pool += monthly_amt; v_target += monthly_amt; last_m = d.month
        v_target += (pool / g_val) / 252
        curr_val = shares * p
        if curr_val < v_target * (1 - band_val):
            diff = min(v_target * (1 - band_val) - curr_val, pool * 0.75)
            shares += diff / p; pool -= diff
        elif curr_val > v_target * (1 + band_val):
            diff = curr_val - v_target * (1 + band_val)
            shares_to_sell = diff / p
            if shares >= shares_to_sell: shares -= shares_to_sell; pool += diff
        equity.append(curr_val + pool)
    return equity

# 5. ISA-VR (변형 공식: 안전장치 포함)
def run_isa_vr(df, initial_cap, g_val, band_max, fng, monthly_amt, dep_day):
    pool, shares, v_target = initial_cap * 0.5, (initial_cap * 0.5) / df['Asset'].iloc[0], initial_cap * 0.5
    last_m, equity = -1, []
    nasdaq_high = df['Nasdaq'].iloc[0]
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        ndx, ndx_ma = df['Nasdaq'].iloc[i], df['Nasdaq_200MA'].iloc[i]
        if is_deposit_day(d, last_m, dep_day): pool += monthly_amt; v_target += monthly_amt; last_m = d.month
        v_target += (pool / g_val) / 252
        nasdaq_high = max(nasdaq_high, ndx); dd = (ndx / nasdaq_high - 1) * 100
        is_bull = ndx > ndx_ma
        
        # 동적 밴드 & 안전장치
        if not is_bull or dd <= -20: band_val = 0.05
        elif -20 < dd <= -10: band_val = 0.07
        else: band_val = band_max
        
        buy_intensity = 1.0
        if dd <= -10:
            if dd > -20: buy_intensity = 0.5 if fng <= 20 else 0.0
            else: buy_intensity = 0.3 if fng <= 15 else 0.0

        curr_val = shares * p
        if curr_val < v_target * (1 - band_val):
            diff = (v_target * (1 - band_val)) - curr_val
            buy_amt = min(diff * buy_intensity, pool * 0.75)
            shares += buy_amt / p; pool -= buy_amt
        elif curr_val > v_target * (1 + band_val):
            diff = curr_val - (v_target * (1 + band_val))
            shares_to_sell = diff / p
            if shares >= shares_to_sell: shares -= shares_to_sell; pool += diff
        equity.append(curr_val + pool)
    return equity

# =========================================================
# [4. 실행 및 시각화]
# =========================================================
if run_btn:
    df = get_combined_data(ticker, benchmark, start_date)
    if not df.empty:
        res = pd.DataFrame(index=df.index)
        res['Simple DCA'] = run_simple_dca(df, initial_capital, monthly_amount, deposit_day)
        res['무매 V1.0 (40분할)'] = run_v1(df, initial_capital, split_v1_v2, monthly_amount, deposit_day)
        res['무매 V2.2 (40분할)'] = run_v22(df, initial_capital, split_v1_v2, monthly_amount, deposit_day)
        res['무매 V3.0 (20분할)'] = run_v3(df, initial_capital, split_v3, monthly_amount, deposit_day, ticker)
        res[f'표준 VR (G={common_g})'] = run_standard_vr(df, initial_capital, common_g, common_band, monthly_amount, deposit_day)
        res[f'ISA-VR (G={common_g})'] = run_isa_vr(df, initial_capital, common_g, common_band, fng_fixed, monthly_amount, deposit_day)
        
        p_list, cur_p, l_m = [], initial_capital, -1
        for d in df.index:
            if is_deposit_day(d, l_m, deposit_day): cur_p += monthly_amount; l_m = d.month
            p_list.append(cur_p)
        res['투입 원금'] = p_list

        mdd_df = (res.drop(columns=['투입 원금']) - res.drop(columns=['투입 원금']).cummax()) / res.drop(columns=['투입 원금']).cummax() * 100

        t1, t2 = st.tabs(["💰 자산 수익금 추이", "📉 MDD 리스크 비교"])
        with t1:
            fig1 = px.line(res, x=res.index, y=res.columns, title="전략별 평가액 비교")
            fig1.update_traces(patch={"line": {"dash": "dot", "color": "gray"}}, selector={"name": "투입 원금"})
            st.plotly_chart(fig1, use_container_width=True)
        with t2:
            st.plotly_chart(px.line(mdd_df, x=mdd_df.index, y=mdd_df.columns, title="전략별 실제 낙폭(MDD)"), use_container_width=True)

        st.write("### 🏁 최종 성과 요약")
        final_p = res['투입 원금'].iloc[-1]
        summary = []
        for col in mdd_df.columns:
            fv = res[col].iloc[-1]
            summary.append({"전략": col, "최종자산": f"${fv:,.0f}", "수익률": f"{((fv-final_p)/final_p)*100:.1f}%", "MDD": f"{mdd_df[col].min():.1f}%"})
        st.table(pd.DataFrame(summary).set_index("전략"))
