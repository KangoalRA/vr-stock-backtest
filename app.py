import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import math
import numpy as np
from datetime import datetime

# --- [0. 페이지 설정] ---
st.set_page_config(page_title="라오어 & ISA-VR 통합 백테스트", layout="wide")

st.title("📊 전 전략 통합 분석 (DCA, 무매 3종, VR 2종)")
st.info("💡 에러 수정 완료: 모든 전략 함수를 포함하였으며, G값과 밴드를 공통으로 적용합니다.")

# --- [1. 역사적 FnG 데이터 (2013-2025)] ---
# 제공해주신 이미지(image_afe748.png)의 월별 데이터를 딕셔너리로 구축했습니다.
FNG_HISTORY = {
    2013: {1:68, 2:72, 3:65, 4:58, 5:70, 6:45, 7:62, 8:55, 9:60, 10:48, 11:65, 12:71},
    2014: {1:55, 2:32, 3:58, 4:42, 5:48, 6:65, 7:68, 8:40, 9:52, 10:12, 11:60, 12:55},
    2015: {1:42, 2:55, 3:60, 4:58, 5:62, 6:55, 7:45, 8:18, 9:10, 10:45, 11:52, 12:40},
    2016: {1:22, 2:10, 3:45, 4:58, 5:52, 6:48, 7:62, 8:68, 9:55, 10:45, 11:40, 12:62},
    2017: {1:65, 2:70, 3:75, 4:60, 5:55, 6:62, 7:68, 8:58, 9:65, 10:72, 11:78, 12:82},
    2018: {1:78, 2:55, 3:42, 4:35, 5:48, 6:52, 7:58, 8:62, 9:65, 10:40, 11:25, 12:5},
    2019: {1:8, 2:45, 3:55, 4:68, 5:58, 6:42, 7:62, 8:35, 9:48, 10:38, 11:72, 12:78},
    2020: {1:88, 2:65, 3:15, 4:5, 5:35, 6:52, 7:58, 8:68, 9:55, 10:42, 11:65, 12:85},
    2021: {1:52, 2:68, 3:55, 4:72, 5:48, 6:55, 7:45, 8:58, 9:52, 10:40, 11:62, 12:55},
    2022: {1:65, 2:42, 3:35, 4:45, 5:25, 6:15, 7:25, 8:40, 9:18, 10:12, 11:45, 12:38},
    2023: {1:32, 2:62, 3:45, 4:52, 5:58, 6:65, 7:78, 8:62, 9:45, 10:32, 11:55, 12:72},
    2024: {1:75, 2:72, 3:78, 4:62, 5:55, 6:60, 7:65, 8:42, 9:52, 10:58, 11:68, 12:75},
    2025: {1:72, 2:54, 3:35, 4:8, 5:25, 6:40, 7:55, 8:48, 9:42, 10:35, 11:58, 12:65},
}

# --- [2. 사이드바 설정] ---
st.sidebar.header("📝 기본 설정")
ticker = st.sidebar.selectbox("대상 티커 (Asset)", ["TQQQ", "SOXL", "BITU", "UPRO", "TSLA"])
benchmark = "^NDX"
start_date = st.sidebar.date_input("시작 날짜", value=pd.to_datetime("2023-01-01"))
initial_capital = st.sidebar.number_input("초기 거치금 (USD)", value=10000, step=1000)
monthly_amount = st.sidebar.number_input("월 적립금 (USD)", value=1000, step=100)
deposit_day = st.sidebar.slider("매월 입금일 (일)", 1, 28, 25)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 전략 세부 설정")
split_v1_v2 = st.sidebar.number_input("V1 / V2.2 분할 횟수 (40분할)", value=40)
split_v3 = st.sidebar.number_input("V3.0 분할 횟수 (20분할)", value=20)

st.sidebar.markdown("---")
st.sidebar.header("⚖️ 공통 VR 파라미터 (G & Band)")
common_g = st.sidebar.radio("공통 G값 (기울기)", [10, 20], index=0, horizontal=True)
common_band = st.sidebar.slider("공통 밴드폭 (%)", 5, 20, 15) / 100

run_btn = st.sidebar.button("백테스트 실행 🚀")

# --- [3. 유틸리티 함수 및 전략 로직] ---
@st.cache_data
def get_combined_data(ticker, bench, start):
    try:
        df = yf.download([ticker, bench], start=start, progress=False, auto_adjust=True)
        if df.empty: return pd.DataFrame()
        close_df = df['Close'].copy().rename(columns={ticker: 'Asset', bench: 'Nasdaq'})
        close_df['Nasdaq_200MA'] = close_df['Nasdaq'].rolling(window=200).mean()
        return close_df.dropna()
    except: return pd.DataFrame()

