import streamlit as st
import json
import urllib.parse
import requests
from PIL import Image
import io

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from google import genai
from google.genai import types

st.set_page_config(page_title="Vocabulary Support Generator", page_icon="📚", layout="wide")

api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

# 1. CACHED TEXT ANALYSIS (Instant response on re-renders)
@st.cache_data(show_spinner=False)
def analyze_vocabulary(text, target_year, word_count):
    prompt = f"""
    Analyze the following text for {target_year} UK secondary students. 
    Extract up to {word_count} Tier 2 words for explicit instruction. 
    Use British English spelling. 
    Passage: "{text}"
    Return a JSON array with fields: word, word_class, definition, sentence, related_words.
    """
    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    return json.loads(response.text)

# 2. PDF GENERATION
def generate_pdf(vocab_data, inc_def, inc_sentence, inc_related):
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
                
        table_data.append(row)

    num_cols = len(headers)
    total_width = 780
    col_width = total_width / num_cols

    t = Table(table_data, colWidths=[col_width] * num_cols)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# 3. INTERFACE
st.title("📚 Vocabulary Support Generator")

st.sidebar.header("1. Target Options")
word_count = st.sidebar.slider("Number of words to extract", min_value=1, max_value=8, value=5)
target_year = st.sidebar.selectbox("Year", ["Year 7", "Year 8", "Year 9", "Year 10", "Year 11"])

st.sidebar.header("2. Active Table Columns")
inc_def = st.sidebar.checkbox("Definition", value=True)
inc_sentence = st.sidebar.checkbox("Example Sentence", value=True)
inc_related = st.sidebar.checkbox("Related Words", value=True)

user_text = st.text_area("Paste Text Below", height=200)

if st.button("Generate Resource Grid", type="primary"):
    if not user_text.strip():
        st.warning("Please paste a text passage before generating.")
    else:
        with st.spinner("Analysing text..."):
            try:
                vocab_data = analyze_vocabulary(user_text, target_year, word_count)
                
                st.markdown("---")
                
                col_title, col_btn = st.columns([3, 1])
                with col_title:
                    st.subheader(" Learning New Vocabulary")
                with col_btn:
                    pdf_buffer = generate_pdf(vocab_data, inc_def, inc_sentence, inc_related)
                    st.download_button(
                        label="📥 Download Printable PDF",
                        data=pdf_buffer,
                        file_name="Vocabulary_Worksheet.pdf",
                        mime="application/pdf",
                        type="primary"
                    )

                for item in vocab_data:
                    word = item.get('word')
                    active_cols = [("Key Word", True)]
                    if inc_def: active_cols.append(("Definition", True))
                    if inc_sentence: active_cols.append(("Example Sentence", True))
                    if inc_related: active_cols.append(("Related Words", True))
                    
                    grid = st.columns(len(active_cols))
                    col_idx = 0

                    with grid[col_idx]:
                        st.markdown(f"**Key Word**\n\n### {word}\n*({item.get('word_class')})*")
                    col_idx += 1

                    if inc_def:
                        with grid[col_idx]:
                            st.markdown(f"**Definition**\n\n{item.get('definition', 'N/A')}")
                        col_idx += 1

                    if inc_sentence:
                        with grid[col_idx]:
                            st.markdown(f"**Example Sentence**\n\n*{item.get('sentence', 'N/A')}*")
                        col_idx += 1

                    if inc_related:
                        with grid[col_idx]:
                            rel_list = item.get('related_words', [])
                            rel_str = ", ".join(rel_list) if isinstance(rel_list, list) else rel_list
                            st.markdown(f"**Related Words**\n\n{rel_str}")
                        col_idx += 1

                    st.divider()

            except Exception as e:
                st.error(f"Error generating resource: {e}")
