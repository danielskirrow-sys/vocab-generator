import streamlit as st
import json
import pandas as pd
import urllib.parse
import requests
from PIL import Image
import io
import concurrent.futures

# PDF Generation Imports (ReportLab)
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from google import genai
from google.genai import types

# Page Configuration
st.set_page_config(
    page_title="Vocabulary Support Generator", 
    page_icon="📚", 
    layout="wide"
)

# Connect securely to Gemini API via Streamlit Secrets
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

# --- HELPER FUNCTION 1: Fetch Dual Coding Visual via Pollinations.ai (Fast & Reliable) ---
def fetch_single_image(word, prompt_text):
    try:
        # Build concise black-and-white vector line-art prompt
        raw_prompt = f"simple black and white vector line art illustration icon for educational dual coding representing the word {word}, {prompt_text}"
        encoded_prompt = urllib.parse.quote(raw_prompt)
        
        # Direct URL call
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=300&height=300&nologo=true&seed=42"
        
        response = requests.get(url, timeout=12)
        if response.status_code == 200:
            return Image.open(io.BytesIO(response.content)), None
        return None, f"HTTP {response.status_code}"
    except Exception as e:
        return None, str(e)

# --- HELPER FUNCTION 2: Generate Landscape A4 PDF ---
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


# --- MAIN UI INTERFACE ---
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
        with st.spinner("Analysing text and processing vocabulary..."):
            prompt = f"""
            Analyze the following text meant for {target_year} secondary school students in the UK. 
            Extract up to {word_count} target Tier 2 words suitable for explicit vocabulary instruction.
            Use British English spelling in all definitions and example sentences.
            
            Passage:
            "{user_text}"
            
            Return a JSON array where each object strictly contains the following fields:
            - word: Target word
            - word_class: Word class (e.g. Noun, Verb, Adjective)
            {"- definition: Student-friendly definition suitable for " + target_year if inc_def else ""}
            {"- sentence: Example sentence showing practical classroom usage" if inc_sentence else ""}
            {"- related_words: Array of related forms or morphology" if inc_related else ""}
            {"- image_prompt: Concise prompt for a clear visual/icon representing the word" if inc_dual_coding else ""}
            """

            try:
                text_response = client.models.generate_content(
                    model='gemini-3.8-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                
                vocab_data = json.loads(text_response.text)
                
                image_dict = {}
                if inc_dual_coding:
                    with st.spinner("Generating dual coding visuals
