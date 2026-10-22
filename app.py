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
        cell_text = (
            f"<b><font size=10 color='#111111'>{item.get('word', '')}</font></b> <i>({item.get('word_class', '')})</i><br/>"
            f"<b>Meaning:
