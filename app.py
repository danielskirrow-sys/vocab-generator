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
def extract_vocabulary_support(passage_text, target_year, word_count, inc_def, inc_example, inc_related, inc_etym):
    fields = []
    if inc_def:
        fields.append("'definition' (short pupil-friendly meaning)")
    if inc_example:
        fields.append("'example_sentence' (contextual sentence illustrating usage)")
    if inc_related:
        fields.append("'related_words' (synonyms or word family forms)")
    if inc_etym:
        fields.append("'etymology' (root word origin or prefix/suffix breakdown)")

    fields_req = ", ".join(fields)
    
    prompt = (
        f"Act as an expert UK Secondary English teacher. Analyse the provided text and extract up to {word_count} "
        f"key Tier 2 vocabulary words suitable for {target_year} pupils. Use UK English spelling strictly throughout.\n\n"
        f"Source Text:\n'{passage_text}'\n\n"
        f"For each word extracted, provide: 'word', 'word_class', plus the following requested fields: {fields_req}.\n"
        f"Return a JSON array where each object strictly contains keys: word, word_class"
    )
    
    if inc_def:
        prompt += ", definition"
    if inc_example:
        prompt += ", example_sentence"
    if inc_related:
        prompt += ", related_words"
    if inc_etym:
        prompt += ", etymology"

    return call_gemini_cascade(prompt)


def replace_single_vocab_word(rejected_word, passage_text, target_year, current_words, inc_def, inc_example, inc_related, inc_etym):
    existing_list = ", ".join([w.get('word', '') for w in current_words if w.get('word')])
    
    prompt = (
        f"Act as an expert UK Secondary English teacher. Generate 1 replacement target vocabulary item from or relevant to this text "
        f"for {target_year} pupils. Replace: '{rejected_word}'. Do NOT generate any of: {existing_list}.\n"
        f"Context: '{passage_text}'\n"
        f"Return JSON array with EXACTLY ONE object containing keys: word, word_class"
    )
    if inc_def:
        prompt += ", definition"
    if inc_example:
        prompt += ", example_sentence"
    if inc_related:
        prompt +=
