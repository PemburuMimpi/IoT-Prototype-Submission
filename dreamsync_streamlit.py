import streamlit as st
from pymongo import MongoClient
import requests
import base64
import os

# Setup MongoDB
MONGO_API_KEY = st.secrets["MONGO_API_KEY"]
client = MongoClient(f"mongodb+srv://pemburu_mimpi:{MONGO_API_KEY}@cluster0.asss8ea.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["MyDatabase"]
collection = db["AudioCollection"]

# Judul Halaman
st.set_page_config(page_title="DREAMSYNC'S Ringkasan Audio AI", layout="centered")

# === Custom CSS ===
st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-family: 'Segoe UI', sans-serif;
    }
    .info-card {
        background-color: #f0f2f6;
        border-left: 5px solid #4a90e2;
        padding: 10px 20px;
        margin-bottom: 20px;
        border-radius: 6px;
    }
    .scroll-box {
        overflow-y: scroll;
        height: 250px;
        border: 1px solid #ccc;
        padding: 10px;
        border-radius: 5px;
        background-color: #f9f9f9;
    }
    </style>
""", unsafe_allow_html=True)

# Title
st.title("📚 DREAMSYNC'S Summaries!")
st.markdown("*Sensor:* INMP441 | *Transkrip:* Whisper | *Ringkasan:* Gemini AI | *Fact-Check:* Hugging Face T5")

# Load Data
docs = list(collection.find().sort("timestamp", -1))

if not docs:
    st.warning("🚫 Belum ada data di database")
else:
    st.header("🎧 Data Rekaman")

    # Pilih file
    filenames = [doc['filename'] for doc in docs]
    selected_filename = st.sidebar.selectbox("Pilih file rekaman", filenames)
    selected_doc = next((doc for doc in docs if doc["filename"] == selected_filename), None)

    if selected_doc:
        st.markdown(f"""
            <div class="info-card">
                <strong>🕒 Timestamp:</strong> {selected_doc['timestamp']}<br>
                <strong>📄 File:</strong> {selected_doc['filename']}<br>
                <strong>🔗 Link Google Drive:</strong> <a href="{selected_doc['drive_url']}" target="_blank">Buka Link</a>
            </div>
        """, unsafe_allow_html=True)

        # === Embed Audio ===
        drive_url = selected_doc['drive_url']
        try:
            drive_id = drive_url.split('/d/')[1].split('/')[0]
            download_url = f"https://drive.google.com/uc?export=download&id={drive_id}"

            response = requests.get(download_url)
            if response.status_code == 200:
                audio_bytes = response.content
                b64_audio = base64.b64encode(audio_bytes).decode()
                st.audio(f"data:audio/wav;base64,{b64_audio}", format="audio/wav")
            else:
                st.warning("⚠️ Gagal mengunduh audio dari Google Drive.")
        except Exception as e:
            st.warning("⚠️ Format URL Google Drive tidak valid atau file tidak bisa diakses.")
            st.error(f"Detail error: {e}")

        # === Transkrip ===
        st.markdown("---")
        st.subheader("📜 Transkrip")
        st.write(selected_doc['transcript'])

        # === Ringkasan ===
        st.markdown("---")
        st.subheader("📝 Ringkasan")
        if isinstance(selected_doc['summary'], list):
            st.markdown("<div class='scroll-box'>", unsafe_allow_html=True)
            for point in selected_doc['summary']:
                st.write(f"• {point}")
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Ringkasan belum tersedia untuk file ini.")

        # === Fact-Check ===
        st.markdown("---")
        st.subheader("❌✅ Hasil Fact-Check")
        if isinstance(selected_doc['fact_check'], list):
            for item in selected_doc['fact_check']:
                st.markdown(f"""
                    <div class="info-card">
                        <strong>👉 Klaim:</strong> {item.get('claim', '-')}\n
                        <strong>✅ Status:</strong> {item.get('status', '-')}\n
                        <strong>💬 Penjelasan:</strong> {item.get('explanation', '-')}\n
                        <strong>🔗 Sumber:</strong> <a href="{item.get('source', '#')}" target="_blank">{item.get('source', '(tidak tersedia)')}</a>
                    </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Fact-check belum tersedia untuk file ini.")