def is_deposit_day(current_date, last_deposit_month, target_day):
    return current_date.month != last_deposit_month and current_date.day >= target_day

# A. Simple DCA
def run_simple_dca(df, initial_capital, monthly_amount, deposit_day):
    shares, last_m, equity = initial_capital / df['Asset'].iloc[0], -1, []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, deposit_day): shares += monthly_amount / p; last_m = d.month
        equity.append(shares * p)
    return equity

# B. 무한매수 V1.0 (40분할, 완전 복리)
def run_v1(df, initial_capital, splits, monthly_amount, deposit_day):
    cash, wait_cash, shares, avg_p, last_m = initial_capital, 0, 0, 0, -1
    budget = cash / splits
    equity = []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, deposit_day): wait_cash += monthly_amount; last_m = d.month
        if shares > 0 and (p - avg_p)/avg_p >= 0.1:
            cash += (shares * p) + wait_cash; shares, avg_p, wait_cash = 0, 0, 0
            budget = cash / splits # 익절 후 수익금 포함 새 예산 편성 (복리)
        if cash >= budget:
            cnt = budget / p
            avg_p = (shares * avg_p + budget) / (shares + cnt) if shares > 0 else p
            shares += cnt; cash -= budget
        equity.append(cash + wait_cash + shares * p)
    return equity

# C. 무한매수 V2.2 (40분할, T값 기반, 완전 복리)
def run_v22(df, initial_capital, splits, monthly_amount, deposit_day):
    cash, wait_cash, shares, avg_p, last_m, acc_buy = initial_capital, 0, 0, 0, -1, 0
    budget = cash / splits
    equity = []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, deposit_day): wait_cash += monthly_amount; last_m = d.month
        t_val = acc_buy / budget if budget > 0 else 0
        if shares > 0 and (p - avg_p)/avg_p >= 0.1:
            cash += (shares * p) + wait_cash; shares, avg_p, wait_cash, acc_buy = 0, 0, 0, 0
            budget = cash / splits # 복리
        loc_p = avg_p * (1 + (10 - t_val/2)/100) if avg_p > 0 else p * 1.1
        buy_amt = budget if p <= loc_p else 0
        if cash >= buy_amt and buy_amt > 0:
            cnt = buy_amt / p
            avg_p = (shares * avg_p + buy_amt) / (shares + cnt) if shares > 0 else p
            shares += cnt; cash -= buy_amt; acc_buy += buy_amt
        equity.append(cash + wait_cash + shares * p)
    return equity

# D. 무한매수 V3.0 (20분할, 쿼터매도, 완전 복리)
def run_v3(df, initial_capital, splits, monthly_amount, deposit_day, ticker):
    cash, wait_cash, shares, avg_p, last_m, acc_buy = initial_capital, 0, 0, 0, -1, 0
    budget = cash / splits
    target = 0.15 if any(x in ticker for x in ["TQQQ", "SOXL", "BITU"]) else 0.20
    equity = []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, deposit_day): wait_cash += monthly_amount; last_m = d.month
        t_val = acc_buy / budget if budget > 0 else 0
        if shares > 0:
            if (p - avg_p) / avg_p >= target:
                cash += (shares * p) + wait_cash; shares, avg_p, wait_cash, acc_buy = 0, 0, 0, 0
                budget = cash / splits # 복리
            elif t_val >= splits / 2 and p >= avg_p: # 쿼터매도
                sell_q = shares * 0.25
                cash += (sell_q * p); shares -= sell_q; acc_buy -= (sell_q * avg_p)
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

# E. 표준 VR (VR 5.0 공식)
def run_standard_vr(df, initial_capital, g_val, band_val, monthly_amount, deposit_day):
    pool, shares, v = initial_capital*0.5, (initial_capital*0.5)/df['Asset'].iloc[0], initial_capital*0.5
    last_m, equity = -1, []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, deposit_day): pool += monthly_amount; v += monthly_amount; last_m = d.month
        v += (pool / g_val) / 252 # V2 = V1 + Pool/G
        cur = shares * p
        if cur < v * (1 - band_val):
            buy = min(v*(1-band_val)-cur, pool * 0.75)
            shares += buy/p; pool -= buy
        elif cur > v * (1 + band_val):
            sell = (cur - v*(1+band_val))/p
            if shares >= sell: shares -= sell; pool += (sell * p)
        equity.append(shares * p + pool)
    return equity

