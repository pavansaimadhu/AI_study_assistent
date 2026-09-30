import os
import io
import time
import base64
import tempfile
from pathlib import Path

import streamlit as st
from google import genai
from google.genai import types
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


# ============================================================
# APP CONFIGURATION
# ============================================================

APP_NAME = "AI Study Assistant"

# Primary + fallback models
TEXT_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]

STT_MODEL = "gemini-3.5-transcribe"
TTS_MODEL = "gemini-3.8-flash-tts"
TTS_VOICE = "Kore"

MAX_PDF_SIZE_MB = 50


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>

    .main-title {
        font-size: 42px;
        font-weight: 700;
        margin-bottom: 5px;
    }

    .subtitle {
        font-size: 18px;
        color: #9ca3af;
        margin-bottom: 25px;
    }

    .feature-card {
        padding: 18px;
        border-radius: 14px;
        background: #1f2937;
        border: 1px solid #374151;
        margin-bottom: 10px;
    }

    .success-box {
        padding: 15px;
        border-radius: 12px;
        background: #064e3b;
        border: 1px solid #10b981;
    }

    .info-box {
        padding: 15px;
        border-radius: 12px;
        background: #172554;
        border: 1px solid #3b82f6;
    }

    .warning-box {
        padding: 15px;
        border-radius: 12px;
        background: #451a03;
        border: 1px solid #f59e0b;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# API KEY
# ============================================================

def get_api_key():
    """
    Get Gemini API key from:
    1. Streamlit secrets
    2. Environment variable

    Never hardcode the API key in source code.
    """

    # Streamlit secrets
    try:
        key = st.secrets.get("GEMINI_API_KEY")

        if key:
            return key

    except Exception:
        pass

    # Environment variable
    key = os.getenv("GEMINI_API_KEY")

    return key


GEMINI_API_KEY = get_api_key()


# ============================================================
# CHECK API KEY
# ============================================================

if not GEMINI_API_KEY:

    st.error("❌ Gemini API key not found.")

    st.markdown(
        """
        ### Create this file:

        ```text
        AIstudy
        └── .streamlit
            └── secrets.toml
        ```

        Then put:

        ```toml
        GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
        ```

        Do not put the API key directly inside `app.py`.
        """
    )

    st.stop()


# ============================================================
# GEMINI CLIENT
# ============================================================

client = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# SYSTEM INSTRUCTION
# ============================================================

SYSTEM_INSTRUCTION = """
You are an expert AI Study Assistant for a Computer Science Engineering student.

Your job is to help the student understand study material clearly.

Main subjects may include:

- Artificial Intelligence
- Machine Learning
- Deep Learning
- Natural Language Processing
- Computer Vision
- Knowledge Representation
- First Order Logic
- Propositional Logic
- Inference
- Unification
- Resolution
- Search Algorithms
- BFS
- DFS
- Uniform Cost Search
- Greedy Best First Search
- A* Search
- Minimax
- Alpha-Beta Pruning
- Bayesian Networks
- Probability
- Fuzzy Logic
- Classification
- Regression
- Decision Trees
- Clustering
- Neural Networks
- Genetic Algorithms
- AI Agents

Teaching style:

1. Use simple English.
2. Explain concepts step by step.
3. Give easy examples.
4. Use tables when useful.
5. Include formulas when required.
6. Explain technical terms.
7. For programming questions, provide complete code when appropriate.
8. For university exam questions, give answers suitable for 2, 5, 8 or 10 marks.
9. Clearly separate definitions, explanation, examples and advantages/disadvantages.
10. If the user asks about uploaded study material, answer using that material.
11. Do not invent information from the uploaded PDF.
12. If the answer cannot be found in the uploaded material, clearly say that.
13. Help the student prepare for exams.
14. Keep answers organized and easy to revise.
"""


# ============================================================
# SESSION STATE
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pdf_name" not in st.session_state:
    st.session_state.pdf_name = None

if "pdf_file" not in st.session_state:
    st.session_state.pdf_file = None

if "pdf_uri" not in st.session_state:
    st.session_state.pdf_uri = None

if "pdf_mime_type" not in st.session_state:
    st.session_state.pdf_mime_type = None

if "summary_text" not in st.session_state:
    st.session_state.summary_text = None

if "summary_pdf" not in st.session_state:
    st.session_state.summary_pdf = None

if "last_audio" not in st.session_state:
    st.session_state.last_audio = None

if "chat_active" not in st.session_state:
    st.session_state.chat_active = True


# ============================================================
# HELPER: TEMPORARY FILE
# ============================================================

def save_uploaded_file_temporarily(uploaded_file):
    """
    Save Streamlit UploadedFile to a temporary file.
    """

    suffix = Path(uploaded_file.name).suffix

    temp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
    )

    temp.write(uploaded_file.getvalue())
    temp.close()

    return temp.name


