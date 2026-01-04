import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import math

# --- 페이지 설정 ---
st.set_page_config(page_title="VR & 무한매수법 백테스트 Pro", layout="wide")

st.title("📊 라오어 전략 vs 적립식 (통합 수정버전)")
st.info("💡 수정 완료: 데이터 로딩 오류 해결 + 휴장일 적립금 누락 방지 + MDD 분석 기능 추가")

# --- 사이드바 설정 ---
st.sidebar.header("📝 기본 및 적립 설정")
ticker = st.sidebar.selectbox("티커 (Ticker)", ["TQQQ", "SOXL", "TECL", "UPRO", "QLD", "SSO", "TSLA", "NVDA", "BITU"])
start_date = st.sidebar.date_input("시작 날짜", value=pd.to_datetime("2021-01-01"))
initial_capital = st.sidebar.number_input("초기 거치금 (USD)", value=10000, step=1000)

st.sidebar.markdown("### 💰 월 적립금 설정")
monthly_amount = st.sidebar.number_input("월 적립금 (USD)", value=1000, step=100)
deposit_day = st.sidebar.slider("매월 입금일 (일)", 1, 28, 25)

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 전략 세부 설정")
split_v1_v2 = st.sidebar.number_input("V1, V2 분할 수", value=40)
split_v3 = st.sidebar.number_input("V3.0 분할 수", value=20)
split_ibs = st.sidebar.number_input("IBS 분할 수", value=10)
vr_target_return = st.sidebar.number_input("VR 연 목표 수익률 (%)", value=15.0)

run_btn = st.sidebar.button("백테스트 실행 🚀")

# --- [강력해진] 데이터 가져오기 함수 ---
@st.cache_data
def get_data(ticker, start):
    try:
        # 1. 기본 다운로드
        df = yf.download(ticker, start=start, progress=False, auto_adjust=False)
        
        if df.empty:
            return pd.DataFrame()

        # 2. 멀티인덱스 및 컬럼 구조 평탄화 (yfinance 버전 호환성 해결)
        if isinstance(df.columns, pd.MultiIndex):
            try:
                # 'Adj Close'가 있으면 우선 사용, 없으면 'Close'
                if 'Adj Close' in df.columns.get_level_values(0):
                    df = df.xs('Adj Close', axis=1, level=0)
                elif 'Close' in df.columns.get_level_values(0):
                    df = df.xs('Close', axis=1, level=0)
                else:
                    # 티커 레벨로 접근 시도
                    df = df.xs(ticker, axis=1, level=1)
            except:
                pass

        # 3. 컬럼명 정규화 (무조건 'Close'로 통일)
        target_col = None
        for col in ['Adj Close', 'adj close', 'Close', 'close']:
            if col in df.columns:
                target_col = col
                break
        
        if target_col:
            df = df[[target_col]].copy()
            df.rename(columns={target_col: 'Close'}, inplace=True)
        else:
            # 컬럼이 하나만 남았다고 가정하고 강제 지정
            if len(df.columns) >= 1:
                df = df.iloc[:, [0]]
                df.columns = ['Close']
            else:
                return pd.DataFrame()

        # 4. 숫자형 변환 및 결측치 제거
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df.dropna(inplace=True)
        return df

    except Exception as e:
        st.error(f"데이터 로딩 중 오류 발생: {e}")
        return pd.DataFrame()

# --- [핵심] 입금일 체크 함수 (휴장일 대응) ---
def is_deposit_day(current_date, last_deposit_month, target_day):
    """이번 달에 입금 안 했고, 오늘이 설정일 이후면 입금"""
    if current_date.month != last_deposit_month and current_date.day >= target_day:
        return True
    return False

# =========================================================
# 0. 벤치마크: Simple DCA (적립식) - 휴장일 패치 적용
# =========================================================
def run_simple_dca(df, initial_cap, monthly_amt, dep_day):
    cash = initial_cap
    shares = 0
    equity = []
    last_dep_month = -1
    
    start_price = df['Close'].iloc[0]
    shares += cash / start_price
    cash = 0
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if is_deposit_day(date, last_dep_month, dep_day):
            shares += monthly_amt / price 
            last_dep_month = date.month
            
        equity.append(shares * price)
    return equity

