Yes, exactly—updating these text labels and dropdown options is as simple as making a quick tweak to your app.py file on GitHub!

Streamlit automatically detects changes to your repository and redeploys the app live within seconds of committing the update.

Updated app.py Code
Replace the entire contents of your app.py file on GitHub with this cleaned-up version:

Python
import streamlit as st
import json
import pandas as pd
from google import genai
from google.genai import types
from PIL import Image
import io

# Page Configuration
st.set_page_config(
    page_title="Vocabulary Support Generator", 
    page_icon="📚", 
    layout="wide"
)

# Connect securely to Gemini API via Streamlit Secrets
api_key = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=api_key)

# Title
st.title("📚 Vocabulary Support Generator")

# --- SIDEBAR CONTROLS ---
st.sidebar.header("1. Target Options")
word_count = st.sidebar.slider("Number of words to extract", min_value=1, max_value=8, value=5)
target_year = st.sidebar.selectbox("Year", ["Year 7", "Year 8", "Year 9", "Year 10", "Year 11"])

st.sidebar.header("2. Active Table Columns")
inc_def = st.sidebar.checkbox("Definition", value=True)
inc_sentence = st.sidebar.checkbox("Example Sentence", value=True)
inc_related = st.sidebar.checkbox("Related Words", value=True)
inc_dual_coding = st.sidebar.checkbox("Dual Coding (Generated Image)", value=True)

# --- MAIN INTERFACE ---
user_text = st.text_area("Paste Text Below", height=200)

if st.button("Generate Resource Grid", type="primary"):
    if not user_text.strip():
        st.warning("Please paste a text passage before generating.")
    else:
        with st.spinner("Analyzing text, processing vocabulary, and generating images..."):
            
            # Construct API Prompt
            prompt = f"""
            Analyze the following text meant for {target_year} secondary school students. 
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

                # Process each extracted word row
                for item in vocab_data:
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