# ============================================================
# GEMINI TEXT GENERATION WITH FALLBACK
# ============================================================

def generate_text_with_fallback(contents, config=None):
    """
    Try multiple Gemini Flash models.

    Automatically retries temporary:
    - 503
    - 429
    - 500
    - UNAVAILABLE

    This prevents the application from failing immediately
    when a particular Gemini model is temporarily busy.
    """

    last_error = None

    for model_name in TEXT_MODELS:

        for attempt in range(3):

            try:

                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )

                if response and response.text:
                    return response.text, model_name

                raise RuntimeError(
                    f"Gemini returned an empty response from {model_name}"
                )

            except Exception as error:

                last_error = error

                error_text = str(error).upper()

                temporary_error = (
                    "503" in error_text
                    or "429" in error_text
                    or "500" in error_text
                    or "UNAVAILABLE" in error_text
                    or "RESOURCE_EXHAUSTED" in error_text
                )

                if temporary_error:

                    wait_time = 2 ** attempt

                    time.sleep(wait_time)

                    continue

                # Non-temporary error
                break

    raise RuntimeError(
        f"All Gemini text models failed.\n\n"
        f"Last error:\n{last_error}"
    )


# ============================================================
# UPLOAD PDF TO GEMINI
# ============================================================

def upload_pdf_to_gemini(uploaded_file):
    """
    Upload PDF through the official Gemini Files API.
    """

    temp_path = None

    try:

        temp_path = save_uploaded_file_temporarily(uploaded_file)

        uploaded_file_response = client.files.upload(
            file=temp_path
        )

        return uploaded_file_response

    finally:

        if temp_path and os.path.exists(temp_path):

            try:
                os.remove(temp_path)
            except Exception:
                pass


# ============================================================
# PDF SUMMARY
# ============================================================

def summarize_pdf():

    if not st.session_state.pdf_uri:

        raise RuntimeError(
            "Please upload a PDF first."
        )

    prompt = """
Summarize the uploaded study material for a Computer Science Engineering student.

Create a clear exam-oriented summary.

Include:

1. Important definitions
2. Main concepts
3. Important algorithms
4. Important formulas
5. Important examples
6. Advantages and disadvantages
7. Key points for examinations
8. Important terms to remember
9. Short revision notes
10. Possible exam questions

Keep the explanation detailed enough for studying but concise enough
to be useful as revision material.

Use headings and bullet points.

Do not add information that is not supported by the uploaded document.
"""

    input_data = [
        {
            "type": "document",
            "uri": st.session_state.pdf_uri,
            "mime_type": "application/pdf",
        },
        {
            "type": "text",
            "text": prompt,
        },
    ]

    last_error = None

    for model_name in TEXT_MODELS:

        for attempt in range(3):

            try:

                interaction = client.interactions.create(
                    model=model_name,
                    input=input_data,
                )

                if interaction.output_text:

                    return (
                        interaction.output_text,
                        model_name,
                    )

                raise RuntimeError(
                    "Gemini returned an empty summary."
                )

            except Exception as error:

                last_error = error

                error_text = str(error).upper()

                temporary_error = (
                    "503" in error_text
                    or "429" in error_text
                    or "500" in error_text
                    or "UNAVAILABLE" in error_text
                    or "RESOURCE_EXHAUSTED" in error_text
                )

                if temporary_error:

                    time.sleep(2 ** attempt)

                    continue

                break

    raise RuntimeError(
        f"PDF summarization failed.\n\n"
        f"Last error:\n{last_error}"
    )


