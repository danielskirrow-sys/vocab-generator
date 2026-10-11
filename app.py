import streamlit as st
import json
import urllib.parse
import requests
from PIL import Image
import io
import time

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from google import genai
from google.genai import types

# Page Configuration
st.set_page_config(page_title="Vocabulary Support Generator", page_icon="📚", layout="wide")

# Connect securely to Gemini API
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

# 1. Fast Image Fetcher
def fetch_single_image(word, prompt_text):
    try:
        raw_prompt = f"simple line art icon for {word}"
        encoded_prompt = urllib.parse.quote(raw_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=250&height=250&nologo=true"
        
        res = requests.get(url, timeout=3)
        if res.status_code == 200:
            return Image.open(io.BytesIO(res.content)), None
        return None, f"HTTP {res.status_code}"
    except Exception:
        return None, "Timeout"

# 2. Hardened Text Generation with Fast Model Fallbacks
def generate_text_with_timeout(prompt):
    # Models ordered by speed and availability
    candidate_models = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-3.8-flash']
    
    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                ),
            )
            if response.text:
                return response.text
        except Exception:
            continue
            
    raise Exception("API connection timed out. Please refresh the page and try again.")

# 3. PDF Generator
def generate_pdf(vocab_data, inc_def, inc_sentence, inc_related, inc_dual_coding, image_dict):
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
    if inc_dual_coding: headers.append(Paragraph("Image", header_style))

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
        if inc_dual_coding:
            img, err = image_dict.get(word, (None, None))
            if img:
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                row.append(RLImage(img_byte_arr, width=50, height=50))
            else:
                row.append(Paragraph("N/A", cell_style))
                
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

# 4. Main UI Interface
st.title("📚 Vocabulary Support Generator")

st.sidebar.header("1. Target Options")
word_count = st.sidebar.slider("Number of words to extract", min_value=1, max_value=8, value=5)
target_year = st.sidebar.selectbox("Year", ["Year 7", "Year 8", "Year 9", "Year 10", "Year 11"])

st.sidebar.header("2. Active Table Columns")
inc_def = st.sidebar.checkbox("Definition", value=True)
inc_sentence = st.sidebar.checkbox("Example Sentence", value=True)
inc_related = st.sidebar.checkbox("Related Words", value=True)
inc_dual_coding = st.sidebar.checkbox("Dual Coding (Generated Image)", value=False)

user_text = st.text_area("Paste Text Below", height=200)

if st.button("Generate Resource Grid", type="primary"):
    if not user_text.strip():
        st.warning("Please paste a text passage before generating.")
    else:
        with st.spinner("Analysing text and generating resources..."):
            
            prompt = f"Analyze the following text for {target_year} UK secondary students. Extract up to {word_count} Tier 2 words suitable for explicit instruction. Use British English spelling throughout. Passage: '{user_text}'. Return a JSON array where each object strictly contains: word, word_class, definition, sentence, related_words, image_prompt."

            try:
                # 1. High-Speed Content Generation
                raw_json = generate_text_with_timeout(prompt)
                vocab_data = json.loads(raw_json)
                
                # 2. Dual Coding Fetching (Only runs when enabled)
                image_dict = {}
                if inc_dual_coding:
                    for item in vocab_data:
                        w = item.get('word')
                        p = item.get('image_prompt', '')
                        image_dict[w] = fetch_single_image(w, p)

                st.markdown("---")
                
                # Header Action Bar
                col_title, col_btn = st.columns([3, 1])
                with col_title:
                    st.subheader(" Learning New Vocabulary")
                with col_btn:
                    pdf_buffer = generate_pdf(vocab_data, inc_def, inc_sentence, inc_related, inc_dual_coding, image_dict)
                    st.download_button(
                        label="📥 Download Printable PDF",
                        data=pdf_buffer,
                        file_name="Vocabulary_Worksheet.pdf",
                        mime="application/pdf",
                        type="primary"
                    )

                # Render Table Grid
                for item in vocab_data:
                    word = item.get('word')
                    active_cols = [("Key Word", True)]
                    if inc_def: active_cols.append(("Definition", True))
                    if inc_sentence: active_cols.append(("Example Sentence", True))
                    if inc_related: active_cols.append(("Related Words", True))
                    if inc_dual_coding: active_cols.append(("Image", True))
                    
                    grid = st.columns(len(active_cols))
                    col_idx = 0

                    # Word
                    with grid[col_idx]:
                        st.markdown(f"**Key Word**\n\n### {word}\n*({item.get('word_class')})*")
                    col_idx += 1

                    # Definition
                    if inc_def:
                        with grid[col_idx]:
                            st.markdown(f"**Definition**\n\n{item.get('definition', 'N/A')}")
                        col_idx += 1

                    # Sentence
                    if inc_sentence:
                        with grid[col_idx]:
                            st.markdown(f"**Example Sentence**\n\n*{item.get('sentence', 'N/A')}*")
                        col_idx += 1

                    # Related
                    if inc_related:
                        with grid[col_idx]:
                            rel_list = item.get('related_words', [])
                            rel_str = ", ".join(rel_list) if isinstance(rel_list, list) else rel_list
                            st.markdown(f"**Related Words**\n\n{rel_str}")
                        col_idx += 1

                    # Image
                    if inc_dual_coding:
                        with grid[col_idx]:
                            st.markdown("**Image**")
                            img, err_msg = image_dict.get(word, (None, None))
                            if img:
                                st.image(img, use_container_width=True)
                            else:
                                st.caption("🖼️ *(Visual unavailable)*")
                        col_idx += 1

                    st.divider()

            except Exception as e:
                st.error(f"Error generating resource: {e}")
