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

# 사용자 입력 부분을 Streamlit으로 변경
st.title('Naver Keyword Analysis Tool')

# st.secrets에서 API 키를 불러옴
CUSTOMER_ID = st.secrets["general"]["CUSTOMER_ID"]
API_KEY = st.secrets["general"]["API_KEY"]
SECRET_KEY = st.secrets["general"]["SECRET_KEY"]
client_id = st.secrets["general"]["client_id"]
client_secret = st.secrets["general"]["client_secret"]

# 키워드 입력
keywords = st.text_area('분석할 키워드를 입력하세요 (쉼표로 구분)', 'chatgpt').split(',')

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
    except urllib.error.HTTPError as e:
        st.error(f"HTTPError: {e.code} for keyword: {keyword}")
        return 0
    except urllib.error.URLError as e:
        st.error(f"URLError: {e.reason} for keyword: {keyword}")
        return 0
    except Exception as e:
        st.error(f"Exception: {str(e)} for keyword: {keyword}")
        return 0

# Streamlit button for running analysis
if st.button('분석 실행'):
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

        # Provide a download link for the resulting dataframe
        csv = tmp_df.to_csv(index=False).encode('utf-8')
        st.download_button("CSV 다운로드", data=csv, file_name='keyword_analysis.csv', mime='text/csv')