# ============================================================
# ASK QUESTION ABOUT PDF
# ============================================================

def ask_pdf_question(question):

    if not st.session_state.pdf_uri:

        raise RuntimeError(
            "No study material is currently uploaded."
        )

    prompt = f"""
You are answering a student's question using the uploaded study material.

Student question:

{question}

Instructions:

- Answer using the uploaded document.
- Explain in simple English.
- If useful, give an example.
- If this is an exam question, structure the answer appropriately.
- If it is a 2-mark question, be concise.
- If it is a 5-mark question, provide definition + explanation + example.
- If it is an 8/10-mark question, provide a detailed structured answer.
- Do not invent facts.
- If the requested information is not available in the uploaded document,
  clearly state that.
"""

    input_data = [
        {
            "type": "document",
            "uri": st.session_state.pdf_uri,
            "mime_type": "application/pdf",
        },
        {
            "type": "text",
            "text": prompt,
        },
    ]

    last_error = None

    for model_name in TEXT_MODELS:

        for attempt in range(3):

            try:

                interaction = client.interactions.create(
                    model=model_name,
                    input=input_data,
                )

                if interaction.output_text:

                    return (
                        interaction.output_text,
                        model_name,
                    )

                raise RuntimeError(
                    "Gemini returned an empty answer."
                )

            except Exception as error:

                last_error = error

                error_text = str(error).upper()

                temporary_error = (
                    "503" in error_text
                    or "429" in error_text
                    or "500" in error_text
                    or "UNAVAILABLE" in error_text
                    or "RESOURCE_EXHAUSTED" in error_text
                )

                if temporary_error:

                    time.sleep(2 ** attempt)

                    continue

                break

    raise RuntimeError(
        f"Question answering failed.\n\n"
        f"Last error:\n{last_error}"
    )


# ============================================================
# NORMAL CHAT
# ============================================================

def ask_general_question(question):

    history_text = ""

    # Keep recent conversation
    recent_messages = st.session_state.messages[-12:]

    for message in recent_messages:

        role = message["role"]

        if role == "user":
            history_text += (
                f"\nStudent: {message['content']}\n"
            )

        elif role == "assistant":
            history_text += (
                f"\nAssistant: {message['content']}\n"
            )

    prompt = f"""
Previous conversation:

{history_text}

New student question:

{question}

Answer the student's question as an AI professor.

Use simple language and step-by-step explanations.
"""

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.3,
    )

    return generate_text_with_fallback(
        contents=prompt,
        config=config,
    )


# ============================================================
# SPEECH TO TEXT
# ============================================================

def transcribe_audio(audio_file):

    if audio_file is None:

        raise RuntimeError(
            "No audio recording found."
        )

    temp_path = None

    try:

        # Save audio temporarily
        suffix = ".wav"

        temp = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
        )

        temp.write(audio_file.getvalue())
        temp.close()

        temp_path = temp.name

        # Upload audio using Gemini Files API
        uploaded_audio = client.files.upload(
            file=temp_path
        )

        # Speech-to-text
        interaction = client.interactions.create(
            model=STT_MODEL,
            input=[
                {
                    "type": "audio",
                    "uri": uploaded_audio.uri,
                    "mime_type": uploaded_audio.mime_type,
                }
            ],
            generation_config={
                "transcription_config": {
                    "mode": "smart",
                    "language_codes": [],
                }
            },
        )

        if not interaction.output_text:

            raise RuntimeError(
                "No speech was detected."
            )

        return interaction.output_text

    finally:

        if temp_path and os.path.exists(temp_path):

            try:
                os.remove(temp_path)
            except Exception:
                pass


# ============================================================
# TEXT TO SPEECH
# ============================================================