# =========================================================
# 1. V1.0 - 휴장일 패치 적용
# =========================================================
def run_v1(df, initial_cap, splits, monthly_amt, dep_day):
    cash = initial_cap
    waiting_cash = 0 
    shares = 0
    avg_price = 0
    one_time_budget = initial_cap / splits
    equity = []
    last_dep_month = -1
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if is_deposit_day(date, last_dep_month, dep_day):
            waiting_cash += monthly_amt
            last_dep_month = date.month
            
        if shares > 0 and avg_price > 0:
            profit_rate = (price - avg_price) / avg_price
            if profit_rate >= 0.1:
                cash += shares * price
                shares = 0; avg_price = 0
                cash += waiting_cash
                waiting_cash = 0
                one_time_budget = cash / splits
        
        if cash >= one_time_budget:
            cnt = one_time_budget / price
            if shares > 0: avg_price = (shares * avg_price + one_time_budget) / (shares + cnt)
            else: avg_price = price
            shares += cnt
            cash -= one_time_budget
            
        equity.append(cash + waiting_cash + shares * price)
    return equity

# =========================================================
# 2. V2.2 - 휴장일 패치 적용
# =========================================================
def run_v22(df, initial_cap, splits, monthly_amt, dep_day):
    cash = initial_cap
    waiting_cash = 0
    shares = 0
    avg_price = 0
    daily_budget = initial_cap / splits
    accumulated_buy = 0
    equity = []
    last_dep_month = -1
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if is_deposit_day(date, last_dep_month, dep_day):
            waiting_cash += monthly_amt
            last_dep_month = date.month
            
        t_val = math.ceil((accumulated_buy / daily_budget) * 100) / 100 if daily_budget > 0 else 0
        
        if shares > 0 and avg_price > 0:
            profit_rate = (price - avg_price) / avg_price
            if profit_rate >= 0.1:
                cash += shares * price
                shares = 0; avg_price = 0; accumulated_buy = 0
                cash += waiting_cash
                waiting_cash = 0
                daily_budget = cash / splits
        
        loc_pct = 10 - (t_val / 2)
        loc_price = avg_price * (1 + loc_pct/100) if avg_price > 0 else price * 1.1
        
        buy_amt = 0
        if t_val < splits/2:
            if avg_price == 0 or price <= avg_price: buy_amt += daily_budget * 0.5
            if price <= loc_price: buy_amt += daily_budget * 0.5
        else:
            if price <= loc_price: buy_amt = daily_budget
            
        if cash >= buy_amt and buy_amt > 0:
            cnt = buy_amt / price
            if shares > 0: avg_price = (shares * avg_price + buy_amt) / (shares + cnt)
            else: avg_price = price
            shares += cnt; cash -= buy_amt; accumulated_buy += buy_amt
            
        equity.append(cash + waiting_cash + shares * price)
    return equity

# =========================================================
# 3. V3.0 - 휴장일 패치 적용
# =========================================================
def run_v3(df, initial_cap, ticker_name, splits, monthly_amt, dep_day):
    cash = initial_cap
    waiting_cash = 0
    shares = 0
    avg_price = 0
    accumulated_buy = 0
    one_time_budget = initial_cap / splits
    last_dep_month = -1
    
    target_pct = 15.0 if "TQQQ" in ticker_name or "SOXL" in ticker_name else 20.0
    t_factor = 1.5 if "TQQQ" in ticker_name or "SOXL" in ticker_name else 2.0
    quarter_mode_days = 0
    equity = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if is_deposit_day(date, last_dep_month, dep_day):
            waiting_cash += monthly_amt
            last_dep_month = date.month
            
        t_val = math.ceil((accumulated_buy / one_time_budget) * 100) / 100 if one_time_budget > 0 else 0
        star_pct = target_pct - (t_factor * t_val)
        
        sell_qty = 0
        if shares > 0 and avg_price > 0:
            if t_val >= splits: 
                if quarter_mode_days == 0: sell_qty = shares * 0.25; quarter_mode_days = 1
                else: quarter_mode_days += 1
                if quarter_mode_days > 5: quarter_mode_days = 0
                star_pct = -15.0
            else:
                quarter_mode_days = 0
            
            profit_rate = (price - avg_price) / avg_price
            if profit_rate >= (target_pct / 100):
                sell_qty = shares * 0.75
                realized_val = sell_qty * price
                profit_amt = realized_val - (sell_qty * avg_price)
                if profit_amt > 0: one_time_budget += (profit_amt * 0.5 / 40)
                quarter_mode_days = 0
            elif sell_qty == 0 and price >= avg_price * (1 + star_pct/100):
                sell_qty = shares * 0.25

            if sell_qty > 0:
                cash += sell_qty * price
                accumulated_buy -= (sell_qty * avg_price)
                if accumulated_buy < 0: accumulated_buy = 0
                shares -= sell_qty
        
        if shares <= 0.001:
            shares = 0; avg_price = 0; accumulated_buy = 0; quarter_mode_days = 0
            cash += waiting_cash
            waiting_cash = 0
            one_time_budget = cash / splits

        buy_amt = 0
        if t_val < splits/2:
            if avg_price == 0 or price <= avg_price: buy_amt += one_time_budget * 0.5
            if price <= avg_price * (1 + star_pct/100): buy_amt += one_time_budget * 0.5
        else:
            if price <= avg_price * (1 + star_pct/100): buy_amt = one_time_budget
            
        if cash >= buy_amt and buy_amt > 0:
            cnt = buy_amt / price
            if shares > 0: avg_price = (shares * avg_price + buy_amt) / (shares + cnt)
            else: avg_price = price
            shares += cnt; cash -= buy_amt; accumulated_buy += buy_amt
            
        equity.append(cash + waiting_cash + shares * price)
    return equity

