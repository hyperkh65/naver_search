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

# 사이드바 설정
st.sidebar.header('분석 옵션')

# st.secrets에서 API 키를 불러옴
CUSTOMER_ID = st.secrets["general"]["CUSTOMER_ID"]
API_KEY = st.secrets["general"]["API_KEY"]
SECRET_KEY = st.secrets["general"]["SECRET_KEY"]
client_id = st.secrets["general"]["client_id"]
client_secret = st.secrets["general"]["client_secret"]

# 키워드 입력 (사이드바로 이동)
keywords = st.sidebar.text_area('분석할 키워드를 입력하세요 (쉼표로 구분)', 'chatgpt').split(',')

BASE_URL = 'https://api.naver.com'

class Signature:
    @staticmethod
    def generate(timestamp, method, uri, secret_key):
        message = "{}.{}.{}".format(timestamp, method, uri)
        hash = hmac.new(bytes(secret_key, "utf-8"), bytes(message, "utf-8"), hashlib.sha256)
        return base64.b64encode(hash.digest())

def get_request_header(method, uri):
    timestamp = str(round(time.time() * 1000))
    signature = Signature.generate(timestamp, method, uri, SECRET_KEY)
    return {
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Timestamp': timestamp,
        'X-API-KEY': API_KEY,
        'X-Customer': str(CUSTOMER_ID),
        'X-Signature': signature
    }

@st.cache_data
def get_keyword_analysis(keyword):
    uri = '/keywordstool'
    method = 'GET'
    r = requests.get(
        BASE_URL + uri,
        params={'hintKeywords': keyword, 'showDetail': 1},
        headers=get_request_header(method, uri)
    )
    df = pd.DataFrame(r.json()['keywordList'])
    df['monthlyMobileQcCnt'] = df['monthlyMobileQcCnt'].apply(lambda x: int(str(x).replace('<', '').strip()))
    df['monthlyPcQcCnt'] = df['monthlyPcQcCnt'].apply(lambda x: int(str(x).replace('<', '').strip()))
    df = df[(df['monthlyMobileQcCnt'] >= 50) & (df['monthlyPcQcCnt'] >= 50)]
    df.rename(
        {'compIdx': '경쟁정도',
        'monthlyMobileQcCnt': '월간검색수_모바일',
        'monthlyPcQcCnt': '월간검색수_PC',
        'relKeyword': '연관키워드'},
        axis=1,
        inplace=True
    )
    df['총검색수'] = df['월간검색수_PC'] + df['월간검색수_모바일']
    df = df.sort_values('총검색수', ascending=False)
    return df

# 문서 수 검색 함수
def get_total_docs(keyword):
    try:
        encText = urllib.parse.quote(keyword)
        url = f"https://openapi.naver.com/v1/search/webkr.json?query={encText}"
        request = urllib.request.Request(url)
        request.add_header("X-Naver-Client-Id", client_id)
        request.add_header("X-Naver-Client-Secret", client_secret)

        # 타임아웃 설정
        with urllib.request.urlopen(request, timeout=10) as response:
            rescode = response.getcode()

            if rescode == 200:
                response_body = response.read()
                text = response_body.decode('utf-8')
                return json.loads(text)['total']
            else:
                st.error(f"Error Code {rescode} for keyword: {keyword}")
                return 0
    except Exception as e:
        st.error(f"Exception: {str(e)} for keyword: {keyword}")
        return 0

# 현재 인기 키워드 가져오기
def get_trending_keywords():
    url = "https://openapi.naver.com/v1/datalab/search"
    
    # 오늘 날짜를 가져옵니다
    today = datetime.now().strftime("%Y-%m-%d")
    
    body = {
        "startDate": today,
        "endDate": today,
        "timeUnit": "date",
        "keywordGroups": [
            {
                "groupName": "트렌드",
                "keywords": [""]
            }
        ]
    }

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=body, headers=headers)
    if response.status_code == 200:
        return response.json()['results'][0]['data'][0]['keywords']
    else:
        return []

# 정보성 키워드 추천
def get_informational_keywords(df):
    informational_words = ["방법", "어떻게", "왜", "의미", "차이", "비교"]
    info_df = df[df['연관키워드'].str.contains('|'.join(informational_words))]
    info_df = info_df.sort_values(by=['경쟁정도', '총검색수'], ascending=[True, False])
    return info_df.head(10)

