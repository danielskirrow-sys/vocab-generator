import streamlit as st
import json
import io
from google import genai
from google.genai import types

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="Vocabulary Support Generator", page_icon="📚", layout="wide")

api_key = st.secrets.get("GEMINI_API_KEY", "")

# --- 1. AGE-CALIBRATED CACHED TEXT ANALYSIS ---
@st.cache_data(show_spinner=False)
def extract_vocab_cached(text, target_year, word_count):
    # Age range mapping for explicit UK secondary calibration
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
        "Return a JSON array where each object strictly contains keys: word, word_class, definition, sentence, related_words."
    )
    
    # Initialize the Google GenAI Client with the key
    client = genai.Client(api_key=api_key.strip())
    
    try:
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        raise Exception(f"API Failed: {str(e)}")

# --- 2. LANDSCAPE A4 PDF GENERATOR ---
def generate_pdf(vocab_data, inc_def, inc_sentence, inc_related, inc_sketch):
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
    if inc_related: 
        headers.append(Paragraph("Related Words", header_style))
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
        if inc_related:
            r_val = item.get('related_words', [])
            r_str = ", ".join(r_val) if isinstance(r_val, list) else str(r_val)
            row.append(Paragraph(r_str, cell_style))
        if inc_sketch:
            # Completely blank cell for student sketching
            row.append(Paragraph("<br/><br/><br/>", blank_style))
                
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

# --- 3. MAIN INTERFACE ---
st.title("📚 Vocabulary Support Generator")

st.sidebar.header("1. Target Options")
word_count = st.sidebar.slider("Number of words to extract", min_value=1, max_value=8, value=5)
target_year = st.sidebar.selectbox
