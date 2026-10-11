import streamlit as st
import json
import requests
import io
import urllib.parse

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="Vocabulary Support Generator", page_icon="📚", layout="wide")

api_key = st.secrets.get("GEMINI_API_KEY", "")

# --- 1. CACHED TEXT ANALYSIS WITH ICON CONCEPT MAPPING ---
@st.cache_data(show_spinner=False)
def extract_vocab_cached(text, target_year, word_count):
    prompt = f"""
    Analyze the text for {target_year} UK secondary students. Extract up to {word_count} Tier 2 words for explicit instruction.
    Use British English spelling. Passage: '{text}'.
    
    Return a JSON array with fields:
    - word
    - word_class
    - definition
    - sentence
    - related_words
    - icon_name: A single simple lower-case Google Material Symbol name representing the word visually (e.g. 'gavel', 'search', 'bolt', 'balance', 'menu-book', 'visibility', 'shield', 'flag').
    """
    
    models = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}
    }

    last_err = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=8)
            if res.status_code == 200:
                raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(raw_text)
            elif res.status_code == 429:
                last_err = f"429 Quota limit on {model}"
            else:
                last_err = f"HTTP {res.status_code} on {model}"
        except Exception as e:
            last_err = str(e)

    raise Exception(f"API Failed: {last_err}")

# --- 2. FAST UNWATERMARKED SVG ICON FETCHING ---
@st.cache_data(show_spinner=False)
def get_icon_image_bytes(icon_name):
    clean_icon = icon_name.lower().strip().replace(" ", "-")
    url = f"https://api.iconify.design/material-symbols:{clean_icon}.svg?color=%23333333&width=64&height=64"
    try:
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            return res.content, url
    except Exception:
        pass
    
    # Fallback to standard book icon if icon name isn't found
    fallback_url = "https://api.iconify.design/material-symbols:menu-book.svg?color=%23333333&width=64&height=64"
    res = requests.get(fallback_url, timeout=3)
    return res.content, fallback_url

# --- 3. LANDSCAPE A4 PDF GENERATOR ---
def generate_pdf(vocab_data, inc_def, inc_sentence, inc_related, inc_icon):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=16, leading=20, spaceAfter=10)
    cell_style = ParagraphStyle('GridCell', parent=styles['Normal'], fontSize=9, leading=12)
    header_style = ParagraphStyle('GridHeader', parent=styles['Normal'], fontSize=10, leading=12, fontName="Helvetica-Bold")

    elements.append(Paragraph("Learning New Vocabulary", title_style))
    elements.append(Spacer(1, 10))

    headers = [Paragraph("Key Word", header_style)]
    if inc_def: headers.append(Paragraph("Definition", header_style))
    if inc_sentence: headers.append(Paragraph("Example Sentence", header_style))
    if inc_related: headers.append(Paragraph("Related Words", header_style))
    if inc_icon: headers.append(Paragraph("Visual Anchor", header_style))

    table_data = [headers]

    for item in vocab_data:
        word = item.get('word', '')
        row = [Paragraph(f"<b>{word}</b><br/><i>({item.get('word_class', '')})</i>", cell_style)]
        if inc_def:
            row.append(Paragraph(item.get('definition', 'N/A'), cell_style))
        if inc_sentence:
            row.append(Paragraph(f"<i>{item.get('sentence', 'N/A')}</i>", cell_style))
        if inc_related:
            rel_list = item.get('related_words', [])
            rel_str = ", ".join(rel_list) if isinstance(rel_list, list) else str(rel_list)
            row.append(Paragraph(rel_str, cell_style))
        if inc_icon:
            icon_name = item.get('icon_name', 'menu-book')
            _, icon_url = get_icon_image_bytes(icon_name)
            # Embedding vector graphic via URL
            row.append(Paragraph(f'<img src="{icon_url}" width="32" height="32"/>', cell_style))
                
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

# --- 4. MAIN INTERFACE ---
st.title("📚 Vocabulary Support Generator")

st.sidebar.header("1. Target Options")
word_count = st.sidebar.slider("Number of words to extract", min_value=1, max_value=8, value=5)
target_year = st.sidebar.selectbox("Year", ["Year 7", "Year 8", "Year 9", "Year 10", "Year 11"])

st.sidebar.header("2. Active Table Columns")
inc_def = st.sidebar.checkbox("Definition", value=True)
inc_sentence = st.sidebar.checkbox("Example Sentence", value=True)
inc_related = st.sidebar.checkbox("Related Words", value=True)
inc_icon = st.sidebar.checkbox("Dual Coding Visual Icon", value=True)

user_text = st.text_area("Paste Text Below", height=200)

if st.button("Generate Resource Grid", type="primary"):
    if not user_text.strip():
        st.warning("Please paste a text passage before generating.")
    else:
        try:
            vocab_data = extract_vocab_cached(user_text, target_year, word_count)
            pdf_buffer = generate_pdf(vocab_data, inc_def, inc_sentence, inc_related, inc_icon)

            st.markdown("---")
            col_title, col_btn = st.columns([3, 1])
            with col_title:
                st.subheader("Learning New Vocabulary")
            with col_btn:
                st.download_button(
                    label="📥 Download Printable PDF",
                    data=pdf_buffer,
                    file_name="Vocabulary_Worksheet.pdf",
                    mime="application/pdf",
                    type="primary"
                )

            for item in vocab_data:
                word = item.get('word')
                icon_name = item.get('icon_name', 'menu-book')
                _, icon_url = get_icon_image_bytes(icon_name)

                active_cols = [("Key Word", True)]
                if inc_def: active_cols.append(("Definition", True))
                if inc_sentence: active_cols.append(("Example Sentence", True))
                if inc_related: active_cols.append(("Related Words", True))
                if inc_icon: active_cols.append(("Visual Icon", True))
                
                grid = st.columns(len(active_cols))
                c_idx = 0

                with grid[c_idx]:
                    st.markdown(f"**Key Word**\n\n### {word}\n*({item.get('word_class')})*")
                c_idx += 1

                if inc_def:
                    with grid[c_idx]:
                        st.markdown(f"**Definition**\n\n{item.get('definition', 'N/A')}")
                    c_idx += 1

                if inc_sentence:
                    with grid[c_idx]:
                        st.markdown(f"**Example Sentence**\n\n*{item.get('sentence', 'N/A')}*")
                    c_idx += 1

                if inc_related:
                    with grid[c_idx]:
                        rel_list = item.get('related_words', [])
                        rel_str = ", ".join(rel_list) if isinstance(rel_list, list) else rel_list
                        st.markdown(f"**Related Words**\n\n{rel_str}")
                    c_idx += 1

                if inc_icon:
                    with grid[c_idx]:
                        st.markdown("**Visual Anchor**")
                        st.image(icon_url, width=48)
                    c_idx += 1

                st.divider()

        except Exception as e:
            st.error(f"Error generating resource: {e}")
