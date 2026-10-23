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
        url = "https://generativelanguage.googleapis.com/v1beta/models/" + model + ":generateContent?key=" + clean_key
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
                    last_err = "HTTP " + str(res.status_code) + " (" + res.text + ")"
                    break
            except Exception as e:
                last_err = str(e)
                break

    raise Exception("API Request Failed: " + last_err)


# --- 2. VOCABULARY EXTRACTOR PROMPT ENGINE ---
def extract_vocabulary_support(passage_text, target_year, word_count, inc_def, inc_example, inc_related, inc_etym):
    req_keys = ["word", "word_class"]
    if inc_def:
        req_keys.append("definition")
    if inc_example:
        req_keys.append("example_sentence")
    if inc_related:
        req_keys.append("related_words")
    if inc_etym:
        req_keys.append("etymology")

    keys_str = ", ".join(req_keys)

    prompt = "Act as an expert UK Secondary English teacher. Analyse the provided source text and extract up to " + str(word_count) + " key Tier 2 vocabulary words suitable for " + str(target_year) + " pupils. Use UK English spelling strictly throughout.\n\nSource Text:\n'" + passage_text + "'\n\nReturn a JSON array where each object strictly contains these keys: " + keys_str + "."
    return call_gemini_cascade(prompt)


# --- 3. LANDSCAPE A4 PDF TABLE GENERATOR ---
def generate_vocab_pdf(vocab_data, target_year, inc_def, inc_example, inc_related, inc_etym, inc_dual_coding):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=16, leading=20, spaceAfter=2)
    sub_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.HexColor("#555555"), spaceAfter=10)
    cell_head = ParagraphStyle('CellHead', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.white, fontName="Helvetica-Bold")
    cell_body = ParagraphStyle('CellBody', parent=styles['Normal'], fontSize=8, leading=10)
    draw_label = ParagraphStyle('DrawLabel', parent=styles['Normal'], fontSize=7, leading=8, textColor=colors.HexColor("#888888"))

    elements.append(Paragraph("Vocabulary Support Sheet", title_style))
    elements.append(Paragraph("<b>Target Group:</b> " + str(target_year), sub_style))

    # Build Header Row
    headers = [Paragraph("<b>Word & Class</b>", cell_head)]
    if inc_def:
        headers.append(Paragraph("<b>Definition</b>", cell_head))
    if inc_example:
        headers.append(Paragraph("<b>Example Sentence</b>", cell_head))
    if inc_related:
        headers.append(Paragraph("<b>Related Words</b>", cell_head))
    if inc_etym:
        headers.append(Paragraph("<b>Etymology</b>", cell_head))
    if inc_dual_coding:
        headers.append(Paragraph("<b>Dual Coding</b>", cell_head))

    table_data = [headers]

    # Build Data Rows
    for item in vocab_data:
        w_name = str(item.get('word', ''))
        w_class = str(item.get('word_class', ''))
        w_html = "<b><font size=9>" + w_name + "</font></b><br/><i>(" + w_class + ")</i>"
        row = [Paragraph(w_html, cell_body)]

        if inc_def:
            row.append(Paragraph(str(item.get('definition', '')), cell_body))
        if inc_example:
            ex_txt = "<i>\"" + str(item.get('example_sentence', '')) + "\"</i>"
