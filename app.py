import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 페이지 설정
st.set_page_config(page_title="자산 시뮬레이터", layout="wide")

# 제목
st.title("💰 내 자산 성장 시뮬레이터")
st.caption("매달 저축하고 투자했을 때, 3년 뒤 얼마나 모일까?")

# 사이드바: 입력값 받기
with st.sidebar:
    st.header("설정 입력")
    current_assets = st.number_input("현재 자산 (만원)", value=1000, step=100)
    monthly_savings = st.number_input("월 저축/투자액 (만원)", value=150, step=10)
    target_years = st.slider("목표 기간 (년)", 1, 10, 3)
    annual_return = st.slider("예상 연 수익률 (%)", 0.0, 30.0, 8.0, 0.1)

# 계산 로직
months = target_years * 12
monthly_rate = annual_return / 100 / 12

data = []
total_saved = current_assets # 원금 합계
current_value = current_assets # 수익 포함 총 자산

for m in range(1, months + 1):
    # 수익 발생
    interest = current_value * monthly_rate
    # 저축 추가
    current_value += interest + monthly_savings
    total_saved += monthly_savings
    
    data.append({
        "개월차": m,
        "원금(저축액)": round(total_saved),
        "총 자산(수익포함)": round(current_value),
        "수익금": round(current_value - total_saved)
    })

# 데이터프레임 생성
df = pd.read_json(pd.Series(data).to_json(orient='records'))

# 메인 화면 구성
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("목표 기간", f"{target_years}년 ({months}개월)")
with col2:
    st.metric("예상 최종 자산", f"{int(df.iloc[-1]['총 자산(수익포함)']):,} 만원")
with col3:
    st.metric("순수익", f"+{int(df.iloc[-1]['수익금']):,} 만원", delta_color="normal")

st.divider()

# 차트 그리기
st.subheader("📈 자산 성장 그래프")
chart_data = df.set_index("개월차")[["총 자산(수익포함)", "원금(저축액)"]]

# 한글 폰트 이슈 방지를 위해 Streamlit 내장 차트 사용
st.line_chart(chart_data, color=["#FF4B4B", "#31333F"])

# 상세 데이터 테이블
with st.expander("월별 상세 데이터 보기"):
    st.dataframe(df, use_container_width=True)
