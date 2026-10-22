import streamlit as st
import json
import requests
import io
import time

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="Vocabulary Support Generator", page_icon="📖", layout="wide")

api_key = st.secrets.get("GEMINI_API_KEY", "")

# Session State Initialization
if "vocab_data" not in st.session_state:
    st.session_state.vocab_data = None
if "text_title" not in st.session_state:
    st.session_state.text_title = ""
if "target_band" not in st.session_state:
    st.session_state.target_band = ""


# --- 1. API CASCADE ENGINE ---
def call_gemini_cascade(prompt):
    models = ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}
    }
    clean_key = api_key.strip().replace('"', '').replace("'", "")
    last_err = ""

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={clean_key}"
        headers = {"Content-Type": "application/json"}
        
        for attempt in range(2):
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=12)
                if res.status_code == 200:
                    raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(raw_text)
                elif res.status_code == 503 and attempt == 0:
                    time.sleep(1)
                    continue
                else:
                    last_err = f"HTTP {res.status_code} ({res.text})"
                    break
            except Exception as e:
                last_err = str(e)
                break

    raise Exception(f"API Request Failed: {last_err}")


# --- 2. VOCABULARY EXTRACTOR PROMPT ENGINE ---
def extract_vocabulary_support(passage_text, mandatory_words, target_year, target_band, word_count):
    # Flightpath adjustment matrix mapping Year Group + Band to realistic pitch
    flightpath_map = {
        ("Year 7", "Developing (Grades 1-3)"): "Entry / Access Level (KS2 to KS3 bridge, highly grounded and clear vocabulary)",
        ("Year 7", "Reaching (Grades 4-6)"): "Year 7 Secure / Working towards GCSE Grade 2-3 (Accessible Tier 2 academic words, no overly complex Latinate terms)",
        ("Year 7", "Mastering (Grades 7-9)"): "Year 7 High Attainer / Working towards GCSE Grade 4-5 (Ambitious yet clean, practical vocabulary)",
        
        ("Year 8", "Developing (Grades 1-3)"): "Year 8 Foundation / GCSE Grade 1-2 equivalent",
        ("Year 8", "Reaching (Grades 4-6)"): "Year 8 Secure / GCSE Grade 3-4 equivalent (Grounded academic Tier 2 words)",
        ("Year 8", "Mastering (Grades 7-9)"): "Year 8 High Attainer / GCSE Grade 5-6 equivalent",
        
        ("Year 9", "Developing (Grades 1-3)"): "Year 9 Foundation / GCSE Grade 2-3 equivalent",
        ("Year 9", "Reaching (Grades 4-6)"): "Year 9 Secure / GCSE Grade 4-5 equivalent",
        ("Year 9", "Mastering (Grades 7-9)"): "Year 9 High Attainer / GCSE Grade 6-7 equivalent",

        ("Year 10", "Developing (Grades 1-3)"): "GCSE Grades 1-3 Foundation",
        ("Year 10", "Reaching (Grades 4-6)"): "GCSE Grades 4-6 Intermediate",
        ("Year 10", "Mastering (Grades 7-9)"): "GCSE Grades 7-9 Higher Mastery",

        ("Year 11", "Developing (Grades 1-3)"): "GCSE Grades 1-3 Foundation",
        ("Year 11", "Reaching (Grades 4-6)"): "GCSE Grades 4-6 Intermediate",
        ("Year 11", "Mastering (Grades 7-9)"): "GCSE Grades 7-9 Higher Mastery"
    }

    calibrated_level = flightpath_map.get((target_year, target_band), f"{target_year} {target_band}")

    mandatory_instruction = ""
    if mandatory_words.strip():
        mandatory_instruction = (
            f"\n\nMANDATORY REQUIREMENT: You MUST extract and include the following teacher-specified words/phrases "
            f"if they appear in or relate to the text: '{mandatory_words}'."
        )

    prompt = (
        f"Act as an expert UK Secondary English teacher. Analyse the following text and extract target vocabulary for {target_year} pupils "
        f"calibrated strictly to this secondary flightpath standard: '{calibrated_level}'. Use UK English spelling strictly throughout (e.g., analyse, characterise, emphasise).\n\n"
        f"STRICT PEDAGOGICAL GUIDELINES:\n"
        f"- Focus on high-utility Tier 2 vocabulary that pupils need to comprehend this text or discuss it academically.\n"
        f"- Do NOT select obscure, archaic, or unnecessarily pretension terms unless central to text comprehension.\n"
        f"- Ensure definitions are concise, pupil-friendly, and
