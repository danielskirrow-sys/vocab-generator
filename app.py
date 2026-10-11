import streamlit as st
import json
import pandas as pd
import urllib.parse
import requests
from PIL import Image
import io
import concurrent.futures

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from google import genai
from google.genai import types

# Configuration
st.set_page_config(page_title="Vocabulary Support Generator", page_icon="📚", layout="wide")

api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

# 1. Image Fetcher (Pollinations.ai)
def fetch_single_image(word, prompt_text):
    try:
        raw_prompt = f"simple black white line art icon for {word}, {prompt_text}"
        encoded_prompt = urllib.parse.quote(raw_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=300&height=300&nologo=true&seed=42"
        res = requests.get(url, timeout=12)
        if res.status_code == 200:
            return Image.open(io.BytesIO(res.content)), None
        return None, f"HTTP {res.status_code}"
    except Exception as e:
        return None, str(e)

# 2. PDF Generator
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
                row.append(RLImage(img_byte_arr, width=55, height=55))
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

# 3. Main Interface
st.title("📚 Vocabulary Support Generator")

st.sidebar.header("1. Target Options")
word_count = st.sidebar.slider("Number of words to extract", min_value=1, max_value=8, value=5)
target_year = st.sidebar.selectbox("Year", ["Year 7", "Year 8", "Year 9", "Year 10", "Year 11"])

st.sidebar.header("2. Active Table Columns")
inc_def = st.sidebar.checkbox("Definition", value=True)
inc_sentence = st.sidebar.checkbox("Example Sentence", value=True)
inc_related = st.sidebar.checkbox("Related Words", value=True)
inc_dual_coding = st.sidebar.checkbox("Dual Coding (Generated Image)", value=True)

user_text = st.text_area("Paste Text Below", height=200)

if st.button("Generate Resource Grid", type="primary"):
    if not user_text.strip():
        st.warning("Please paste a text passage before generating.")
    else:
        status = st.empty()
        status.info("Analysing text and processing vocabulary...")
        
        prompt = f"Analyze the following text for {target_year} UK secondary students. Extract up to {word_count} Tier 2 words. Use British English spelling. Passage: '{user_text}'. Return a JSON array with fields: word, word_class, definition, sentence, related_words, image_prompt."

        try:
            text_response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            
            vocab_data = json.loads(text_response.text)
            
            image_dict = {}
            if inc_dual_coding:
                status.info("Generating dual coding visuals...")
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future_to_word = {
                        executor.submit(fetch_single_image, item.get('word'), item.get('image_prompt', '')): item.get('word') 
                        for item in vocab_data
                    }
                    for future in concurrent.futures.as_completed(future_to_word):
                        word = future_to_word[future]
                        try:
                            image_dict[word] = future.result()
                        except Exception as err:
                            image_dict[word] = (None, str(err))

            status.empty()
            st.markdown("---")
            
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

            for item in vocab_data:
                word = item.get('word')
                active_cols = [("Key Word", True)]
                if inc_def: active_cols.append(("Definition", True))
                if inc_sentence: active_cols.append(("Example Sentence", True))
                if inc_related: active_cols.append(("Related Words", True))
                if inc_dual_coding: active_cols.append(("Image", True))
                
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

                if inc_dual_coding:
                    with grid[col_idx]:
                        st.markdown("**Image**")
                        img, err_msg = image_dict.get(word, (None, None))
                        if img:
                            st.image(img, use_container_width=True)
                        elif err_msg:
                            st.caption(f"🖼️ *(Image error: {err_msg[:60]}...)*")
                        else:
                            st.caption("🖼️ *(Visual unavailable)*")
                    col_idx += 1

                st.divider()

        except Exception as e:
            st.error(f"Error generating resource: {e}")