# F. ISA-VR (사용자 변형 + 역사적 FnG 적용)
def run_isa_vr(df, initial_capital, g_val, band_max, monthly_amount, deposit_day, fng_map):
    pool, shares, v = initial_capital*0.5, (initial_capital*0.5)/df['Asset'].iloc[0], initial_capital*0.5
    last_m, equity = -1, []
    ndx_high = df['Nasdaq'].iloc[0]
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        ndx, ndx_ma = df['Nasdaq'].iloc[i], df['Nasdaq_200MA'].iloc[i]
        current_fng = fng_map.get(d.year, {}).get(d.month, 50) # 역사적 FnG 로드

        if is_deposit_day(d, last_m, deposit_day): pool += monthly_amount; v += monthly_amount; last_m = d.month
        v += (pool / g_val) / 252
        ndx_high = max(ndx_high, ndx); dd = (ndx/ndx_high - 1) * 100
        
        # 동적 밴드 & 안전장치
        band = 0.05 if (ndx < ndx_ma or dd <= -20) else (0.07 if dd <= -10 else band_max)
        intensity = 1.0
        if dd <= -10:
            if dd > -20: intensity = 0.5 if current_fng <= 20 else 0.0
            else: intensity = 0.3 if current_fng <= 15 else 0.0
            
        cur = shares * p
        if cur < v * (1 - band):
            buy = min((v*(1-band)-cur) * intensity, pool * 0.75)
            shares += buy/p; pool -= buy
        elif cur > v * (1 + band):
            sell = (cur - v*(1+band))/p
            if shares >= sell: shares -= sell; pool += (sell * p)
        equity.append(shares * p + pool)
    return equity

# =========================================================
# [4. 실행 및 결과 출력]
# =========================================================
if run_btn:
    data = get_combined_data(ticker, benchmark, start_date)
    if not data.empty:
        res = pd.DataFrame(index=data.index)
        # 모든 전략 함수 호출 (Naming 일치 확인 완료)
        res['Simple DCA'] = run_simple_dca(data, initial_capital, monthly_amount, deposit_day)
        res['무매 V1.0 (40분할)'] = run_v1(data, initial_capital, split_v1_v2, monthly_amount, deposit_day)
        res['무매 V2.2 (40분할)'] = run_v22(data, initial_capital, split_v1_v2, monthly_amount, deposit_day)
        res['무매 V3.0 (20분할)'] = run_v3(data, initial_capital, split_v3, monthly_amount, deposit_day, ticker)
        res['표준 VR'] = run_standard_vr(data, initial_capital, common_g, common_band, monthly_amount, deposit_day)
        res['ISA-VR (FnG반영)'] = run_isa_vr(data, initial_capital, common_g, common_band, monthly_amount, deposit_day, FNG_HISTORY)
        
        # 원금 계산
        p_list, cur_p, l_m = [], initial_capital, -1
        for d in data.index:
            if is_deposit_day(d, l_m, deposit_day): cur_p += monthly_amount; l_m = d.month
            p_list.append(cur_p)
        res['투입 원금'] = p_list

        mdd_df = (res.drop(columns=['투입 원금']) - res.drop(columns=['투입 원금']).cummax()) / res.drop(columns=['투입 원금']).cummax() * 100

        tab1, tab2 = st.tabs(["💰 자산 수익금 추이", "📉 MDD 리스크 비교"])
        with tab1:
            fig1 = px.line(res, x=res.index, y=res.columns, title=f"{ticker} 전략 통합 비교")
            fig1.update_traces(patch={"line": {"dash": "dot", "color": "gray"}}, selector={"name": "투입 원금"})
            st.plotly_chart(fig1, use_container_width=True)
        with tab2:
            st.plotly_chart(px.line(mdd_df, x=mdd_df.index, y=mdd_df.columns, title="전략별 실제 낙폭(MDD)"), use_container_width=True)

        st.write("### 🏁 최종 성과 요약")
        final_p = res['투입 원금'].iloc[-1]
        summary = []
        for col in mdd_df.columns:
            fv = res[col].iloc[-1]
            summary.append({"전략": col, "최종자산": f"${fv:,.0f}", "수익률": f"{((fv/final_p)-1)*100:.1f}%", "MDD": f"{mdd_df[col].min():.1f}%"})
        st.table(pd.DataFrame(summary).set_index("전략"))
