import streamlit as st
import json
import pandas as pd
from google import genai
from google.genai import types
from PIL import Image
import io

# Page Configuration
st.set_page_config(
    page_title="Explicit Vocabulary Generator", 
    page_icon="📚", 
    layout="wide"
)

# Connect securely to Gemini API via Streamlit Secrets
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

st.title("📚 Classroom Vocabulary Resource Generator")
st.write("Extract high-utility Tier 2 vocabulary from curriculum texts and generate custom, print-ready teaching grids.")

# --- SIDEBAR CONTROLS ---
st.sidebar.header("1. Target Options")
word_count = st.sidebar.slider("Number of words to extract", min_value=1, max_value=8, value=5)
target_year = st.sidebar.selectbox("Target Key Stage / Year", ["KS1 (Years 1-2)", "LKS2 (Years 3-4)", "UKS2 (Years 5-6)", "KS3 (Years 7-9)"])

st.sidebar.header("2. Active Table Columns")
st.sidebar.write("Toggle features to include or exclude from the generated resource:")
inc_def = st.sidebar.checkbox("Definition", value=True)
inc_sentence = st.sidebar.checkbox("Example Sentence", value=True)
inc_related = st.sidebar.checkbox("Related Words", value=True)
inc_dual_coding = st.sidebar.checkbox("Dual Coding (Generated Image)", value=True)

# --- MAIN INTERFACE ---
user_text = st.text_area("Paste English Curriculum Passage Here:", height=200, placeholder="e.g., London lies to-day under the spell of a great terror...")

if st.button("Generate Resource Grid", type="primary"):
    if not user_text.strip():
        st.warning("Please paste a text passage before generating.")
    else:
        with st.spinner("Analyzing text, processing vocabulary, and generating images..."):
            
            # Construct API Prompt based on toggling selections
            prompt = f"""
            Analyze the following text meant for {target_year} students. 
            Extract up to {word_count} target Tier 2 words suitable for explicit vocabulary instruction.
            
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
                # Text Generation API Call
                text_response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    ),
                )
                
                vocab_data = json.loads(text_response.text)
                
                st.markdown("---")
                st.subheader(" Learning New Vocabulary")
                st.caption("Printable preview grid generated based on active toggles.")

                # Process each extracted word row
                for item in vocab_data:
                    # Dynamically determine columns based on active checkboxes
                    active_cols = [("Key Word", True)]
                    if inc_def: active_cols.append(("Definition", True))
                    if inc_sentence: active_cols.append(("Example Sentence", True))
                    if inc_related: active_cols.append(("Related Words", True))
                    if inc_dual_coding: active_cols.append(("Image", True))
                    
                    grid = st.columns(len(active_cols))
                    col_idx = 0

                    # 1. Key Word
                    with grid[col_idx]:
                        st.markdown(f"**Key Word**\n\n### {item.get('word')}\n*({item.get('word_class')})*")
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

                    # 5. Generated Image
                    if inc_dual_coding:
                        with grid[col_idx]:
                            st.markdown("**Image**")
                            with st.spinner("Drawing image..."):
                                img_prompt = f"Simple black and white vector line illustration for educational dual coding representing the word '{item.get('word')}': {item.get('image_prompt', '')}"
                                
                                img_response = client.models.generate_images(
                                    model='imagen-3.0-generate-002',
                                    prompt=img_prompt,
                                    config=types.GenerateImagesConfig(
                                        number_of_images=1,
                                        aspect_ratio="1:1"
                                    )
                                )
                                
                                for generated_image in img_response.generated_images:
                                    image = Image.open(io.BytesIO(generated_image.image.image_bytes))
                                    st.image(image, use_container_width=True)
                        col_idx += 1

                    st.divider()

            except Exception as e:
                st.error(f"Error generating resource: {e}")