# 키워드 트렌드 분석
def get_keyword_trend(keyword, start_date, end_date):
    url = "https://openapi.naver.com/v1/datalab/search"
    
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "month",
        "keywordGroups": [
            {
                "groupName": keyword,
                "keywords": [keyword]
            }
        ]
    }

    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=body, headers=headers)
    if response.status_code == 200:
        return response.json()['results'][0]['data']
    else:
        return []

# 키워드 트렌드 분석 (Matplotlib 사용)
def plot_keyword_trend(trend_data, keyword):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot([d['period'] for d in trend_data], [d['ratio'] for d in trend_data], marker='o')
    ax.set_title(f"{keyword} 트렌드")
    ax.set_xlabel("기간")
    ax.set_ylabel("검색 비율")
    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig

# Streamlit button for running analysis (사이드바로 이동)
if st.sidebar.button('분석 실행'):
    tmp_df = pd.DataFrame()

    with st.spinner('키워드 분석 중...'):
        for keyword in keywords:
            keyword = keyword.strip()  # Trim whitespace
            df = get_keyword_analysis(keyword)
            tmp_df = pd.concat([tmp_df, df], axis=0)

    if not tmp_df.empty:
        # '연관키워드' 개수 출력
        st.write(f"연관키워드 개수: {len(tmp_df['연관키워드'])}")

        # Progress bar for document search
        progress_bar = st.progress(0)
        progress_text = st.empty()

        # 병렬 처리로 문서 검색 수행
        with concurrent.futures.ThreadPoolExecutor() as executor:
            total_docs = list(executor.map(get_total_docs, tmp_df['연관키워드']))

        tmp_df['총문서수'] = total_docs
        tmp_df['경쟁정도_ratio'] = tmp_df['총문서수'] / tmp_df['총검색수']

        # Progress 업데이트
        for i, word in enumerate(tmp_df['연관키워드']):
            progress_bar.progress((i + 1) / len(tmp_df['연관키워드']))
            progress_text.text(f"문서 검색 진행 중... ({i + 1}/{len(tmp_df['연관키워드'])})")

        # Display final dataframe
        st.write(tmp_df)

        # 경쟁정도가 작고, 모바일 검색이 높은 순으로 정렬
        recommended_df = tmp_df.sort_values(by=['경쟁정도', '월간검색수_모바일'], ascending=[True, False])

        # 추천 목록을 표로 표시
        st.subheader('추천 키워드 (경쟁정도가 낮고 모바일 검색이 높은 순서)')
        st.write(recommended_df[['연관키워드', '경쟁정도', '월간검색수_모바일']].head(10))  # 상위 10개의 추천 키워드

        # 현재 인기 키워드 표시
        st.subheader("현재 인기 키워드")
        trending_keywords = get_trending_keywords()
        st.write(", ".join(trending_keywords))

        # 정보성 키워드 추천
        st.subheader("추천 정보성 키워드")
        info_keywords = get_informational_keywords(tmp_df)
        st.write(info_keywords[['연관키워드', '경쟁정도', '총검색수']])

        # 키워드 트렌드 분석 옵션 (사이드바로 이동)
        st.sidebar.subheader("키워드 트렌드 분석")
        selected_keyword = st.sidebar.selectbox("트렌드를 볼 키워드 선택", tmp_df['연관키워드'])
        start_date = st.sidebar.date_input("시작 날짜", value=datetime.now() - timedelta(days=365))
        end_date = st.sidebar.date_input("종료 날짜", value=datetime.now())

        if st.sidebar.button("트렌드 보기"):
            trend_data = get_keyword_trend(selected_keyword, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
            
            if trend_data:
                st.subheader(f"{selected_keyword} 트렌드")
                fig = plot_keyword_trend(trend_data, selected_keyword)
                st.pyplot(fig)
            else:
                st.write("트렌드 데이터를 가져오는데 실패했습니다.")

        # Provide a download link for the resulting dataframe
        csv = tmp_df.to_csv(index=False).encode('utf-8')
        st.download_button("CSV 다운로드", data=csv, file_name='keyword_analysis.csv', mime='text/csv')
