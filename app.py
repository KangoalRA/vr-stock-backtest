import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
import math

# --- 페이지 설정 ---
st.set_page_config(page_title="VR & 적립식 백테스트", layout="wide")

st.title("📊 라오어 전략 vs 적립식 존버 (동일 현금흐름 비교)")
st.markdown("""
**핵심 비교 포인트:**
1. **Simple DCA (무지성 적립):** 월급 들어오면 그 날 바로 풀매수 (비교 기준)
2. **무매법 (V1~V3, IBS):** 월급은 '대기 자금'으로 보관하다가, **익절(리셋) 시** 시드에 합산하여 스케일업
3. **VR (Value Rebalancing):** 월급 입금 시 **Pool 추가 + 목표가치 상향** (로직 오작동 방지)
""")

# --- 사이드바 설정 ---
st.sidebar.header("📝 기본 및 적립 설정")
ticker = st.sidebar.selectbox("티커 (Ticker)", ["SOXL", "TQQQ", "TECL", "UPRO"])
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

# --- 데이터 가져오기 (수정됨: 안정성 강화) ---
@st.cache_data
def get_data(ticker, start):
    try:
        # multi_level_index=False 옵션 추가로 데이터 구조 꼬임 방지
        df = yf.download(ticker, start=start, progress=False, multi_level_index=False)
        
        if df.empty:
            return pd.DataFrame()

        # 'Adj Close' 우선 사용, 없으면 'Close' 사용
        col = 'Adj Close' if 'Adj Close' in df.columns else 'Close'
        
        # 필요한 컬럼만 남기고 이름 변경
        df = df[[col]].rename(columns={col: 'Close'})
        return df
    except Exception as e:
        st.error(f"데이터 로딩 오류: {e}")
        return pd.DataFrame()

# =========================================================
# 0. 벤치마크: Simple DCA (무지성 적립식)
# =========================================================
def run_simple_dca(df, initial_cap, monthly_amt, dep_day):
    cash = initial_cap
    shares = 0
    equity = []
    
    start_price = df['Close'].iloc[0]
    shares += cash / start_price
    cash = 0
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if date.day == dep_day:
            shares += monthly_amt / price 
            
        equity.append(shares * price)
    return equity

# =========================================================
# 1. V1.0 (적립금 대기 -> 리셋 시 합산)
# =========================================================
def run_v1(df, initial_cap, splits, monthly_amt, dep_day):
    cash = initial_cap
    waiting_cash = 0 
    shares = 0
    avg_price = 0
    one_time_budget = initial_cap / splits
    equity = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if date.day == dep_day:
            waiting_cash += monthly_amt
            
        if shares > 0 and avg_price > 0:
            profit_rate = (price - avg_price) / avg_price
            if profit_rate >= 0.1:
                cash += shares * price
                shares = 0
                avg_price = 0
                cash += waiting_cash
                waiting_cash = 0
                one_time_budget = cash / splits
        
        if cash >= one_time_budget:
            cnt = one_time_budget / price
            if shares > 0:
                avg_price = (shares * avg_price + one_time_budget) / (shares + cnt)
            else:
                avg_price = price
            shares += cnt
            cash -= one_time_budget
            
        equity.append(cash + waiting_cash + shares * price)
    return equity

