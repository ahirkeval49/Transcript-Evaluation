# transcript_evaluator.py
import streamlit as st
import pdfplumber
import pytesseract
from docx import Document
from PIL import Image
import pandas as pd
import io
import re
import requests
from bs4 import BeautifulSoup
import json
from time import sleep
import random
from functools import lru_cache

# --------------------------
# Configuration
# --------------------------
pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'  # Update for your OS
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
COUNTRIES = ["India", "Pakistan", "Saudi Arabia", "Germany", "Nigeria", "Bangladesh"]

# --------------------------
# Document Processing
# --------------------------
def extract_text(uploaded_file, country):
    try:
        if uploaded_file.type == "application/pdf":
            with pdfplumber.open(uploaded_file) as pdf:
                return " ".join([page.extract_text() for page in pdf.pages])
        elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            doc = Document(uploaded_file)
            return " ".join([para.text for para in doc.paragraphs])
        elif uploaded_file.type.startswith('image'):
            img = Image.open(io.BytesIO(uploaded_file.read()))
            lang = 'ara' if country == "Saudi Arabia" else 'eng'
            return pytesseract.image_to_string(img, lang=lang)
        return None
    except Exception as e:
        st.error(f"Document processing error: {str(e)}")
        return None

# --------------------------
# DeepSeek-R1 Integration
# --------------------------
def analyze_with_deepseek(text, country):
    headers = {
        "Authorization": f"Bearer {st.secrets['DEEPSEEK_API_KEY']}",
        "Content-Type": "application/json"
    }
    
    system_prompt = """Extract from transcript as JSON:
{
  "institution_name": "Official name",
  "original_gpa": number,
  "gpa_scale": "Original scale",
  "degree_name": "Degree title",
  "courses": [{"code": str, "name": str, "credits": number, "grade": str}],
  "us_degree_equivalent": "US equivalent"
}
Country: {country}"""
    
    payload = {
        "model": "deepseek-reasoner",
        "messages": [
            {"role": "system", "content": system_prompt.format(country=country)},
            {"role": "user", "content": text[:15000]}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return json.loads(response.json()['choices'][0]['message']['content'])
    except Exception as e:
        st.error(f"DeepSeek API Error: {str(e)}")
        return None

# --------------------------
# GPA Conversion
# --------------------------
def convert_gpa(original_gpa, country):
    conversion_rules = {
        "India": lambda x: (x / 10) * 4,
        "Pakistan": lambda x: (x / 100) * 4,
        "Saudi Arabia": lambda x: (x / 5) * 4,
        "Germany": lambda x: 4 - ((x - 1) * 1),
        "Nigeria": lambda x: (x / 5) * 4,
        "Bangladesh": lambda x: (x / 4) * 4
    }
    return min(4.0, conversion_rules.get(country, lambda x: x)(original_gpa))

# --------------------------
# Accreditation Checker
# --------------------------
@lru_cache(maxsize=1000)
def check_accreditation(institution: str, country: str) -> bool:
    try:
        sleep(random.uniform(1, 3))  # Rate limiting
        if country == "India":
            return check_ugc_india(institution)
        elif country == "Pakistan":
            return check_hec_pakistan(institution)
        elif country == "Saudi Arabia":
            return check_moe_saudi(institution)
        elif country == "Germany":
            return check_anabin_germany(institution)
        elif country == "Nigeria":
            return check_nuc_nigeria(institution)
        elif country == "Bangladesh":
            return check_ugc_bangladesh(institution)
        return False
    except Exception as e:
        st.error(f"Accreditation check failed: {str(e)}")
        return False

def check_ugc_india(institution: str) -> bool:
    session = requests.Session()
    response = session.get("https://www.ugc.ac.in/recog_College.aspx")
    soup = BeautifulSoup(response.text, 'html.parser')
    viewstate = soup.find('input', {'id': '__VIEWSTATE'})['value']
    eventval = soup.find('input', {'id': '__EVENTVALIDATION'})['value']

    data = {
        '__VIEWSTATE': viewstate,
        '__EVENTVALIDATION': eventval,
        'ctl00$ContentPlaceHolder1$txtCollegeName': institution,
        'ctl00$ContentPlaceHolder1$btnSearch': 'Search'
    }

    response = session.post("https://www.ugc.ac.in/recog_College.aspx", data=data)
    return "No College Found" not in response.text

def check_hec_pakistan(institution: str) -> bool:
    response = requests.get("https://www.hec.gov.pk/english/universities/Pages/Recognized-Universities.aspx")
    soup = BeautifulSoup(response.text, 'html.parser')
    return any(re.search(institution, div.text, re.I) for div in soup.select('div.university-name'))

def check_moe_saudi(institution: str) -> bool:
    response = requests.get("https://www.moe.gov.sa/en/education/highereducation/Pages/Government-Universities.aspx")
    return institution.lower() in response.text.lower()

def check_anabin_germany(institution: str) -> bool:
    response = requests.get(f"https://anabin.kmk.org/no_cache/filter/institutionen.html?search=1&name={institution}")
    return "Keine Treffer gefunden" not in response.text

def check_nuc_nigeria(institution: str) -> bool:
    response = requests.get("https://www.nuc.edu.ng/nigerian-universities/")
    return institution.lower() in response.text.lower()

def check_ugc_bangladesh(institution: str) -> bool:
    response = requests.get("http://www.ugc.gov.bd/en/home/privateuniversity/2")
    soup = BeautifulSoup(response.text, 'html.parser')
    return any(institution.lower() in li.text.lower() for li in soup.select('div.content-body li'))

# --------------------------
# Streamlit Interface
# --------------------------
def main():
    st.set_page_config(page_title="Transcript Evaluator Pro", layout="wide")
    st.title("🎓 University of Hartford Transcript Evaluation")
    
    with st.sidebar:
        st.header("Applicant Details")
        name = st.text_input("Full Name")
        country = st.selectbox("Country of Education", COUNTRIES)
        uploaded_file = st.file_uploader("Upload Transcript", 
                                       type=["pdf", "docx", "png", "jpg", "jpeg"])
    
    if uploaded_file and name:
        with st.spinner("Analyzing transcript..."):
            raw_text = extract_text(uploaded_file, country)
            
            if raw_text:
                analysis = analyze_with_deepseek(raw_text, country)
                
                if analysis:
                    us_gpa = convert_gpa(float(analysis["original_gpa"]), country)
                    accredited = check_accreditation(analysis["institution_name"], country)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("Academic Summary")
                        st.metric("Institution", analysis["institution_name"])
                        st.metric("Original GPA", f"{analysis['original_gpa']} ({analysis['gpa_scale']} scale)")
                        st.metric("US Equivalent GPA", f"{us_gpa:.2f}/4.0")
                        
                    with col2:
                        st.subheader("Verification")
                        status = "✅ Recognized" if accredited else "❌ Not Recognized"
                        st.metric("Accreditation Status", status)
                        st.metric("Degree Equivalent", analysis["us_degree_equivalent"])
                        st.metric("Courses Analyzed", len(analysis["courses"]))
                    
                    st.subheader("Course Details")
                    courses_df = pd.DataFrame(analysis["courses"])
                    st.dataframe(
                        courses_df.style.format({"credits": "{:.0f}"}),
                        use_container_width=True,
                        hide_index=True
                    )

if __name__ == "__main__":
    main()
