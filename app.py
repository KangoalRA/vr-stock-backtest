import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import math
import numpy as np

# --- 페이지 설정 ---
st.set_page_config(page_title="라오어 & ISA-VR 통합 백테스트", layout="wide")

st.title("⚖️ 전략 통합 분석 (라오어 무매법 & ISA-VR 변형)")
st.info("💡 사용자님의 'ISA-VR 변형 공식(동적 밴드 & 안전장치)'이 추가되었습니다.")

# --- 사이드바 설정 ---
st.sidebar.header("📝 기본 설정")
ticker = st.sidebar.selectbox("대상 티커 (Asset)", ["TQQQ", "SOXL", "BITU", "TSLA", "NVDA"])
benchmark = "^NDX" # 나스닥 지수 (안전장치용)
start_date = st.sidebar.date_input("시작 날짜", value=pd.to_datetime("2023-01-01"))
initial_capital = st.sidebar.number_input("초기 거치금 (USD)", value=10000, step=1000)
monthly_amount = st.sidebar.number_input("월 적립금 (USD)", value=1000, step=100)
deposit_day = st.sidebar.slider("매월 입금일 (일)", 1, 28, 25)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ ISA-VR 세부 설정")
g_val_isa = st.sidebar.radio("ISA-VR G값", [10, 20], index=0, horizontal=True)
fng_fixed = st.sidebar.slider("백테스트용 고정 FnG 지수", 0, 100, 30) # 과거 FnG 데이터 제한으로 인해 고정값 사용

run_btn = st.sidebar.button("백테스트 실행 🚀")

# --- 데이터 로딩 함수 ---
@st.cache_data
def get_combined_data(ticker, bench, start):
    try:
        # 자산 데이터와 벤치마크(나스닥) 데이터를 동시에 가져옴
        df = yf.download([ticker, bench], start=start, progress=False, auto_adjust=True)
        if df.empty: return pd.DataFrame()
        
        # MultiIndex 처리
        close_df = df['Close'].copy()
        close_df = close_df.rename(columns={ticker: 'Asset', bench: 'Nasdaq'})
        
        # 나스닥 200일 이평선 계산 (ISA-VR 불마켓 판단용)
        close_df['Nasdaq_200MA'] = close_df['Nasdaq'].rolling(window=200).mean()
        close_df.dropna(inplace=True)
        return close_df
    except: return pd.DataFrame()

def is_deposit_day(current_date, last_deposit_month, target_day):
    return current_date.month != last_deposit_month and current_date.day >= target_day

# =========================================================
# [추가됨] ISA-VR 변형 전략 함수
# =========================================================
def run_isa_vr(df, initial_cap, g_val, fng, monthly_amt, dep_day):
    # 초기 설정
    pool = initial_cap * 0.5
    shares = (initial_cap * 0.5) / df['Asset'].iloc[0]
    v_target = initial_cap * 0.5
    last_m, equity = -1, []
    
    # 나스닥 역대 고점 추적용 (DD 계산용)
    nasdaq_high = df['Nasdaq'].iloc[0]

    for i in range(len(df)):
        p, d = df['Asset'].iloc[i], df.index[i]
        ndx, ndx_ma = df['Nasdaq'].iloc[i], df['Nasdaq_200MA'].iloc[i]
        
        # 1. 입금 및 V 업데이트 (2주 사이클 대신 매일 업데이트로 시뮬레이션 최적화)
        if is_deposit_day(d, last_m, dep_day):
            pool += monthly_amt
            v_target += monthly_amt
            last_m = d.month
        
        # V 성장 공식: V_next = V + (Pool / G) [사용자 변형 공식의 수학적 결과]
        v_target += (pool / g_val) / 252 # 일일 성장분으로 환산
        
        # 2. 동적 밴드 설정 (사용자 로직 적용)
        nasdaq_high = max(nasdaq_high, ndx)
        dd = (ndx / nasdaq_high - 1) * 100
        is_bull = ndx > ndx_ma
        
        if not is_bull or dd <= -20: band_pct = 0.05 # 폭락장 5%
        elif -20 < dd <= -10: band_pct = 0.07 # 조정장 7%
        else: band_pct = 0.15 # 상승장 15% (사용자 피드백 반영)

        # 3. 안전장치 체크 (사용자 로직 적용)
        buy_intensity = 1.0
        if dd <= -10:
            if dd > -20: # 조정장
                buy_intensity = 0.5 if fng <= 20 else 0.0
            else: # 폭락장
                buy_intensity = 0.3 if fng <= 15 else 0.0

        # 4. 매매 실행
        curr_val = shares * p
        if curr_val < v_target * (1 - band_pct): # 매수 신호
            diff = (v_target * (1 - band_pct)) - curr_val
            buy_amt = min(diff * buy_intensity, pool * 0.75) # 적립식 풀 사용제한 75% 적용
            shares += buy_amt / p
            pool -= buy_amt
        elif curr_val > v_target * (1 + band_pct): # 매도 신호
            diff = curr_val - (v_target * (1 + band_pct))
            shares_to_sell = diff / p
            if shares >= shares_to_sell:
                shares -= shares_to_sell
                pool += diff
        
        equity.append((shares * p) + pool)
    return equity

