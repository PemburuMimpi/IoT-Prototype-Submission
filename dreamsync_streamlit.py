import streamlit as st # untuk streamlit
from pymongo import MongoClient #untuk MongoDB
import pandas as pd # memanipulasi/analisis data
import requests  # untuk download file dari URL
import base64  # untuk encode file audio ke base64

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

st.title("DREAMSYNC'S Summaries!:open_book:")
st.markdown("*Sensor:* INMP441 | *Transkrip:* Whisper | *Ringkasan:* Gemini AI  | *Fact Check :* Hugging Face T5")

# Ambil data dari MongoDB
docs = list(collection.find().sort("timestamp", -1))

if not docs:
    st.warning("🚫 Belum ada data di database")
else:
    st.header("💻 Data Rekaman")

    # untuk memilih audio
    filenames = [doc['filename'] for doc in docs]
    selected_filename = st.sidebar.selectbox("Pilih file", filenames)  
    selected_doc = next((doc for doc in docs if doc["filename"] == selected_filename), None)

    #untuk desain streamlit
    if selected_doc:
        st.markdown(f"""
            <div class="info-card">
                <strong> 🕒 Timestamp: {selected_doc['timestamp']}<br>
                <strong> 📝Ringkasan: {selected_doc['filename']}<br>
                <strong> 🎧Link Audio: {selected_doc['drive_url']}" target="_blank">Buka Link</a>
            </div>
        """, unsafe_allow_html=True)

        # === Embed audio file dari Google Drive (pake base64) ===
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
                st.warning("Gagal mengunduh audio dari Google Drive.")
        except Exception as e:
            st.warning("🔗 Format URL Google Drive tidak valid atau file tidak bisa diakses.")
            st.error(f"Detail error: {e}")

        st.markdown("---")
        st.subheader("📜Transkrip")
        st.write(selected_doc['transcript'])

        st.markdown("---")
        st.subheader("📝Ringkasan")
        st.markdown(
            f"""
            <div style='overflow-y: scroll; height: 250px; border: 1px solid #ccc; padding: 10px; border-radius: 5px; background-color: #f9f9f9'>
                {selected_doc['summary']}
            </div>
            """,
            unsafe_allow_html=True
        )
        
        st.markdown("---")
        st.subheader("❌✅ Hasil Fact Check")
        for item in selected_doc['fact_check']:
            st.markdown(f"* 👉 Claim:* {item['claim']}")
            st.markdown(f"> 💡 {item['explanation']}")
            st.markdown("---")
