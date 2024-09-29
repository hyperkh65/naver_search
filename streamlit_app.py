import streamlit as st
import urllib.request
import json
import pandas as pd
import requests
import time
import hashlib
import hmac
import base64
import concurrent.futures
from datetime import datetime, timedelta
import matplotlib.pyplot as plt

# Streamlit 앱 제목
st.title('네이버 키워드 분석 도구')

# 세션 상태 초기화
if 'analysis_done' not in st.session_state:
    st.session_state.analysis_done = False
if 'tmp_df' not in st.session_state:
    st.session_state.tmp_df = pd.DataFrame()

# 사이드바 설정
st.sidebar.header('분석 옵션')

# API 키 설정
CUSTOMER_ID = st.secrets["general"]["CUSTOMER_ID"]
API_KEY = st.secrets["general"]["API_KEY"]
SECRET_KEY = st.secrets["general"]["SECRET_KEY"]
client_id = st.secrets["general"]["client_id"]
client_secret = st.secrets["general"]["client_secret"]

# 키워드 입력 (사이드바)
keywords = st.sidebar.text_area('분석할 키워드를 입력하세요 (쉼표로 구분)', 'chatgpt')

BASE_URL = 'https://api.naver.com'

def Signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    hash = hmac.new(bytes(secret_key, "utf-8"), bytes(message, "utf-8"), hashlib.sha256)
    hash.hexdigest()
    return base64.b64encode(hash.digest())

def get_request_header(method, uri, api_key, secret_key, customer_id):
    timestamp = str(round(time.time() * 1000))
    signature = Signature(timestamp, method, uri, secret_key)
    return {'Content-Type': 'application/json; charset=UTF-8', 
            'X-Timestamp': timestamp, 
            'X-API-KEY': api_key, 
            'X-Customer': str(customer_id), 
            'X-Signature': signature}

def get_keyword_analysis(keyword):
    uri = '/keywordstool'
    method = 'GET'
    params = {
        'hintKeywords': keyword,
        'showDetail': '1'
    }

    # Request API
    response = requests.get(BASE_URL + uri, params=params, headers=get_request_header(method, uri, API_KEY, SECRET_KEY, CUSTOMER_ID))
    
    if response.status_code != 200:
        st.error(f"Error: API request failed with status code {response.status_code}")
        return pd.DataFrame()

    data = response.json()['keywordList']
    df = pd.DataFrame(data)
    
    # Rename columns
    df = df.rename(columns={
        'relKeyword': '연관키워드',
        'monthlyPcQcCnt': '월간검색수_PC',
        'monthlyMobileQcCnt': '월간검색수_모바일',
        'monthlyAvePcClkCnt': '월평균클릭수_PC',
        'monthlyAveMobileClkCnt': '월평균클릭수_모바일',
        'monthlyAvePcCtr': '월평균클릭률_PC',
        'monthlyAveMobileCtr': '월평균클릭률_모바일',
        'compIdx': '경쟁정도'
    })
    
    df['총검색수'] = df['월간검색수_PC'] + df['월간검색수_모바일']
    
    return df

def get_total_docs(keyword):
    time.sleep(0.1)  # Add delay to avoid hitting rate limits
    encText = urllib.parse.quote(keyword)
    url = f"https://openapi.naver.com/v1/search/blog?query={encText}"
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", client_id)
    request.add_header("X-Naver-Client-Secret", client_secret)
    response = urllib.request.urlopen(request)
    rescode = response.getcode()
    if(rescode==200):
        response_body = response.read()
        data = json.loads(response_body.decode('utf-8'))
        return data['total']
    else:
        return 0

def get_trending_keywords():
    url = "https://openapi.naver.com/v1/datalab/search"
    body = {
        "startDate": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        "endDate": datetime.now().strftime("%Y-%m-%d"),
        "timeUnit": "date",
        "keywordGroups": [
            {
                "groupName": "트렌드",
                "keywords": ["트렌드"]
            }
        ]
    }
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", client_id)
    request.add_header("X-Naver-Client-Secret", client_secret)
    request.add_header("Content-Type", "application/json")
    response = urllib.request.urlopen(request, data=json.dumps(body).encode("utf-8"))
    rescode = response.getcode()
    if(rescode==200):
        response_body = response.read()
        data = json.loads(response_body.decode('utf-8'))
        return [item['keyword'] for item in data['results'][0]['data']]
    else:
        return []

def get_informational_keywords(df):
    info_keywords = df[df['연관키워드'].str.contains('방법|어떻게|왜|이유|차이')]
    return info_keywords.sort_values('총검색수', ascending=False).head(10)

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
    response = urllib.request.urlopen(request, data=json.dumps(body).encode("utf-8"))
    rescode = response.getcode()
    if(rescode==200):
        response_body = response.read()
        data = json.loads(response_body.decode('utf-8'))
        return data['results'][0]['data']
    else:
        return None