def text_to_speech(text):

    # Limit very long answers
    text_for_audio = text[:12000]

    interaction = client.interactions.create(
        model=TTS_MODEL,
        input=[
            {
                "type": "user_input",
                "content": [
                    {
                        "type": "text",
                        "text": text_for_audio,
                        "annotations": [
                            {
                                "type": "speech_metadata",
                                "style": (
                                    "clear, friendly, "
                                    "educational and natural"
                                ),
                            }
                        ],
                    }
                ],
            }
        ],
        response_format={
            "type": "audio"
        },
        generation_config={
            "speech_config": [
                {
                    "voice": TTS_VOICE
                }
            ]
        },
    )

    if not interaction.output_audio:

        raise RuntimeError(
            "TTS did not return audio."
        )

    audio_data = interaction.output_audio.data

    return base64.b64decode(audio_data)


# ============================================================
# CREATE SUMMARY PDF
# ============================================================

def create_summary_pdf(summary_text, original_filename):

    buffer = io.BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Title"],
        alignment=TA_CENTER,
        fontSize=20,
        leading=24,
        spaceAfter=15,
    )

    heading_style = ParagraphStyle(
        "HeadingCustom",
        parent=styles["Heading2"],
        fontSize=13,
        leading=17,
        spaceBefore=10,
        spaceAfter=6,
    )

    body_style = ParagraphStyle(
        "BodyCustom",
        parent=styles["BodyText"],
        fontSize=9.5,
        leading=13,
        spaceAfter=5,
    )

    story = []

    story.append(
        Paragraph(
            "AI Study Assistant",
            title_style,
        )
    )

    story.append(
        Paragraph(
            "Study Material Summary",
            heading_style,
        )
    )

    story.append(
        Paragraph(
            f"Source: {original_filename}",
            body_style,
        )
    )

    story.append(Spacer(1, 10))

    # Convert basic markdown
    lines = summary_text.split("\n")

    for line in lines:

        line = line.strip()

        if not line:
            story.append(Spacer(1, 5))
            continue

        # Markdown heading
        if line.startswith("#"):

            clean = line.lstrip("#").strip()

            story.append(
                Paragraph(
                    clean,
                    heading_style,
                )
            )

        elif line.startswith("- "):

            clean = line[2:].strip()

            story.append(
                Paragraph(
                    f"• {clean}",
                    body_style,
                )
            )

        elif line.startswith("* "):

            clean = line[2:].strip()

            story.append(
                Paragraph(
                    f"• {clean}",
                    body_style,
                )
            )

        else:

            # Escape basic ampersand
            line = line.replace(
                "&",
                "&amp;"
            )

            story.append(
                Paragraph(
                    line,
                    body_style,
                )
            )

    document.build(story)

    buffer.seek(0)

    return buffer.getvalue()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("🎓 AI Study Assistant")

    st.write(
        "Your personal AI assistant for studying "
        "from PDFs and asking questions."
    )

    st.divider()

    st.subheader("🤖 Models")

    st.caption(
        f"Text: {TEXT_MODELS[0]}"
    )

    st.caption(
        f"Speech-to-Text: {STT_MODEL}"
    )

    st.caption(
        f"Text-to-Speech: {TTS_MODEL}"
    )

    st.divider()

    st.subheader("✨ Features")

    st.write("📄 PDF Study Material")
    st.write("📝 PDF Summarization")
    st.write("💬 PDF Question Answering")
    st.write("🎤 Voice Questions")
    st.write("🔊 AI Voice Answers")
    st.write("🧠 AI Study Chat")

    st.divider()

    if st.button(
        "🗑️ Clear Chat",
        use_container_width=True,
    ):

        st.session_state.messages = []

        st.rerun()

    if st.button(
        "🚪 Exit Chat",
        use_container_width=True,
    ):

        st.session_state.chat_active = False


# ============================================================
# MAIN HEADER
# ============================================================

st.markdown(
    '<div class="main-title">🎓 AI Study Assistant</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="subtitle">'
    'Learn from your study materials using Gemini AI'
    '</div>',
    unsafe_allow_html=True,
)


