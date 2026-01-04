import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import math
import numpy as np
from datetime import datetime

# --- [0. 페이지 설정] ---
st.set_page_config(page_title="라오어 & ISA-VR 역사적 데이터 백테스트", layout="wide")

st.title("⚖️ 역사적 FnG 반영: ISA-VR vs 표준 전략 분석")
st.info("💡 이미지(image_afe748.png)의 2013-2025 월별 FnG 데이터를 적용한 정밀 백테스트 버전입니다.")

# --- [1. 역사적 FnG 데이터 (이미지에서 추출)] ---
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
with st.sidebar:
    st.header("📝 설정")
    ticker = st.selectbox("대상 티커", ["TQQQ", "SOXL", "BITU", "TSLA"])
    start_year = st.selectbox("시작 연도", sorted(FNG_HISTORY.keys()), index=10) # 2023년 기본
    initial_cap = st.number_input("초기 거치금 (USD)", value=10000)
    monthly_amt = st.number_input("월 적립금 (USD)", value=1000)
    common_g = st.radio("공통 G값", [10, 20], index=0)
    common_band = st.slider("공통 밴드 (%)", 5, 20, 15) / 100

run_btn = st.sidebar.button("백테스트 실행 🚀")

# --- [3. 유틸리티 및 전략 함수] ---
@st.cache_data
def get_data(ticker, start):
    df = yf.download([ticker, "^NDX"], start=f"{start}-01-01", progress=False, auto_adjust=True)
    if df.empty: return pd.DataFrame()
    close_df = df['Close'].copy().rename(columns={ticker: 'Asset', "^NDX": 'Nasdaq'})
    close_df['Nasdaq_200MA'] = close_df['Nasdaq'].rolling(window=200).mean()
    return close_df.dropna()

def is_deposit_day(curr, last_m, target_d):
    return curr.month != last_m and curr.day >= target_d

def run_simple_dca(df, initial, monthly):
    shares, last_m, equity = initial / df['Asset'].iloc[0], -1, []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, 25): shares += monthly / p; last_m = d.month
        equity.append(shares * p)
    return equity

def run_standard_vr(df, initial, g, band, monthly):
    pool, shares, v = initial*0.5, (initial*0.5)/df['Asset'].iloc[0], initial*0.5
    last_m, equity = -1, []
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        if is_deposit_day(d, last_m, 25): pool += monthly; v += monthly; last_m = d.month
        v += (pool / g) / 252 # VR 5.0 공식 반영
        cur = shares * p
        if cur < v * (1 - band):
            buy = min(v*(1-band)-cur, pool*0.75)
            shares += buy/p; pool -= buy
        elif cur > v * (1 + band):
            sell = (cur - v*(1+band))/p
            if shares >= sell: shares -= sell; pool += (sell * p)
        equity.append(shares * p + pool)
    return equity

def run_isa_vr_dynamic(df, initial, g, band_max, monthly, fng_map):
    pool, shares, v = initial*0.5, (initial*0.5)/df['Asset'].iloc[0], initial*0.5
    last_m, equity = -1, []
    nasdaq_high = df['Nasdaq'].iloc[0]
    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        ndx, ndx_ma = df['Nasdaq'].iloc[i], df['Nasdaq_200MA'].iloc[i]
        
        # 매월 1일 FnG 업데이트
        current_fng = fng_map.get(d.year, {}).get(d.month, 50)
        
        if is_deposit_day(d, last_m, 25): pool += monthly; v += monthly; last_m = d.month
        v += (pool / g) / 252
        
        nasdaq_high = max(nasdaq_high, ndx)
        dd = (ndx/nasdaq_high - 1) * 100
        
        # 동적 밴드 & 안전장치 (사용자 로직)
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

# --- [4. 결과 출력] ---
if run_btn:
    data = get_data(ticker, start_year)
    if not data.empty:
        res = pd.DataFrame(index=data.index)
        res['Simple DCA'] = run_simple_dca(data, initial_cap, monthly_amt)
        res['표준 VR'] = run_standard_vr(data, initial_capital, common_g, common_band, monthly_amt)
        res['ISA-VR (역사적 FnG)'] = run_isa_vr_dynamic(data, initial_capital, common_g, common_band, monthly_amt, FNG_HISTORY)
        
        # 원금 계산
        p_list, cur_p, l_m = [], initial_cap, -1
        for d in data.index:
            if is_deposit_day(d, l_m, 25): cur_p += monthly_amt; l_m = d.month
            p_list.append(cur_p)
        res['투입 원금'] = p_list

        st.plotly_chart(px.line(res, x=res.index, y=res.columns, title=f"전략 비교: {ticker} (FnG 동적 반영)"), use_container_width=True)
        
        # 요약 표
        final_p = res['투입 원금'].iloc[-1]
        summary = []
        for col in res.columns[:-1]:
            fv = res[col].iloc[-1]
            mdd = ((res[col] / res[col].cummax()) - 1).min() * 100
            summary.append({"전략": col, "최종자산": f"${fv:,.0f}", "수익률": f"{((fv/final_p)-1)*100:.2f}%", "MDD": f"{mdd:.2f}%"})
        st.table(pd.DataFrame(summary).set_index("전략"))
