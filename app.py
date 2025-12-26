import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 한글 폰트 설정 (깨짐 방지용, 영어로 표기)
plt.rcParams['font.family'] = 'sans-serif' 
plt.rcParams['axes.unicode_minus'] = False

st.set_page_config(page_title="자산 시뮬레이터", layout="wide")

st.title("💰 자산 성장 시뮬레이터")

with st.sidebar:
    st.header("설정")
    current_assets = st.number_input("현재 자산 (만원)", value=1000)
    monthly_savings = st.number_input("월 투자액 (만원)", value=150)
    target_years = st.slider("기간 (년)", 1, 10, 3)
    annual_return = st.slider("연 수익률 (%)", 0.0, 30.0, 8.0)

# 계산
months = target_years * 12
monthly_rate = annual_return / 100 / 12

data = []
money = current_assets
total_invested = current_assets

for m in range(1, months + 1):
    money = money * (1 + monthly_rate) + monthly_savings
    total_invested += monthly_savings
    data.append([m, round(total_invested), round(money)])

df = pd.DataFrame(data, columns=["개월", "원금", "평가금액"])

# 결과 출력
col1, col2 = st.columns(2)
with col1:
    st.metric("3년 뒤 모이는 돈", f"{int(df.iloc[-1]['평가금액']):,} 만원")
with col2:
    st.metric("순수익", f"+{int(df.iloc[-1]['평가금액'] - df.iloc[-1]['원금']):,} 만원")

# 그래프
st.line_chart(df.set_index("개월")[["평가금액", "원금"]], color=["#FF0000", "#CCCCCC"])
st.dataframe(df, use_container_width=True)