# =========================================================
# 4. IBS - 휴장일 패치 적용
# =========================================================
def run_ibs(df, initial_cap, ticker_name, splits, monthly_amt, dep_day):
    cash = initial_cap
    waiting_cash = 0
    shares = 0
    avg_price = 0
    accumulated_buy = 0
    one_time_budget = initial_cap / splits
    last_dep_month = -1
    
    target_pct = 15.0 if "TQQQ" in ticker_name or "SOXL" in ticker_name else 20.0
    t_factor = 3.0 if "TQQQ" in ticker_name or "SOXL" in ticker_name else 4.0
    equity = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if is_deposit_day(date, last_dep_month, dep_day):
            waiting_cash += monthly_amt
            last_dep_month = date.month
            
        t_val = math.ceil((accumulated_buy / one_time_budget) * 100) / 100 if one_time_budget > 0 else 0
        star_pct = target_pct - (t_factor * t_val)
        
        sell_qty = 0
        if shares > 0:
            profit_rate = (price - avg_price) / avg_price if avg_price > 0 else 0
            sell_unit = shares / t_val if t_val > 0 else shares
            
            if t_val > 9:
                sell_qty = min(shares, sell_unit)
                if (shares - sell_qty) > 0 and profit_rate >= (target_pct/100): sell_qty = shares
            elif t_val < 1:
                if price >= avg_price * (1 + star_pct/100): sell_qty = shares
            else:
                if price >= avg_price * (1 + star_pct/100): sell_qty = min(shares, sell_unit)
                if (shares - sell_qty) > 0 and profit_rate >= (target_pct/100): sell_qty = shares
            
            if sell_qty > 0:
                cash += sell_qty * price
                accumulated_buy -= (sell_qty * avg_price)
                if accumulated_buy < 0: accumulated_buy = 0
                shares -= sell_qty
                
        if shares <= 0.001:
            shares = 0; avg_price = 0; accumulated_buy = 0; t_val = 0
            cash += waiting_cash
            waiting_cash = 0
            one_time_budget = cash / splits

        limit_price = avg_price * (1 + star_pct/100) if avg_price > 0 else price * 1.1
        if price <= limit_price:
            buy_amt = one_time_budget
            if cash >= buy_amt:
                cnt = buy_amt / price
                if shares > 0: avg_price = (shares * avg_price + buy_amt) / (shares + cnt)
                else: avg_price = price
                shares += cnt; cash -= buy_amt; accumulated_buy += buy_amt
                
        equity.append(cash + waiting_cash + shares * price)
    return equity

