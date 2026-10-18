import streamlit as st
import json
import requests
import io
import time

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="Adaptation Station", page_icon="📚", layout="wide")

api_key = st.secrets.get("GEMINI_API_KEY", "")

# Initialize active tool state
if "active_tool" not in st.session_state:
    st.session_state.active_tool = None


# --- 1. SHARED API CASCADE ENGINE ---
def call_gemini_cascade(prompt):
    models = ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-1.5-flash"]
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


# --- 2. VOCABULARY GENERATOR LOGIC ---
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
        f"Extract up to {word_count} target Tier 2 vocabulary words that represent an appropriate challenge. "
        f"Use UK English spelling strictly throughout (e.g., analyse, characterise, emphasise).\n\n"
        f"Write student-friendly definitions and example sentences using tone and vocabulary appropriate for {target_year} ({target_age}). "
        f"For 'word_forms', list alternative word class forms of the target word. "
        f"For 'word_families', identify shared root words, prefixes, or morphologically linked terms. "
        "Return a JSON array where each object strictly contains keys: word, word_class, definition, sentence, word_forms, word_families."
    )
    return call_gemini_cascade(prompt)


def generate_vocab_pdf(vocab_data, inc_def, inc_sentence, inc_forms, inc_families, inc_sketch):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=16, leading=20, spaceAfter=10)
    cell_style = ParagraphStyle('GridCell', parent=styles['Normal'], fontSize=9, leading=12)
    header_style = ParagraphStyle('GridHeader', parent=styles['Normal'], fontSize=10, leading=12, fontName="Helvetica-Bold")
    blank_style = ParagraphStyle('BlankBox', parent=styles['Normal'], fontSize=9, leading=12)

    elements.append(Paragraph("Learning New Vocabulary", title_style))
    elements.append(Spacer(1, 10))

    headers = [Paragraph("Key Word", header_style)]
    if inc_def: headers.append(Paragraph("Definition", header_style))
    if inc_sentence: headers.append(Paragraph("Example Sentence", header_style))
    if inc_forms: headers.append(Paragraph("Word Forms", header_style))
    if inc_families: headers.append(Paragraph("Word Families & Roots", header_style))
    if inc_sketch: headers.append(Paragraph("Dual Coding Space", header_style))

    table_data = [headers]

    for item in vocab_data:
        w_text = item.get('word', '')
        w_cls = item.get('word_class', '')
        row = [Paragraph(f"<b>{w_text}</b><br/><i>({w_cls})</i>", cell_style)]
        
        if inc_def: row.append(Paragraph(item.get('definition', 'N/A'), cell_style))
        if inc_sentence: row.append(Paragraph(f"<i>{item.get('sentence', 'N/A')}</i>", cell_style))
        if inc_forms:
            f_val = item.get('word_forms', [])
            row.append(Paragraph(", ".join(f_val) if isinstance(f_val, list) else str(f_val), cell_style))
        if inc_families:
            r_val = item.get('word_families', [])
            row.append(Paragraph(", ".join(r_val) if isinstance(r_val, list) else str(r_val), cell_style))
        if inc_sketch: row.append(Paragraph("<br/><br/><br/>", blank_style))
                
        table_data.append(row)

    num_cols = len(headers)
    col_width = 780 / num_cols

    t = Table(table_data, colWidths=[col_width] * num_cols)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer


# --- 3. WORD BANK GENERATOR LOGIC ---
def extract_word_bank(task_type, prompt_text, target_year, target_band, word_count):
    if task_type == "Literary Analysis / GCSE Essay":
        category_guidance = (
            "Organise the output strictly into 4 literature categories: "
            "1. 'Conceptual Nouns' (abstract thematic ideas directly tailored to this prompt/text), "
            "2. 'Analytical Verbs' (e.g. subverts, epitomises, forebodes), "
            "3. 'Tone Descriptors' (e.g. didactic, volatile, sombre), "
            "4. 'Discourse Markers' (e.g. fundamentally, conversely, ultimately)."
        )
    elif task_type in ["Creative / Descriptive Writing", "Narrative Writing"]:
        category_guidance = (
            "Organise the output strictly into 4 descriptive categories: "
            "1. 'Sensory Details', 2. 'Atmospheric Adjectives', "
            "3. 'Dynamic Verbs', 4. 'Figurative Openers'."
        )
    else:
        category_guidance = (
            "Organise the output strictly into 4 persuasive categories: "
            "1. 'Rhetorical Connectives', 2. 'Emotive Nouns', "
            "3. 'Persuasive Adverbs', 4. 'Counter-argument Markers'."
        )

    prompt = (
        f"Act as an expert UK Secondary English teacher. Generate a writing word bank for {target_year} pupils "
        f"working at {target_band}. Use UK English spelling strictly throughout (e.g., analyse, characterise, emphasise).\n\n"
        f"Task Type: {task_type}\n"
        f"Task Prompt/Context: '{prompt_text}'\n\n"
        f"{category_guidance}\n\n"
        f"Extract/generate exactly {word_count} target vocabulary words or academic phrases appropriate for this writing task. "
        f"For each item, include: word, word_class, category, definition, and a short model_phrase illustrating its use in an English writing context.\n"
        "Return a JSON array where each object strictly contains keys: word, word_class, category, definition, model_phrase."
    )
    return call_gemini_cascade(prompt)


def generate_word_bank_pdf(wb_data, task_type, target_band):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=16, leading=20, spaceAfter=4)
    sub_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontSize=10, leading=12, textColor=colors.HexColor("#555555"), spaceAfter=10)
    cell_body = ParagraphStyle('CellBody', parent=styles['Normal'], fontSize=8.5, leading=11)

    elements.append(Paragraph("English Writing Word Bank", title_style))
    elements.append(Paragraph(f"<b>Focus:</b> {task_type} &nbsp;|&nbsp; <b>Level:</b> {target_band}", sub_style))

    rows = []
    current_row = []
    for item in wb_data:
        cell_text = (
            f"<b><font size=7 color='#005b96'>{item.get('category', '').upper()}</font></b><br/>"
            f"<b><font size=11 color='#111111'>{item.get('word', '')}</font></b> <i>({item.get('word_class', '')})</i><br/><br/>"
            f"<b>Meaning:</b> {item.get('definition', '')}<br/>"
            f"<b>Usage:</b> <i>\"{item.get('model_phrase', '')}\"</i>"
        )
        current_row.append(Paragraph(cell_text, cell_body))
        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []
            
    if current_row:
        while len(current_row) < 3:
            current_row.append(Paragraph("", cell_body))
        rows.append(current_row)

    t = Table(rows, colWidths=[260, 260, 260])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fdfdfd")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 8)
    ]))
    
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer


# --- 4. LANDING PAGE & ROUTING ---
if st.session_state.active_tool is None:
    st.write("<br/><br/>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    
    with c1:
        with st.container(border=True):
            st.markdown("### 📖 Vocabulary Support Generator")
            st.write("Extract key Tier 2 reading vocabulary from any text passage. Generates structured definition tables and dual-coding grids.")
            st.write("")
            if st.button("Launch Vocabulary Tool", type="primary", use_container_width=True, key="btn_launch_vocab"):
                st.session_state.active_tool = "vocab"
                st.