# ============================================================
# EXIT MESSAGE
# ============================================================

if not st.session_state.chat_active:

    st.info(
        "👋 Chat session ended."
    )

    if st.button("▶️ Start New Chat"):

        st.session_state.chat_active = True
        st.session_state.messages = []

        st.rerun()

    st.stop()


# ============================================================
# FEATURE CARDS
# ============================================================

col1, col2, col3 = st.columns(3)

with col1:

    st.markdown(
        """
        <div class="feature-card">
        <h3>📄 Study Materials</h3>
        Upload your PDF and learn directly from it.
        </div>
        """,
        unsafe_allow_html=True,
    )

with col2:

    st.markdown(
        """
        <div class="feature-card">
        <h3>🎤 Voice Questions</h3>
        Ask questions using your microphone.
        </div>
        """,
        unsafe_allow_html=True,
    )

with col3:

    st.markdown(
        """
        <div class="feature-card">
        <h3>🔊 AI Voice</h3>
        Listen to Gemini's answers.
        </div>
        """,
        unsafe_allow_html=True,
    )


st.divider()


# ============================================================
# PDF SECTION
# ============================================================

st.header("📄 Study Material")

uploaded_pdf = st.file_uploader(
    "Upload your study-material PDF",
    type=["pdf"],
    help="Maximum recommended size: 50 MB",
)


if uploaded_pdf:

    pdf_size_mb = (
        len(uploaded_pdf.getvalue())
        / (1024 * 1024)
    )

    if pdf_size_mb > MAX_PDF_SIZE_MB:

        st.error(
            f"❌ PDF is too large: "
            f"{pdf_size_mb:.2f} MB. "
            f"Maximum is {MAX_PDF_SIZE_MB} MB."
        )

    else:

        # Upload only when new PDF selected
        if (
            st.session_state.pdf_name
            != uploaded_pdf.name
        ):

            with st.spinner(
                "📤 Uploading study material to Gemini..."
            ):

                try:

                    gemini_file = upload_pdf_to_gemini(
                        uploaded_pdf
                    )

                    st.session_state.pdf_name = (
                        uploaded_pdf.name
                    )

                    st.session_state.pdf_file = (
                        uploaded_pdf.getvalue()
                    )

                    st.session_state.pdf_uri = (
                        gemini_file.uri
                    )

                    st.session_state.pdf_mime_type = (
                        gemini_file.mime_type
                    )

                    st.session_state.summary_text = None
                    st.session_state.summary_pdf = None

                    st.success(
                        f"✅ Loaded: {uploaded_pdf.name}"
                    )

                except Exception as error:

                    st.error(
                        "❌ PDF upload failed:"
                    )

                    st.exception(error)

        else:

            st.success(
                f"✅ Loaded: {uploaded_pdf.name}"
            )


# ============================================================
# PDF CONTROLS
# ============================================================

if st.session_state.pdf_uri:

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "📝 Summarize PDF",
            use_container_width=True,
        ):

            with st.spinner(
                "🤖 Gemini is reading and summarizing your PDF..."
            ):

                try:

                    summary, used_model = summarize_pdf()

                    st.session_state.summary_text = summary

                    st.session_state.summary_pdf = (
                        create_summary_pdf(
                            summary,
                            st.session_state.pdf_name,
                        )
                    )

                    st.success(
                        f"✅ Summary generated using {used_model}"
                    )

                except Exception as error:

                    st.error(
                        "❌ PDF summarization failed:"
                    )

                    st.exception(error)

    with col2:

        if st.button(
            "❌ Remove PDF",
            use_container_width=True,
        ):

            st.session_state.pdf_name = None
            st.session_state.pdf_file = None
            st.session_state.pdf_uri = None
            st.session_state.pdf_mime_type = None
            st.session_state.summary_text = None
            st.session_state.summary_pdf = None

            st.rerun()


# ============================================================
# SUMMARY DISPLAY
# ============================================================

