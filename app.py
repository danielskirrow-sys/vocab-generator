import streamlit as st
import json
import requests
import io
import time

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="Vocabulary Support Generator", page_icon="📖", layout="wide")

api_key = st.secrets.get("GEMINI_API_KEY", "")

# Session State Initialization
if "vocab_data" not in st.session_state:
    st.session_state.vocab_data = None
if "text_title" not in st.session_state:
    st.session_state.text_title = ""
if "target_band" not in st.session_state:
    st.session_state.target_band = ""


# --- 1. FIXED API CASCADE ENGINE ---
def call_gemini_cascade(prompt):
    models = ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash"]
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


# --- 2. VOCABULARY EXTRACTOR PROMPT ENGINE ---
def extract_vocabulary_support(passage_text, mandatory_words, target_year, target_band, word_count, include_dual_coding, include_word_families, include_morphology):
    flightpath_map = {
        ("Year 7", "Developing (Grades 1-3)"): "Entry / Access Level (KS2 to KS3 bridge, highly grounded and clear vocabulary)",
        ("Year 7", "Reaching (Grades 4-6)"): "Year 7 Secure / Working towards GCSE Grade 2-3 (Accessible Tier 2 academic words, no overly complex Latinate terms)",
        ("Year 7", "Mastering (Grades 7-9)"): "Year 7 High Attainer / Working towards GCSE Grade 4-5 (Ambitious yet clean, practical vocabulary)",
        
        ("Year 8", "Developing (Grades 1-3)"): "Year 8 Foundation / GCSE Grade 1-2 equivalent",
        ("Year 8", "Reaching (Grades 4-6)"): "Year 8 Secure / GCSE Grade 3-4 equivalent (Grounded academic Tier 2 words)",
        ("Year 8", "Mastering (Grades 7-9)"): "Year 8 High Attainer / GCSE Grade 5-6 equivalent",
        
        ("Year 9", "Developing (Grades 1-3)"): "Year 9 Foundation / GCSE Grade 2-3 equivalent",
        ("Year 9", "Reaching (Grades 4-6)"): "Year 9 Secure / GCSE Grade 4-5 equivalent",
        ("Year 9", "Mastering (Grades 7-9)"): "Year 9 High Attainer / GCSE Grade 6-7 equivalent",

        ("Year 10", "Developing (Grades 1-3)"): "GCSE Grades 1-3 Foundation",
        ("Year 10", "Reaching (Grades 4-6)"): "GCSE Grades 4-6 Intermediate",
        ("Year 10", "Mastering (Grades 7-9)"): "GCSE Grades 7-9 Higher Mastery",

        ("Year 11", "Developing (Grades 1-3)"): "GCSE Grades 1-3 Foundation",
        ("Year 11", "Reaching (Grades 4-6)"): "GCSE Grades 4-6 Intermediate",
        ("Year 11", "Mastering (Grades 7-9)"): "GCSE Grades 7-9 Higher Mastery"
    }

    calibrated_level = flightpath_map.get((target_year, target_band), f"{target_year} {target_band}")

    mandatory_instruction = ""
    if mandatory_words.strip():
        mandatory_instruction = f"\n\nMANDATORY REQUIREMENT: You MUST include these teacher-specified words: '{mandatory_words}'."

    extra_fields = []
    if include_word_families:
        extra_fields.append("'word_family' (related forms e.g. noun/verb/adjective forms)")
    if include_morphology:
        extra_fields.append("'morphology' (root word, prefix, or etymology breakdown)")

    extra_fields_str = ", ".join(extra_fields)
    if extra_fields_str:
        extra_fields_str = f", along with {extra_fields_str}"

    prompt = (
        f"Act as an expert UK Secondary English teacher. Extract target vocabulary for {target_year} pupils "
        f"calibrated strictly to flightpath standard: '{calibrated_level}'. Use UK English spelling throughout.\n\n"
        f"PEDAGOGICAL GUIDELINES:\n"
        f"- Focus on high-utility Tier 2 vocabulary required to comprehend or analyze this text.\n"
        f"- Do NOT select obscure, archaic, or unnecessarily pretentiously elevated words.\n"
        f"- Ensure definitions are concise, pupil-friendly, and accessible.\n\n"
        f"Target Word Count: {word_count}\n"
        f"Source Context: '{passage_text}'{mandatory_instruction}\n\n"
        f"Return a JSON array where each object strictly contains keys: word, word_class, definition, model_phrase{extra_fields_str}."
    )
    return call_gemini_cascade(prompt)