# =========================================================
# 2. V2.2 (적립금 대기 -> 리셋 시 합산)
# =========================================================
def run_v22(df, initial_cap, splits, monthly_amt, dep_day):
    cash = initial_cap
    waiting_cash = 0
    shares = 0
    avg_price = 0
    daily_budget = initial_cap / splits
    accumulated_buy = 0
    equity = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if date.day == dep_day:
            waiting_cash += monthly_amt
            
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
# 3. V3.0 (적립금 대기 -> 리셋 시 합산)
# =========================================================
def run_v3(df, initial_cap, ticker_name, splits, monthly_amt, dep_day):
    cash = initial_cap
    waiting_cash = 0
    shares = 0
    avg_price = 0
    accumulated_buy = 0
    one_time_budget = initial_cap / splits
    target_pct = 15.0 if ticker_name == "TQQQ" else 20.0
    t_factor = 1.5 if ticker_name == "TQQQ" else 2.0
    quarter_mode_days = 0
    equity = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if date.day == dep_day:
            waiting_cash += monthly_amt
            
        t_val = math.ceil((accumulated_buy / one_time_budget) * 100) / 100 if one_time_budget > 0 else 0
        star_pct = target_pct - (t_factor * t_val)
        
        sell_qty = 0
        if shares > 0 and avg_price > 0:
            if t_val >= splits: 
                if quarter_mode_days == 0: sell_qty = shares * 0.25; quarter_mode_days = 1
                else: quarter_mode_days += 1
                if quarter_mode_days > 5: quarter_mode_days = 0
                star_pct = -15.0 if ticker_name == "TQQQ" else -20.0
            else:
                quarter_mode_days = 0
            
            profit_rate = (price - avg_price) / avg_price
            if profit_rate >= (target_pct / 100):
                sell_qty = shares * 0.75
                realized_val = sell_qty * price
                profit_amt = realized_val - (sell_qty * avg_price)
                if profit_amt > 0:
                    one_time_budget += (profit_amt * 0.5 / 40)
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
# 4. IBS (적립금 대기 -> 리셋 시 합산)
# =========================================================
def run_ibs(df, initial_cap, ticker_name, splits, monthly_amt, dep_day):
    cash = initial_cap
    waiting_cash = 0
    shares = 0
    avg_price = 0
    accumulated_buy = 0
    one_time_budget = initial_cap / splits
    target_pct = 15.0 if ticker_name == "TQQQ" else 20.0
    t_factor = 3.0 if ticker_name == "TQQQ" else 4.0
    equity = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if date.day == dep_day: waiting_cash += monthly_amt
            
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
# 5. VR (즉시 반영: Pool 추가 + 목표가치 상향)
# =========================================================
def run_vr(df, initial_cap, target_cagr, band_pct, monthly_amt, dep_day):
    pool_cash = initial_cap * 0.5
    shares = (initial_cap * 0.5) / df['Close'].iloc[0]
    daily_growth = (1 + target_cagr/100.0) ** (1/252) - 1
    target_val = initial_cap * 0.5 
    equity = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        
        if date.day == dep_day:
            pool_cash += monthly_amt
            target_val += monthly_amt 
            
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
    with st.spinner('전략 엔진 가동 중...'):
        df = get_data(ticker, start_date)
        if df.empty:
            st.error("데이터 로딩 실패")
        else:
            res = pd.DataFrame(index=df.index)
            res['Simple DCA (적립식)'] = run_simple_dca(df, initial_capital, monthly_amount, deposit_day)
            res[f'V1 ({split_v1_v2})'] = run_v1(df, initial_capital, split_v1_v2, monthly_amount, deposit_day)
            res[f'V2.2 ({split_v1_v2})'] = run_v22(df, initial_capital, split_v1_v2, monthly_amount, deposit_day)
            res[f'V3.0 ({split_v3})'] = run_v3(df, initial_capital, ticker, split_v3, monthly_amount, deposit_day)
            res[f'IBS ({split_ibs})'] = run_ibs(df, initial_capital, ticker, split_ibs, monthly_amount, deposit_day)
            res[f'VR ({vr_target_return}%)'] = run_vr(df, initial_capital, vr_target_return, 5.0, monthly_amount, deposit_day)
            
            fig = px.line(res, x=res.index, y=res.columns, title=f"🚀 {ticker} 적립식 전략 비교 (월 ${monthly_amount} 투입)")
            st.plotly_chart(fig)
            
            st.write("### 🏁 최종 자산 현황")
            st.write(f"**기간:** {start_date} ~ {df.index[-1].date()} | **총 투입 원금 (추산):** ${initial_capital + monthly_amount * (len(df)//21):,.0f}")
            
            cols = st.columns(len(res.columns))
            for i, col in enumerate(res.columns):
                final = res[col].iloc[-1]
                cols[i].metric(col, f"${final:,.0f}")
