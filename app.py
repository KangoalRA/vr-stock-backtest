import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import math

# --- 페이지 설정 ---
st.set_page_config(page_title="라오어 전략 통합 백테스트", layout="wide")

st.title("📊 라오어 V1, V2.2, V3.0, VR & DCA 통합 분석")
st.info("💡 수정 완료: DCA 복구, VR(G=10, Band=15%) 적용, 모든 전략 휴장일 보정 통합")

# --- 사이드바 설정 ---
st.sidebar.header("📝 기본 설정")
ticker = st.sidebar.selectbox("티커 (Ticker)", ["BITU", "TQQQ", "SOXL", "UPRO", "TSLA", "NVDA"])
start_date = st.sidebar.date_input("시작 날짜", value=pd.to_datetime("2024-01-01"))
initial_capital = st.sidebar.number_input("초기 거치금 (USD)", value=10000, step=1000)
monthly_amount = st.sidebar.number_input("월 적립금 (USD)", value=1000, step=100)
deposit_day = st.sidebar.slider("매월 입금일 (일)", 1, 28, 25)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 전략 세부 설정")
split_v1_v2 = st.sidebar.number_input("V1/V2.2 분할 수", value=40)
split_v3 = st.sidebar.number_input("V3.0 분할 수", value=20)
vr_g_value = st.sidebar.number_input("VR G값 (기울기 %)", value=10.0)
vr_band_value = st.sidebar.number_input("VR 밴드값 (폭 %)", value=15.0)

run_btn = st.sidebar.button("백테스트 실행 🚀")

# --- 데이터 로딩 함수 (최신 yfinance 대응) ---
@st.cache_data
def get_data(ticker, start):
    try:
        df = yf.download(ticker, start=start, progress=False, auto_adjust=True)
        if df.empty: return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df[['Close']].copy() if 'Close' in df.columns else df.iloc[:, [0]]
        df.columns = ['Close']
        df.dropna(inplace=True); return df
    except: return pd.DataFrame()

def is_deposit_day(current_date, last_deposit_month, target_day):
    return current_date.month != last_deposit_month and current_date.day >= target_day

# =========================================================
# 전략 함수 (DCA, V1, V2.2, V3.0, VR)
# =========================================================

def run_simple_dca(df, initial_cap, monthly_amt, dep_day):
    shares, last_m, equity = initial_cap / df['Close'].iloc[0], -1, []
    for i in range(len(df)):
        p, d = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, dep_day): shares += monthly_amt / p; last_m = d.month
        equity.append(shares * p)
    return equity

def run_v1(df, initial_cap, splits, monthly_amt, dep_day):
    cash, wait_cash, shares, avg_p, last_m = initial_cap, 0, 0, 0, -1
    budget = cash / splits
    equity = []
    for i in range(len(df)):
        p, d = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, dep_day): wait_cash += monthly_amt; last_m = d.month
        if shares > 0 and (p - avg_p)/avg_p >= 0.1:
            cash += (shares * p) + wait_cash; shares, avg_p, wait_cash = 0, 0, 0
            budget = cash / splits
        if cash >= budget:
            cnt = budget / p
            avg_p = (shares * avg_p + budget) / (shares + cnt) if shares > 0 else p
            shares += cnt; cash -= budget
        equity.append(cash + wait_cash + shares * p)
    return equity

def run_v22(df, initial_cap, splits, monthly_amt, dep_day):
    cash, wait_cash, shares, avg_p, last_m, acc_buy = initial_cap, 0, 0, 0, -1, 0
    budget = cash / splits
    equity = []
    for i in range(len(df)):
        p, d = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, dep_day): wait_cash += monthly_amt; last_m = d.month
        t_val = acc_buy / budget if budget > 0 else 0
        if shares > 0 and (p - avg_p)/avg_p >= 0.1:
            cash += (shares * p) + wait_cash; shares, avg_p, wait_cash, acc_buy = 0, 0, 0, 0
            budget = cash / splits
        loc_p = avg_p * (1 + (10 - t_val/2)/100) if avg_p > 0 else p * 1.1
        buy_amt = 0
        if t_val < splits/2:
            if avg_p == 0 or p <= avg_p: buy_amt += budget * 0.5
            if p <= loc_p: buy_amt += budget * 0.5
        else:
            if p <= loc_p: buy_amt = budget
        if cash >= buy_amt and buy_amt > 0:
            cnt = buy_amt / p
            avg_p = (shares * avg_p + buy_amt) / (shares + cnt) if shares > 0 else p
            shares += cnt; cash -= buy_amt; acc_buy += buy_amt
        equity.append(cash + wait_cash + shares * p)
    return equity