def replace_single_vocab_word(rejected_word, target_band, passage_text, current_words, include_word_families, include_morphology):
    existing_list = ", ".join([w.get('word', '') for w in current_words if w.get('word')])
    
    extra_keys = ""
    if include_word_families:
        extra_keys += ", word_family"
    if include_morphology:
        extra_keys += ", morphology"

    prompt = (
        f"Act as an expert UK Secondary English teacher. Generate 1 replacement target vocabulary item "
        f"for flightpath standard '{target_band}'. Word to replace: '{rejected_word}'. "
        f"Do NOT generate these existing words: {existing_list}. Context: '{passage_text}'. "
        f"Use UK English. Return a JSON array containing EXACTLY ONE object with keys: word, word_class, definition, model_phrase{extra_keys}."
    )
    res = call_gemini_cascade(prompt)
    if isinstance(res, list) and len(res) > 0:
        return res[0]
    return None


# --- 3. LANDSCAPE A4 PDF GENERATOR WITH DUAL CODING & PEDAGOGY EXTENSIONS ---
def generate_vocab_pdf(vocab_data, text_title, target_band, include_dual_coding, include_word_families, include_morphology):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=15, leading=18, spaceAfter=2)
    sub_style = ParagraphStyle('DocSub', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.HexColor("#555555"), spaceAfter=10)
    cell_body = ParagraphStyle('CellBody', parent=styles['Normal'], fontSize=8, leading=10)
    draw_label = ParagraphStyle('DrawLabel', parent=styles['Normal'], fontSize=7, leading=8, textColor=colors.HexColor("#777777"))

    doc_label = f"Vocabulary Support Sheet: {text_title}" if text_title else "Vocabulary Support Sheet"
    elements.append(Paragraph(doc_label, title_style))
    elements.append(Paragraph(f"<b>Level:</b> {target_band}", sub_style))

    rows = []
    current_row = []
    for item in vocab_data:
        w_name = item.get('word', '')
        w_class = item.get('word_class', '')
        w_def = item.get('definition', '')
        w_phrase = item.get('model_phrase', '')

        cell_text = f"<b><font size=10 color='#111111'>{w_name}</font></b> <i>({w_class})</i><br/>" + f"<b>Meaning:</b> {w_def}<br/>" + f"<b>Usage:</b> <i>\"{w_phrase}\"</i>"

        if include_word_families and item.get('word_family'):
            w_fam = item.get('word_family')
            cell_text += f"<br/><b>Word Family:</b> {w_fam}"
            
        if include_morphology and item.get('morphology'):
            w_morph = item.get('morphology')
            cell_text += f"<br/><b>Root/Etymology:</b> {w_morph}"

        cell_elements = [Paragraph(cell_text, cell_body)]

        if include_dual_coding:
            cell_elements.append(Spacer(1, 4))
            draw_box = Table([[Paragraph("<i>Draw a visual icon / sketch:</i>", draw_label)]], colWidths=[240], rowHeights=[38])
            draw_box.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fafafa")),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('PADDING', (0, 0), (-1, -1), 3)
            ]))
            cell_elements.append(draw_box)

        current_row.append(cell_elements)
        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []

    if current_row:
        while len(current_row) < 3:
            current_row.append([Paragraph("", cell_body)])
        rows.append(current_row)

    t = Table(rows, colWidths=[260, 260, 260])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#fdfdfd")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('PADDING', (0, 0), (-1, -1), 6)
    ]))
    elements.append(t)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# --- 4. USER INTERFACE ---
st.title("📖 Vocabulary Support Generator")

st.sidebar.header("1. Target Options")
vocab_year = st.sidebar.selectbox("Target Year Group", ["Year 7", "Year 8", "Year 9", "Year 10", "Year 11"], index=3, key="vocab_year_select")

vocab_band = st.sidebar.selectbox("Target Attainment Band", [
    "Developing (Grades 1-3)", 
    "Reaching (Grades 4-6)", 
    "Mastering (Grades 7-9)"
], index=1, key="vocab_band_select")

vocab_count = st.sidebar.slider("Number of Vocabulary Items", min_value=6, max_value=18, value=12, key="vocab_count_slider")