if st.session_state.summary_text:

    st.divider()

    st.header("📝 PDF Summary")

    st.markdown(
        st.session_state.summary_text
    )

    st.download_button(
        label="⬇️ Download Summary PDF",
        data=st.session_state.summary_pdf,
        file_name="AI_Study_Material_Summary.pdf",
        mime="application/pdf",
        use_container_width=True,
    )


# ============================================================
# VOICE QUESTION SECTION
# ============================================================

st.divider()

st.header("🎤 Ask Using Your Voice")

st.write(
    "Record your question and Gemini will convert your speech "
    "to text and answer it."
)

audio_recording = st.audio_input(
    "🎙️ Record your question"
)


if audio_recording:

    st.audio(
        audio_recording
    )

    if st.button(
        "🎤 Transcribe & Ask",
        use_container_width=True,
    ):

        with st.spinner(
            "🎧 Converting your speech to text..."
        ):

            try:

                transcribed_text = transcribe_audio(
                    audio_recording
                )

                st.success(
                    "✅ Speech converted to text"
                )

                st.write(
                    f"**You asked:** {transcribed_text}"
                )

                # Add user message
                st.session_state.messages.append(
                    {
                        "role": "user",
                        "content": transcribed_text,
                    }
                )

                with st.spinner(
                    "🤖 Gemini is thinking..."
                ):

                    if st.session_state.pdf_uri:

                        answer, used_model = (
                            ask_pdf_question(
                                transcribed_text
                            )
                        )

                    else:

                        answer, used_model = (
                            ask_general_question(
                                transcribed_text
                            )
                        )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                    }
                )

                st.success(
                    f"Answered using {used_model}"
                )

                st.markdown(answer)

                # Generate speech
                with st.spinner(
                    "🔊 Generating voice..."
                ):

                    try:

                        response_audio = text_to_speech(
                            answer
                        )

                        st.audio(
                            response_audio,
                            format="audio/wav",
                        )

                    except Exception as tts_error:

                        st.warning(
                            "Text answer generated, "
                            "but voice generation failed."
                        )

                        st.caption(
                            str(tts_error)
                        )

            except Exception as error:

                st.error(
                    "❌ Voice processing failed:"
                )

                st.exception(error)


# ============================================================
# CHAT SECTION
# ============================================================

st.divider()

st.header("💬 Ask My AI Study Assistant")


# Display previous messages
for message in st.session_state.messages:

    role = message["role"]

    with st.chat_message(role):

        st.markdown(
            message["content"]
        )


# ============================================================
# TEXT CHAT INPUT
# ============================================================

question = st.chat_input(
    "Ask a question about your study material..."
)


if question:

    # Exit commands
    if question.lower().strip() in [
        "exit",
        "quit",
        "bye",
        "stop",
    ]:

        st.session_state.chat_active = False

        st.rerun()

    # Display user question
    with st.chat_message("user"):

        st.markdown(question)

    st.session_state.messages.append(
        {
            "role": "user",
            "content": question,
        }
    )

    # Generate answer
    with st.chat_message("assistant"):

        with st.spinner(
            "🤖 Gemini is thinking..."
        ):

            try:

                if st.session_state.pdf_uri:

                    answer, used_model = (
                        ask_pdf_question(
                            question
                        )
                    )

                else:

                    answer, used_model = (
                        ask_general_question(
                            question
                        )
                    )

                st.markdown(answer)

                st.caption(
                    f"Model: {used_model}"
                )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                    }
                )

                # TTS
                with st.spinner(
                    "🔊 Generating voice..."
                ):

                    try:

                        response_audio = text_to_speech(
                            answer
                        )

                        st.audio(
                            response_audio,
                            format="audio/wav",
                        )

                    except Exception as tts_error:

                        st.warning(
                            "Voice generation failed, "
                            "but the text answer is available."
                        )

                        st.caption(
                            str(tts_error)
                        )

            except Exception as error:

                st.error(
                    "❌ AI response failed:"
                )

                st.exception(error)


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "🎓 AI Study Assistant | "
    "Powered by Google Gemini API | "
    "Built with Streamlit"
)