# =========================================================
# 5. VR - 휴장일 패치 적용
# =========================================================
def run_vr(df, initial_cap, target_cagr, band_pct, monthly_amt, dep_day):
    pool_cash = initial_cap * 0.5
    shares = (initial_cap * 0.5) / df['Close'].iloc[0]
    daily_growth = (1 + target_cagr/100.0) ** (1/252) - 1
    target_val = initial_cap * 0.5 
    equity = []
    last_dep_month = -1
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if is_deposit_day(date, last_dep_month, dep_day):
            pool_cash += monthly_amt
            target_val += monthly_amt 
            last_dep_month = date.month
            
        target_val *= (1 + daily_growth) 
        
        current_val = shares * price
        min_b = target_val * (1 - band_pct/100)
        max_b = target_val * (1 + band_pct/100)
        
        if current_val < min_b: 
            diff = min_b - current_val
            if pool_cash > 0:
                amt = min(diff, pool_cash)
                shares += amt / price
                pool_cash -= amt
        elif current_val > max_b: 
            diff = current_val - max_b
            qty = diff / price
            if shares >= qty:
                shares -= qty
                pool_cash += diff
                
        equity.append((shares * price) + pool_cash)
    return equity

# --- 메인 실행 ---
if run_btn:
    with st.spinner('전략 엔진 가동 중... (데이터 다운로드 및 계산)'):
        df = get_data(ticker, start_date)
        
        if df.empty:
            st.error("데이터를 가져올 수 없습니다. 티커를 확인해주세요.")
        else:
            res = pd.DataFrame(index=df.index)
            
            # 1. 전략별 자산 계산
            res['Simple DCA'] = run_simple_dca(df, initial_capital, monthly_amount, deposit_day)
            res[f'V1'] = run_v1(df, initial_capital, split_v1_v2, monthly_amount, deposit_day)
            res[f'V2.2'] = run_v22(df, initial_capital, split_v1_v2, monthly_amount, deposit_day)
            res[f'V3.0'] = run_v3(df, initial_capital, ticker, split_v3, monthly_amount, deposit_day)
            res[f'IBS'] = run_ibs(df, initial_capital, ticker, split_ibs, monthly_amount, deposit_day)
            res[f'VR'] = run_vr(df, initial_capital, vr_target_return, 5.0, monthly_amount, deposit_day)
            
            # 2. 총 투입 원금 (휴장일 보정 적용)
            principal_list = []
            current_principal = initial_capital
            last_dep_month = -1
            
            for date in df.index:
                if is_deposit_day(date, last_dep_month, deposit_day):
                    current_principal += monthly_amount
                    last_dep_month = date.month
                principal_list.append(current_principal)
            
            res['총 투입 원금'] = principal_list
            
            # 3. MDD 계산
            mdd_df = pd.DataFrame(index=res.index)
            for col in res.columns:
                if col == '총 투입 원금': continue
                rolling_max = res[col].cummax()
                drawdown = (res[col] - rolling_max) / rolling_max * 100
                mdd_df[col] = drawdown

            # 4. 시각화 (탭으로 구분)
            st.write("### 📈 전략 성과 및 리스크 분석")
            tab1, tab2 = st.tabs(["자산 추이 (수익금)", "MDD (최대 낙폭)"])
            
            with tab1:
                fig = px.line(res, x=res.index, y=res.columns, 
                              title=f"{ticker} 전략별 수익금 비교",
                              labels={"value": "자산 (USD)", "variable": "전략"})
                fig.update_traces(patch={"line": {"dash": "dot", "color": "gray", "width": 2}}, selector={"name": "총 투입 원금"})
                st.plotly_chart(fig, use_container_width=True)
                
            with tab2:
                fig_mdd = px.area(mdd_df, x=mdd_df.index, y=mdd_df.columns,
                                  title=f"{ticker} 전략별 MDD 추이",
                                  labels={"value": "낙폭 (%)", "variable": "전략"})
                st.plotly_chart(fig_mdd, use_container_width=True)
            
            # 5. 최종 요약표
            st.write("### 🏁 최종 성과 요약")
            final_principal = res['총 투입 원금'].iloc[-1]
            summary_data = []
            
            for col in res.columns:
                if col == '총 투입 원금': continue
                final_val = res[col].iloc[-1]
                profit_pct = ((final_val - final_principal) / final_principal) * 100
                min_mdd = mdd_df[col].min()
                summary_data.append({
                    "전략": col,
                    "최종 자산": f"${final_val:,.0f}",
                    "수익률": f"{profit_pct:+.2f}%",
                    "최대 낙폭 (MDD)": f"{min_mdd:.2f}%"
                })
            
            st.dataframe(pd.DataFrame(summary_data).set_index("전략"), use_container_width=True)
