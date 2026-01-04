# 기존 get_data 함수를 지우고 아래 코드로 통째로 교체하세요.

@st.cache_data
def get_data(ticker, start):
    try:
        # 1. 기본 다운로드 (옵션 최소화)
        df = yf.download(ticker, start=start, progress=False)
        
        if df.empty:
            st.error(f"'{ticker}' 데이터를 받아오지 못했습니다. 티커 철자를 확인하세요.")
            return pd.DataFrame()

        # 2. 데이터 구조 평탄화 (yfinance 최신 버전 호환성 해결)
        # 경우의 수 A: 컬럼이 MultiIndex인 경우 (예: ('Adj Close', 'TQQQ'))
        if isinstance(df.columns, pd.MultiIndex):
            # 'Adj Close'나 'Close'가 포함된 레벨을 찾음
            # 보통 level 0이 가격 종류(Price), level 1이 티커(Ticker)입니다.
            try:
                # 수정 종가(Adj Close) 우선 확보 시도
                if 'Adj Close' in df.columns.get_level_values(0):
                    df = df.xs('Adj Close', axis=1, level=0)
                elif 'Close' in df.columns.get_level_values(0):
                    df = df.xs('Close', axis=1, level=0)
                else:
                    # 만약 구조가 반대라면 (Ticker, Price)
                    df = df.xs(ticker, axis=1, level=0)
            except Exception:
                # 구조가 복잡하면 그냥 첫 번째 컬럼을 가져와서 씁니다 (최후의 수단)
                df = df.iloc[:, 0].to_frame()

        # 경우의 수 B: 단일 인덱스인데 컬럼명이 여러개인 경우
        # (원하는 컬럼만 남기고 'Close'로 이름 변경)
        target_col = None
        for col in ['Adj Close', 'adj close', 'Close', 'close']:
            if col in df.columns:
                target_col = col
                break
        
        if target_col:
            df = df[[target_col]].copy()
            df.rename(columns={target_col: 'Close'}, inplace=True)
        else:
            # 컬럼 이름을 못 찾았으면 첫번째 컬럼을 그냥 Close로 간주
            df.columns = ['Close']

        # 3. 숫자형 변환 및 결측치 제거
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df.dropna(inplace=True)

        return df

    except Exception as e:
        st.error(f"데이터 처리 중 치명적 오류: {e}")
        st.write("yfinance 버전을 확인해주세요. 터미널에서 `pip install --upgrade yfinance`를 실행해보세요.")
        return pd.DataFrame()