st.sidebar.header("2. Layout & Pedagogical Options")
include_dual_coding = st.sidebar.checkbox("Include Dual Coding Space (Drawing Box)", value=True, key="cb_dual_coding")
include_word_families = st.sidebar.checkbox("Include Word Families", value=False, key="cb_word_families")
include_morphology = st.sidebar.checkbox("Include Morphology / Etymology", value=False, key="cb_morphology")

# Main Page Inputs
text_title_input = st.text_input("Text / Topic Title (Optional)", placeholder="e.g. Macbeth Act 1 Scene 2 OR Victorian Child Labour Article", key="vocab_title_input")

c1, c2 = st.columns(2)

prompt_placeholder = "Paste reading passage or topic context here..."
mandatory_placeholder = "e.g. tyrant, valorous (Separate multiple words with commas)"

with c1:
    passage_input = st.text_area(
        "Source Text / Context", 
        placeholder=prompt_placeholder,
        height=160,
        key="vocab_passage_input"
    )

with c2:
    mandatory_input = st.text_area(
        "Words to Include (Optional)", 
        placeholder=mandatory_placeholder,
        height=160,
        key="vocab_mandatory_input"
    )

generate_vocab = st.button("Generate Vocabulary Support Grid", type="primary", key="vocab_generate_btn", use_container_width=True)

if generate_vocab:
    if not passage_input.strip():
        st.warning("Please enter a source text or context.")
    elif not api_key:
        st.error("Missing GEMINI_API_KEY in Streamlit Secrets.")
    else:
        with st.spinner("Generating..."):
            try:
                data = extract_vocabulary_support(
                    passage_input, 
                    mandatory_input, 
                    vocab_year, 
                    vocab_band, 
                    vocab_count,
                    include_dual_coding,
                    include_word_families,
                    include_morphology
                )
                st.session_state.vocab_data = data
                st.session_state.text_title = text_title_input
                st.session_state.target_band = vocab_band
            except Exception as e:
                st.error(f"Error generating resource: {e}")

# Render Web Grid & PDF if data exists in Session State
if st.session_state.vocab_data is not None:
    vocab_pdf = generate_vocab_pdf(
        st.session_state.vocab_data, 
        st.session_state.text_title, 
        st.session_state.target_band,
        include_dual_coding,
        include_word_families,
        include_morphology
    )

    st.markdown("---")
    col_title, col_btn = st.columns([3, 1])
    col_title.subheader("Generated Vocabulary Support Grid")
    col_btn.download_button(
        label="📥 Download Printable PDF (A4)",
        data=vocab_pdf,
        file_name="Vocabulary_Support_Sheet.pdf",
        mime="application/pdf",
        type="primary",
        key="dl_vocab_pdf"
    )

    cols = st.columns(3)
    for idx, item in enumerate(st.session_state.vocab_data):
        with cols[idx % 3]:
            with st.container(border=True):
                st.subheader(item.get('word', ''))
                st.caption(f"*({item.get('word_class', '')})*")
                st.write(f"**Meaning:** {item.get('definition', '')}")
                st.write(f"**Usage:** *\"{item.get('model_phrase', '')}\"*")
                
                if include_word_families and item.get('word_family'):
                    st.write(f"**Word Family:** {item.get('word_family')}")
                if include_morphology and item.get('morphology'):
                    st.write(f"**Root/Etymology:** {item.get('morphology')}")

                if include_dual_coding:
                    st.caption("✏️ *Dual Coding Sketch Box included on Printable PDF*")

                btn_key = f"replace_vocab_{item.get('word', '')}_{idx}"
                if st.button("🔄 Replace Word", key=btn_key, use_container_width=True):
                    with st.spinner("Replacing..."):
                        try:
                            replacement = replace_single_vocab_word(
                                item.get('word', ''),
                                st.session_state.target_band,
                                passage_input,
                                st.session_state.vocab_data,
                                include_word_families,
                                include_morphology
                            )
                            if replacement:
                                for orig_idx, orig_item in enumerate(st.session_state.vocab_data):
                                    if orig_item.get('word') == item.get('word'):
                                        st.session_state.vocab_data[orig_idx] = replacement
                                        break
                                st.rerun()
                        except Exception as e:
                            st.error(f"Could not replace word: {e}")
