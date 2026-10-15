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
            f_val = item.get('word_forms', [])
            f_str = ", ".join(f_val) if isinstance(f_val, list) else str(f_val)
            row.append(Paragraph(f_str, cell_style))
        if inc_families:
            r_val = item.get('word_families', [])
            r_str = ", ".join(r_val) if isinstance(r_val, list) else str(r_val)
            row.append(Paragraph(r_str, cell_style))
        if inc_sketch:
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

# --- 3. MAIN UI LAYOUT ---
st.title("📚 Vocabulary Support Generator")

st.sidebar.header("1. Target Options")
word_count = st.sidebar.slider("Number of words to extract", min_value=1, max_value=8, value=5)
target_year = st.sidebar.selectbox("Year", ["Year 7", "Year 8", "Year 9", "Year 10", "Year 11"])

st.sidebar.header("2. Active Table Columns")
inc_def = st.sidebar.checkbox("Definition", value=True)
inc_sentence = st.sidebar.checkbox("Example Sentence", value=True)
inc_forms = st.sidebar.checkbox("Word Forms", value=True)
inc_families = st.sidebar.checkbox("Word Families & Roots", value=True)
inc_sketch = st.sidebar.checkbox("Space for Dual Coding", value=True)

user_text = st.text_area("Paste Text Below", height=200)
generate_clicked = st.button("Generate Resource Grid", type="primary")

if generate_clicked:
    if not user_text.strip():
        st.warning("Please paste a text passage before generating.")
    elif not api_key:
        st.error("Missing GEMINI_API_KEY in Streamlit Secrets.")
    else:
        try:
            vocab_data = extract_vocab(user_text, target_year, word_count)
            pdf_buffer = generate_pdf(vocab_data, inc_def, inc_sentence, inc_forms, inc_families, inc_sketch)

            st.markdown("---")
            col_title, col_btn = st.columns([3, 1])
            col_title.subheader("Learning New Vocabulary")
            col_btn.download_button(
                label="📥 Download Printable PDF",
                data=pdf_buffer,
                file_name="Vocabulary_Worksheet.pdf",
                mime="application/pdf",
                type="primary"
            )

            for item in vocab_data:
                cols_count = 1
                if inc_def: cols_count += 1
                if inc_sentence: cols_count += 1
                if inc_forms: cols_count += 1
                if inc_families: cols_count += 1
                if inc_sketch: cols_count += 1

                grid = st.columns(cols_count)
                c_idx = 0

                grid[c_idx].markdown(f"**Key Word**\n\n### {item.get('word', '')}\n*({item.get('word_class', '')})*")
                c_idx += 1

                if inc_def:
                    grid[c_idx].markdown(f"**Definition**\n\n{item.get('definition', 'N/A')}")
                    c_idx += 1

                if inc_sentence:
                    grid[c_idx].markdown(f"**Example Sentence**\n\n*{item.get('sentence', 'N/A')}*")
                    c_idx += 1

                if inc_forms:
                    f_val = item.get('word_forms', [])
                    f_out = ", ".join(f_val) if isinstance(f_val, list) else str(f_val)
                    grid[c_idx].markdown(f"**Word Forms**\n\n{f_out}")
                    c_idx += 1

                if inc_families:
                    fam_val = item.get('word_families', [])
                    fam_out = ", ".join(fam_val) if isinstance(fam_val, list) else str(fam_val)
                    grid[c_idx].markdown(f"**Word Families / Roots**\n\n{fam_out}")
                    c_idx += 1

                if inc_sketch:
                    grid[c_idx].markdown("**Dual Coding Space**")
                    c_idx += 1

                st.divider()

        except Exception as e:
            st.error(f"Error generating resource: {e}")
