import streamlit as st
import os
import time
import urllib.request
import json
import pandas as pd
import requests
import datetime
import hashlib
import hmac
import base64

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

# Streamlit button for running analysis
if st.button('분석 실행'):
    tmp_df = pd.DataFrame()

    with st.spinner('키워드 분석 중...'):
        for keyword in keywords:
            keyword = keyword.strip()  # Trim whitespace
            uri = '/keywordstool'
            method = 'GET'
            try:
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
                tmp_df = pd.concat([tmp_df, df], axis=0)
                time.sleep(1)
            except Exception as e:
                st.error(f"에러 발생: {e}")
                continue

    total_docs = []

    if not tmp_df.empty:
        # '연관키워드' 개수 출력
        st.write(f"연관키워드 개수: {len(tmp_df['연관키워드'])}")

        # Progress bar for document search
        progress_bar = st.progress(0)
        progress_text = st.empty()

        for idx, word in enumerate(tmp_df['연관키워드']):
            encText = urllib.parse.quote(word)
            url = f"https://openapi.naver.com/v1/search/webkr.json?query={encText}"
            request = urllib.request.Request(url)
            request.add_header("X-Naver-Client-Id", client_id)
            request.add_header("X-Naver-Client-Secret", client_secret)
            response = urllib.request.urlopen(request)
            rescode = response.getcode()

            try:
                if rescode == 200:
                    response_body = response.read()
                    text = response_body.decode('utf-8')
                    total_docs.append(json.loads(text)['total'])
                else:
                    st.warning(f"Error Code: {rescode}")
                    total_docs.append(0)
            except:
                total_docs.append(0)

            # Update progress
            progress_bar.progress((idx + 1) / len(tmp_df['연관키워드']))
            progress_text.text(f"문서 검색 진행 중... ({idx + 1}/{len(tmp_df['연관키워드'])})")
            time.sleep(0.5)

        tmp_df['총문서수'] = total_docs
        tmp_df['경쟁정도_ratio'] = tmp_df['총문서수'] / tmp_df['총검색수']

        # Display final dataframe
        st.write(tmp_df)

        # Provide a download link for the resulting dataframe
        csv = tmp_df.to_csv(index=False).encode('utf-8')
        st.download_button("CSV 다운로드", data=csv, file_name='keyword_analysis.csv', mime='text/csv')
