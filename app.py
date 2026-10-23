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

    prompt = (
        f"Act as an expert UK Secondary English teacher. Analyse the provided source text and extract up to {word_count} "
        f"key Tier 2 vocabulary words suitable for {target_year} pupils. Use UK English spelling strictly throughout.\n\n"
        f"Source Text:\n'{passage_text}'\n\n"
        f"Return a JSON array where each object strictly contains these keys: {keys_str}."
    )
    return call_gemini_cascade(prompt)


def replace_single_vocab_word(rejected_word, passage_text, target_year, current_words, inc_def, inc_example, inc_related, inc_etym):
    existing_list = ", ".join([w.get("word", "") for w in current_words if w.get("word")])
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

    prompt = (
        f"Act as an expert UK Secondary English teacher. Generate 1 replacement target vocabulary item from or relevant to this text "
        f"for {target_year} pupils. Replace: '{rejected_word}'. Do NOT generate any of: {existing_list}.\n\n"
        f"Source Text:\n'{passage_text}'\n\n"
        f"Return JSON array with EXACTLY ONE object containing keys: {keys_str}."
    )
    res = call_gemini_cascade(prompt)
    if isinstance(res, list) and len(res) > 0:
        return res[0]
    return None


# --- 3. LANDSCAPE A4 PDF GENERATOR ---
def generate_vocab_pdf(vocab_data, text_title, target_year, inc_def, inc_example, inc_related, inc_etym, inc_dual_coding):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=15, leading=18, spaceAfter=2)
    sub_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.HexColor("#555555"), spaceAfter=10)
    cell_body = ParagraphStyle('CellBody', parent=styles['Normal'], fontSize=8, leading=10)
    draw_label = ParagraphStyle('DrawLabel', parent=styles['Normal'], fontSize=7, leading=8, textColor=colors.HexColor("#777777"))

    doc_label = f"Vocabulary Support Sheet: {text_title}" if text_title else "Vocabulary Support Sheet"
    elements.append(Paragraph(doc_label, title_style))
    elements.append(Paragraph(f"<b>Target Group:</b> {target_year}", sub_style))

    rows = []
    current_row = []
    for item in vocab_data:
        w_name = item.get('word', '')
        w_class = item.get('word_class', '')

        cell_text = f"<b><font size=10 color='#111111'>{w_name}</font></b> <i>({w_class})</i><br/>"
        
        if inc_def and item.get('definition'):
            cell_text += f"<b>Definition:</b> {item.get('definition')}<br/>"
        if inc_example and item.get('example_sentence'):
            cell_text += f"<b>Example:</b> <i>\"{item.get('example_sentence')}\"</i><br/>"
        if inc_related and item.get('related_words'):
            cell_text += f"<b>Related Words:</b> {item.get('related_words')}<br/>"
        if inc_etym and item.get('etymology'):
            cell_text += f"<b>Etymology:</b> {item.get('etymology')}<br/>"

        cell_elements = [Paragraph(cell_text, cell_body)]

        if inc_dual_coding:
            cell_elements.append(Spacer(1, 4))
            draw_box = Table([[Paragraph("<i>Space for dual coding (sketch / icon):</i>", draw_label)]], colWidths=[240], rowHeights=[38])
            draw_box.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fafafa")),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 3)
            ]))
            cell_elements.append(draw_box)

        current_row.append(cell_elements)
        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []

    if current_row:
        while len(current_row) < 3:
            current_row.append([Paragraph("", cell_body)])
        rows.append(current_row)

    t = Table(rows, colWidths=[260, 260, 260])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fdfdfd")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 6)
    ]))
    elements.append(t)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# --- 4. USER INTERFACE ---
st.title("📖 Vocabulary Support Generator")

st.sidebar.header("1. Options")
vocab_year = st.sidebar.selectbox
