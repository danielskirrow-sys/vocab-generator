import streamlit as st
import json
import requests
import io

# ReportLab Imports for PDF Generation
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Page Configuration
st.set_page_config(
    page_title="Vocabulary Support Generator", 
    page_icon="📚", 
    layout="wide"
)

api_key = st.secrets["GEMINI_API_KEY"]

# --- 1. DIRECT REST API CALL (Fast & Anti-Stall) ---
def extract_vocab(text, target_year, word_count):
    prompt = f"""
    Analyze the following text meant for {target_year} secondary school students in the UK. 
    Extract up to {word_count} target Tier 2 words suitable for explicit vocabulary instruction.
    Use British English spelling in all definitions and example sentences.
    
    Passage:
    "{text}"
    
    Return a JSON array where each object strictly contains the following fields:
    - word: Target word
    - word_class: Word class (e.g. Noun, Verb, Adjective)
    - definition: Student-friendly definition suitable for {target_year}
    - sentence: Example sentence showing practical classroom usage
    - related_words: Array of related forms or morphology
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }

    # Hard 8-second timeout prevents indefinite hanging
    response = requests.post(url, headers=headers, json=payload, timeout=8)
    
    if response.status_code == 200:
        res_data = response.json()
        raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(raw_text)
    else:
        raise Exception(f"API Error {response.status_code}: {response.text[:100]}")

# --- 2. LANDSCAPE A4 PDF GENERATOR ---
def generate_pdf(vocab_data, inc_def, inc_sentence, inc_related):
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

# --- 3. MAIN UI INTERFACE ---
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
        with st.spinner("Generating vocabulary support grid..."):
            try:
                vocab_data = extract_vocab(user_text, target_year, word_count)
                
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
