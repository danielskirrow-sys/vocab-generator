import streamlit as st
import json
import requests
import io

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="Vocabulary Support Generator", page_icon="📚", layout="wide")

api_key = st.secrets.get("GEMINI_API_KEY", "")

# --- 1. AGE-CALIBRATED TEXT ANALYSIS ---
def extract_vocab(text, target_year, word_count):
    age_map = {
        "Year 7": "ages 11-12",
        "Year 8": "ages 12-13",
        "Year 9": "ages 13-14",
        "Year 10": "ages 14-15",
        "Year 11": "ages 15-16"
    }
    target_age = age_map.get(target_year, "ages 11-16")

    prompt = (
        f"Act as a UK secondary school literacy specialist. Analyze the passage for {target_year} students ({target_age}): '{text}'. "
        f"Extract up to {word_count} target Tier 2 vocabulary words that represent an appropriate challenge, sitting just above the "
        f"independent reading level of a typical {target_year} pupil. "
        f"Write student-friendly definitions and example sentences using tone and vocabulary appropriate for {target_year} ({target_age}). "
        f"For 'word_forms', list alternative word class forms of the target word (e.g., noun, verb, adjective, or adverb variants). "
        f"For 'word_families', identify shared root words, prefixes, or morphologically linked terms (e.g., for 'insatiable', include 'satisfied, satiate, satisfaction'). "
        "Return a JSON array where each object strictly contains keys: word, word_class, definition, sentence, word_forms, word_families."
    )
    
    models = ["gemini-2.5-flash", "gemini-3.5-flash-lite"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}
    }

    last_err = ""
    clean_key = api_key.strip().replace('"', '').replace("'", "")
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={clean_key}"
        headers = {"Content-Type": "application/json"}
        
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=12)
            if res.status_code == 200:
                raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(raw_text)
            else:
                last_err = f"HTTP {res.status_code} ({res.text})"
        except Exception as e:
            last_err = str(e)

    raise Exception(f"API Request Failed: {last_err}")

# --- 2. LANDSCAPE A4 PDF GENERATOR ---
def generate_pdf(vocab_data, inc_def, inc_sentence, inc_forms, inc_families, inc_sketch):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(A4), 
        rightMargin=30, 
        leftMargin=30, 
        topMargin=30, 
        bottomMargin=30
    )
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=16, leading=20, spaceAfter=10)
    cell_style = ParagraphStyle('GridCell', parent=styles['Normal'], fontSize=9, leading=12)
    header_style = ParagraphStyle('GridHeader', parent=styles['Normal'], fontSize=10, leading=12, fontName="Helvetica-Bold")
    blank_style = ParagraphStyle('BlankBox', parent=styles['Normal'], fontSize=9, leading=12)

    elements.append(Paragraph("Learning New Vocabulary", title_style))
    elements.append(Spacer(1, 10))

    headers = [Paragraph("Key Word", header_style)]
    if inc_def: 
        headers.append(Paragraph("Definition", header_style))
    if inc_sentence: 
        headers.append(Paragraph("Example Sentence", header_style))
    if inc_forms:
        headers.append(Paragraph("Word Forms", header_style))
    if inc_families: 
        headers.append(Paragraph("Word Families & Roots", header_style))
    if inc_sketch: 
        headers.append(Paragraph("Dual Coding Space", header_style))

    table_data = [headers]

    for item in vocab_data:
        w_text = item.get('word', '')
        w_cls = item.get('word_class', '')
        row = [Paragraph(f"<b>{w_text}</b><br/><i>({w_cls})</i>", cell_style)]
        
        if inc_def:
            row.append(Paragraph(item.get('definition', 'N/A'), cell_style))
        if inc_sentence:
            row.append(Paragraph(f"<i>{item.get('sentence', 'N/A')}</i>", cell_style))
        if inc_forms:
            f_val = item.get('word_forms', item
