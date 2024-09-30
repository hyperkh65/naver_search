import streamlit as st
import urllib.request
import json
import pandas as pd
import requests
import time
import hashlib
import hmac
import base64
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# API 키 설정
CUSTOMER_ID = "your_customer_id"
API_KEY = "your_api_key"
SECRET_KEY = "your_secret_key"
client_id = "your_client_id"
client_secret = "your_client_secret"

# 서명 생성 함수
def Signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    hash = hmac.new(bytes(secret_key, "utf-8"), bytes(message, "utf-8"), hashlib.sha256)
    hash.hexdigest()
    return base64.b64encode(hash.digest())

# 요청 헤더 생성 함수
def get_request_header(method, uri, api_key, secret_key, customer_id):
    timestamp = str(int(time.time() * 1000))
    signature = Signature(timestamp, method, uri, secret_key)
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": api_key,
        "X-Customer": str(customer_id),
        "X-Signature": signature,
    }

# 키워드 분석 함수
def get_keyword_analysis(keyword):
    uri = "/keywordstool"
    method = "GET"
    
    params = {
        "hintKeywords": keyword,
        "showDetail": 1
    }
    
    base_url = "https://api.naver.com"
    req_url = f"{base_url}{uri}"
    
    headers = get_request_header(method, uri, API_KEY, SECRET_KEY, CUSTOMER_ID)
    response = requests.get(req_url, params=params, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        return data.get("keywordList", [])
    else:
        st.error(f"API 요청 실패: 상태 코드 {response.status_code}")
        return []

# 키워드 트렌드 함수 (캐싱 적용)
@st.cache_data(ttl=3600)
def get_keyword_trend(keyword, start_date, end_date):
    url = "https://openapi.naver.com/v1/datalab/search"
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "date",
        "keywordGroups": [
            {
                "groupName": keyword,
                "keywords": [keyword]
            }
        ]
    }
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", client_id)
    request.add_header("X-Naver-Client-Secret", client_secret)
    request.add_header("Content-Type", "application/json")
    try:
        response = urllib.request.urlopen(request, data=json.dumps(body).encode("utf-8"))
        rescode = response.getcode()
        if(rescode==200):
            response_body = response.read()
            data = json.loads(response_body.decode('utf-8'))
            return data['results'][0]['data']
        else:
            st.error(f"API 요청 실패: 상태 코드 {rescode}")
            return None
    except Exception as e:
        st.error(f"키워드 트렌드 요청 중 오류 발생: {str(e)}")
        return None

# 트렌드 시각화 함수
def plot_keyword_trend(trend_data, keyword):
    df = pd.DataFrame(trend_data)
    df['period'] = pd.to_datetime(df['period'])
    
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df['period'], df['ratio'])
    ax.set_title(f"{keyword} 검색 트렌드")
    ax.set_xlabel("날짜")
    ax.set_ylabel("검색량 비율")
    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig

# 세션 상태 초기화
if 'trend_data' not in st.session_state:
    st.session_state.trend_data = None
if 'selected_keyword' not in st.session_state:
    st.session_state.selected_keyword = ""

# Streamlit 앱 시작
st.title("키워드 분석 도구")

# 사이드바 입력
st.sidebar.header("검색 설정")
keyword = st.sidebar.text_input("키워드 입력", value=st.session_state.selected_keyword)
start_date = st.sidebar.date_input("시작 날짜", datetime.now() - timedelta(days=30))
end_date = st.sidebar.date_input("종료 날짜", datetime.now())

if st.sidebar.button("트렌드 보기"):
    if keyword:
        st.session_state.selected_keyword = keyword
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        st.session_state.trend_data = get_keyword_trend(keyword, start_date_str, end_date_str)

# 메인 영역에 결과 표시
if st.session_state.trend_data is not None:
    st.subheader(f"{st.session_state.selected_keyword} 트렌드")
    fig = plot_keyword_trend(st.session_state.trend_data, st.session_state.selected_keyword)
    st.pyplot(fig)
elif st.session_state.selected_keyword:
    st.warning("트렌드 데이터를 가져오는데 실패했습니다.")
else:
    st.info("키워드를 입력하고 '트렌드 보기' 버튼을 클릭하세요.")

# 키워드 분석 결과 표시
if st.sidebar.button("키워드 분석"):
    if keyword:
        analysis_results = get_keyword_analysis(keyword)
        if analysis_results:
            st.subheader("키워드 분석 결과")
            df = pd.DataFrame(analysis_results)
            st.dataframe(df)
    else:
        st.warning("키워드를 입력해주세요.")