# (나머지 V1, V2.2, V3.0, VR 함수들은 이전과 동일하므로 생략하거나 통합 유지)
# ... [기존 run_simple_dca, run_v1, run_v22, run_v3, run_vr 함수들] ...

# --- 메인 실행 ---
if run_btn:
    df = get_combined_data(ticker, benchmark, start_date)
    if not df.empty:
        res = pd.DataFrame(index=df.index)
        # 기존 전략들
        from copy import deepcopy # 로직 분리를 위해 호출 시 주의
        
        # 예시로 핵심만 호출
        res['Simple DCA'] = run_simple_dca(df.rename(columns={'Asset':'Close'}), initial_capital, monthly_amount, deposit_day)
        res['무매법 V3.0 (20분할)'] = run_v3(df.rename(columns={'Asset':'Close'}), initial_capital, 20, monthly_amount, deposit_day, ticker)
        res['표준 VR (G=10, B=15%)'] = run_vr(df.rename(columns={'Asset':'Close'}), initial_capital, 10, 15, monthly_amount, deposit_day)
        
        # [신규] 사용자 변형 ISA-VR
        res['ISA-VR (변형공식)'] = run_isa_vr(df, initial_capital, g_val_isa, fng_fixed, monthly_amount, deposit_day)
        
        # 원금 계산
        p_list, cur_p, l_m = [], initial_capital, -1
        for d in df.index:
            if is_deposit_day(d, l_m, deposit_day): cur_p += monthly_amount; l_m = d.month
            p_list.append(cur_p)
        res['투입 원금'] = p_list

        # 결과 시각화
        tab1, tab2 = st.tabs(["💰 수익금 추이", "📉 MDD 리스크 비교"])
        with tab1:
            st.plotly_chart(px.line(res, x=res.index, y=res.columns, title=f"{ticker} 전략 통합 비교"), use_container_width=True)
        with tab2:
            mdd_df = (res.drop(columns=['투입 원금']) - res.drop(columns=['투입 원금']).cummax()) / res.drop(columns=['투입 원금']).cummax() * 100
            st.plotly_chart(px.line(mdd_df, x=mdd_df.index, y=mdd_df.columns, title="최대 낙폭(MDD) 비교"), use_container_width=True)

        st.write("### 🏁 최종 성과 분석")
        final_p = res['투입 원금'].iloc[-1]
        summary = []
        for col in res.columns:
            if col == '투입 원금': continue
            fv = res[col].iloc[-1]
            summary.append({"전략": col, "최종자산": f"${fv:,.0f}", "수익률": f"{((fv-final_p)/final_p)*100:.1f}%", "MDD": f"{mdd_df[col].min():.1f}%"})
        st.table(pd.DataFrame(summary).set_index("전략"))
