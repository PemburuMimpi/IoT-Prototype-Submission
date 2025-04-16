import streamlit as st # untuk streamlit
from pymongo import MongoClient #untuk MongoDB
import pandas as pd # memanipulasi/analisis data
import streamlit_scrollable_textbox as stx

# Setup MongoDB
MONGO_API_KEY = st.secrets["MONGO_API_KEY"]
client = MongoClient(f"mongodb+srv://pemburu_mimpi:{MONGO_API_KEY}@cluster0.asss8ea.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["MyDatabase"]
collection = db["AudioCollection"]

# Judul Halaman
st.set_page_config(page_title="DREAMSYNC'S Ringkasan Audio AI", layout="centered")
st.title("DREAMSYNC'Summaries!:open_book:")
st.markdown("*Sensor:* INMP441 | *Transkrip:* Whisper | *Ringkasan:* Gemini AI")

# Ambil data dari MongoDB
docs = list(collection.find().sort("timestamp", -1))


if not docs:
    st.warning("Belum ada data di database")
else:
    st.header("💻Data from MongoDB")

    # untuk memilih audio
    filenames = [doc['filename'] for doc in docs]
    selected_filename = st.sidebar.selectbox("Pilih file", filenames)  
    selected_doc = next((doc for doc in docs if doc["filename"] == selected_filename), None)

    #untuk desain streamlit
    if selected_doc:
        st.markdown(f"🕒 Timestamp: {selected_doc['timestamp']}")
        st.markdown(f"📝Ringkasan: {selected_doc['filename']}")
        st.markdown(f"Link Audio: {selected_doc['drive_url']}")


        st.markdown("---")
        st.subheader("Transkrip")
        st.write(selected_doc['transcript'])

        st.markdown("---")
        st.subheader("Ringkasan")
        stx.scrollableTextbox( 
            selected_doc['summary'],
            height=250,           # tinggi kotaknya
            border=True)
        
        st.markdown("---")
        st.subheader("Hasil Fact Check")
        for item in selected_doc['fact_check']:
            st.markdown(f"*Claim:* {item['claim']}")
            st.markdown(f"> 💡 {item['explanation']}")
            st.markdown("---")
