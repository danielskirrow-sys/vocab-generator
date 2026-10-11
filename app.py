import streamlit as st
import json
import pandas as pd
from google import genai
from google.genai import types
from PIL import Image
import io
import concurrent.futures

# PDF Generation Imports (ReportLab)
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Page Configuration
st.set_page_config(
    page_title="Vocabulary Support Generator", 
    page_icon="📚", 
    layout="wide"
)

# Connect securely to Gemini API via Streamlit Secrets
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

# --- HELPER FUNCTION 1: Fetch Single Image Safely ---
def fetch_single_image(word, prompt_text):
    try:
        img_prompt = f"Simple black and white vector line illustration for educational dual coding representing the word '{word}': {prompt_text}"
        img_response = client.models.generate_images(
            model='imagen-3.0-generate-002',
            prompt=img_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="1:1"
            )
        )
        for generated_image in img_response.generated_images:
            return Image.open(io.BytesIO(generated_image.image.image_bytes))
    except Exception:
        return None

# --- HELPER FUNCTION 2: Generate Landscape A4 PDF ---
def generate_pdf(vocab_data, inc_def, inc_sentence, inc_related, inc_dual_coding, image_dict):
    buffer = io.BytesIO()
    # Using Landscape A4 to cleanly fit all table columns
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=16, leading=20, spaceAfter=10)
    cell_style = ParagraphStyle('GridCell', parent=styles['Normal'], fontSize=9, leading=12)
    header_style = ParagraphStyle('GridHeader', parent=styles['Normal'], fontSize=10, leading=12, fontName="Helvetica-Bold")

    # Header Title
    elements.append(Paragraph("Learning New Vocabulary", title_style))
    elements.append(Spacer(1, 10))

    # Define Column Headers
    headers = [Paragraph("Key Word", header_style)]
    if inc_def: headers.append(Paragraph("Definition", header_style))
    if inc_sentence: headers.append(Paragraph("Example Sentence", header_style))
    if inc_related: headers.append(Paragraph("Related Words", header_style))
    if inc_dual_coding: headers.append(Paragraph("Image", header_style))

    table_data = [headers]

    # Populate Data Rows
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
            img = image_dict.get(word)
            if img:
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                row.append(RLImage(img_byte_arr, width=55, height=55))
            else:
                row.append(Paragraph("N/A", cell_style))
                
        table_data.append(row)

    # Calculate column widths evenly based on active selections
    num_cols = len(headers)
    total_width = 780 # Landscape printable width
    col_width = total_width / num_cols

    # Format Table Layout
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

# Sidebar Controls
st.sidebar.header("1. Target Options")
word_count = st.sidebar.slider("Number of words to extract", min_value=1, max_value=8, value=5)
target_year = st.sidebar.selectbox("Year", ["Year 7", "Year 8", "Year 9", "Year 10", "Year 11"])

st.sidebar.header("2. Active Table Columns")
inc_def = st.sidebar.checkbox("Definition", value=True)
inc_sentence = st.sidebar.checkbox("Example Sentence", value=True)
inc_related = st.sidebar.checkbox("Related Words", value=True)
inc_dual_coding = st.sidebar.checkbox("Dual Coding (Generated Image)", value=True)

# User Text Input
user_text = st.text_area("Paste Text Below", height=200)

if st.button("Generate Resource Grid", type="primary"):
    if not user_text.strip():
        st.warning("Please paste a text passage before generating.")
    else:
        with st.spinner("Analysing text and processing vocabulary..."):
            
            # API Prompt Construction
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
                # Text Generation Call
                text_response = client.models.generate_content(
                    model='gemini-3.8-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                
                vocab_data = json.loads(text_response.text)
                
                # Fetch images in parallel
                image_dict = {}
                if inc_dual_coding:
                    with st.spinner("Generating dual coding visuals in parallel..."):
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future_to_word = {
                                executor.submit(fetch_single_image, item.get('word'), item.get('image_prompt', '')): item.get('word') 
                                for item in vocab_data
                            }
                            for future in concurrent.futures.as_completed(future_to_word):
                                word = future_to_word[future]
                                try:
                                    image_dict[word] = future.result()
                                except Exception:
                                    image_dict[word] = None

                st.markdown("---")
                
                # Top Action Bar with Download Button
                col_title, col_btn = st.columns([3, 1])
                with col_title:
                    st.subheader(" Learning New Vocabulary")
                with col_btn:
                    # Generate PDF buffer for download button
                    pdf_buffer = generate_pdf(vocab_data, inc_def, inc_sentence, inc_related, inc_dual_coding, image_dict)
                    st.download_button(
                        label="📥 Download Printable PDF",
                        data=pdf_buffer,
                        file_name="Vocabulary_Worksheet.pdf",
                        mime="application/pdf",
                        type="primary"
                    )

                # Display On-Screen Grid Preview
                for item in vocab_data:
                    word = item.get('word')
                    active_cols = [("Key Word", True)]
                    if inc_def: active_cols.append(("Definition", True))
                    if inc_sentence: active_cols.append(("Example Sentence", True))
                    if inc_related: active_cols.append(("Related Words", True))
                    if inc_dual_coding: active_cols.append(("Image", True))
                    
                    grid = st.columns(len(active_cols))
                    col_idx = 0

                    # 1. Key Word
                    with grid[col_idx]:
                        st.markdown(f"**Key Word**\n\n### {word}\n*({item.get('word_class')})*")
                    col_idx += 1

                    # 2. Definition
                    if inc_def:
                        with grid[col_idx]:
                            st.markdown(f"**Definition**\n\n{item.get('definition', 'N/A')}")
                        col_idx += 1

                    # 3. Example Sentence
                    if inc_sentence:
                        with grid[col_idx]:
                            st.markdown(f"**Example Sentence**\n\n*{item.get('sentence', 'N/A')}*")
                        col_idx += 1

                    # 4. Related Words
                    if inc_related:
                        with grid[col_idx]:
                            rel_list = item.get('related_words', [])
                            rel_str = ", ".join(rel_list) if isinstance(rel_list, list) else rel_list
                            st.markdown(f"**Related Words**\n\n{rel_str}")
                        col_idx += 1

                    # 5. Image
                    if inc_dual_coding:
                        with grid[col_idx]:
                            st.markdown("**Image**")
                            img = image_dict.get(word)
                            if img:
                                st.image(img, use_container_width=True)
                            else:
                                st.caption("🖼️ *(Visual unavailable)*")
                        col_idx += 1

                    st.divider()

            except Exception as e:
                st.error(f"Error generating resource: {e}")