def plot_keyword_trend(trend_data, keyword):
    dates = [item['period'] for item in trend_data]
    ratios = [item['ratio'] for item in trend_data]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(dates, ratios)
    ax.set_title(f"{keyword} 트렌드")
    ax.set_xlabel("날짜")
    ax.set_ylabel("검색 비율")
    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig

# Streamlit button for running analysis (사이드바)
if st.sidebar.button('분석 실행'):
    keywords_list = [keyword.strip() for keyword in keywords.split(',') if keyword.strip()]
    st.session_state.tmp_df = pd.DataFrame()

    with st.spinner('키워드 분석 중...'):
        for keyword in keywords_list:
            try:
                df = get_keyword_analysis(keyword)
                st.session_state.tmp_df = pd.concat([st.session_state.tmp_df, df], axis=0)
            except Exception as e:
                st.error(f"키워드 '{keyword}' 분석 중 오류 발생: {str(e)}")

    if not st.session_state.tmp_df.empty:
        # '연관키워드' 개수 출력
        st.write(f"연관키워드 개수: {len(st.session_state.tmp_df['연관키워드'])}")

        # Progress bar for document search
        progress_bar = st.progress(0)
        progress_text = st.empty()

        # 병렬 처리로 문서 검색 수행
        with concurrent.futures.ThreadPoolExecutor() as executor:
            total_docs = list(executor.map(get_total_docs, st.session_state.tmp_df['연관키워드']))

        st.session_state.tmp_df['총문서수'] = total_docs
        st.session_state.tmp_df['경쟁정도_ratio'] = st.session_state.tmp_df['총문서수'] / st.session_state.tmp_df['총검색수']

        # Progress 업데이트
        for i, word in enumerate(st.session_state.tmp_df['연관키워드']):
            progress_bar.progress((i + 1) / len(st.session_state.tmp_df['연관키워드']))
            progress_text.text(f"문서 검색 진행 중... ({i + 1}/{len(st.session_state.tmp_df['연관키워드'])})")

        st.session_state.analysis_done = True
    else:
        st.error("분석 결과가 없습니다. 키워드를 확인해 주세요.")

# 분석 결과 표시 (분석이 완료된 경우에만)
if st.session_state.analysis_done:
    # Display final dataframe
    st.write(st.session_state.tmp_df)

    # 경쟁정도가 작고, 모바일 검색이 높은 순으로 정렬
    recommended_df = st.session_state.tmp_df.sort_values(by=['경쟁정도', '월간검색수_모바일'], ascending=[True, False])

    # 추천 목록을 표로 표시
    st.subheader('추천 키워드 (경쟁정도가 낮고 모바일 검색이 높은 순서)')
    st.write(recommended_df[['연관키워드', '경쟁정도', '월간검색수_모바일']].head(10))  # 상위 10개의 추천 키워드

    # 현재 인기 키워드 표시
    st.subheader("현재 인기 키워드")
    trending_keywords = get_trending_keywords()
    st.write(", ".join(trending_keywords))

    # 정보성 키워드 추천
    st.subheader("추천 정보성 키워드")
    info_keywords = get_informational_keywords(st.session_state.tmp_df)
    st.write(info_keywords[['연관키워드', '경쟁정도', '총검색수']])

    # 키워드 트렌드 분석 옵션 (사이드바)
    st.sidebar.subheader("키워드 트렌드 분석")
    selected_keyword = st.sidebar.selectbox("트렌드를 볼 키워드 선택", st.session_state.tmp_df['연관키워드'])
    start_date = st.sidebar.date_input("시작 날짜", value=datetime.now() - timedelta(days=365))
    end_date = st.sidebar.date_input("종료 날짜", value=datetime.now())

    if st.sidebar.button("트렌드 보기"):
        trend_data = get_keyword_trend(selected_keyword, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        
        if trend_data:
            st.subheader(f"{selected_keyword} 트렌드")
            fig = plot_keyword_trend(trend_data, selected_keyword)
            st.pyplot(fig)
        else:
            st.warning("트렌드 데이터를 가져오는데 실패했습니다.")

    # Provide a download link for the resulting dataframe
    csv = st.session_state.tmp_df.to_csv(index=False).encode('utf-8')
    st.download_button("CSV 다운로드", data=csv, file_name='keyword_analysis.csv', mime='text/csv')

else:
    st.info("키워드를 입력하고 '분석 실행' 버튼을 눌러 분석을 시작하세요.")