def run_v3(df, initial_cap, splits, monthly_amt, dep_day, ticker_name):
    cash, wait_cash, shares, avg_p, last_m, acc_buy = initial_cap, 0, 0, 0, -1, 0
    budget = cash / splits
    target_pct = 15.0 if any(x in ticker_name for x in ["TQQQ", "SOXL", "BITU"]) else 20.0
    equity = []
    for i in range(len(df)):
        p, d = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, dep_day): wait_cash += monthly_amt; last_m = d.month
        t_val = acc_buy / budget if budget > 0 else 0
        if shares > 0 and (p - avg_p)/avg_p >= target_pct/100:
            sell_q = shares * 0.75
            cash += sell_q * p; shares -= sell_q; acc_buy -= (sell_q * avg_p)
            if acc_buy < 0: acc_buy = 0
        buy_amt = budget if (t_val < splits/2 and (p <= avg_p or avg_p == 0)) or (t_val >= splits/2 and p <= avg_p * 1.1) else 0
        if cash >= buy_amt and buy_amt > 0:
            cnt = buy_amt / p
            avg_p = (shares * avg_p + buy_amt) / (shares + cnt) if shares > 0 else p
            shares += cnt; cash -= buy_amt; acc_buy += buy_amt
        equity.append(cash + wait_cash + shares * p)
    return equity

def run_vr(df, initial_cap, G_val, Band_val, monthly_amt, dep_day):
    pool, shares, target_val = initial_cap * 0.5, (initial_cap * 0.5) / df['Close'].iloc[0], initial_cap * 0.5
    daily_growth = (1 + G_val/100.0) ** (1/252) - 1
    last_m, equity = -1, []
    for i in range(len(df)):
        p, d = df['Close'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, dep_day): pool += monthly_amt; target_val += monthly_amt; last_m = d.month
        target_val *= (1 + daily_growth); cur_val = shares * p
        if cur_val < target_val * (1 - Band_val/100):
            diff = min(target_val * (1 - Band_val/100) - cur_val, pool)
            shares += diff / p; pool -= diff
        elif cur_val > target_val * (1 + Band_val/100):
            diff = cur_val - target_val * (1 + Band_val/100)
            shares_to_sell = diff / p
            if shares >= shares_to_sell: shares -= shares_to_sell; pool += diff
        equity.append(cur_val + pool)
    return equity

# --- 실행 ---
if run_btn:
    df = get_data(ticker, start_date)
    if not df.empty:
        res = pd.DataFrame(index=df.index)
        res['Simple DCA'] = run_simple_dca(df, initial_capital, monthly_amount, deposit_day)
        res['V1'] = run_v1(df, initial_capital, split_v1_v2, monthly_amount, deposit_day)
        res['V2.2'] = run_v22(df, initial_capital, split_v1_v2, monthly_amount, deposit_day)
        res['V3.0'] = run_v3(df, initial_capital, split_v3, monthly_amount, deposit_day, ticker)
        res['VR'] = run_vr(df, initial_capital, vr_g_value, vr_band_value, monthly_amount, deposit_day)
        
        p_list, cur_p, l_m = [], initial_capital, -1
        for d in df.index:
            if is_deposit_day(d, l_m, deposit_day): cur_p += monthly_amount; l_m = d.month
            p_list.append(cur_p)
        res['원금'] = p_list

        mdd_df = pd.DataFrame(index=res.index)
        for col in ['Simple DCA', 'V1', 'V2.2', 'V3.0', 'VR']:
            mdd_df[col] = (res[col] - res[col].cummax()) / res[col].cummax() * 100

        tab1, tab2 = st.tabs(["💰 자산 추이", "📉 MDD 리스크 비교"])
        with tab1: st.plotly_chart(px.line(res, x=res.index, y=res.columns, title="전략별 평가액 비교"), use_container_width=True)
        with tab2: st.plotly_chart(px.line(mdd_df, x=mdd_df.index, y=mdd_df.columns, title="전략별 실제 낙폭(MDD)"), use_container_width=True)

        st.write("### 🏁 최종 성과 요약")
        final_p = res['원금'].iloc[-1]
        summary = []
        for col in mdd_df.columns:
            fv = res[col].iloc[-1]
            summary.append({"전략": col, "최종자산": f"${fv:,.0f}", "수익률": f"{((fv-final_p)/final_p)*100:.1f}%", "최대낙폭": f"{mdd_df[col].min():.1f}%"})
        st.table(pd.DataFrame(summary).set_index("전략"))
