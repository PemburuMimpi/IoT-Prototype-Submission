import os #import file lokal
import shutil #untuk copy file
import whisper #import library whisper
import gdown #untuk download file dari gdrive
import io #untuk stream file
import urllib.request #untuk request url
from flask import Flask, jsonify #import flask untuk web server
from pymongo import MongoClient #untuk mongodb
from datetime import datetime #untuk timestamp
from transformers import pipeline #untuk flan T5 Hugging Face
import google.generativeai as genai #untuk Gemini AI
from google.oauth2 import service_account #untuk autentikasi google
from googleapiclient.discovery import build #untuk go
from googleapiclient.http import MediaFileUpload #untuk upload file ke gdrive
from dotenv import load_dotenv #untuk laod environment (environment tersembunyi)
from nltk import sent_tokenize #untuk tokenisasi kalimat
import nltk #untuk tokenisasi kalimat
import requests #untuk request HTTP
from mutagen import File as AudioFile #untuk metadata audio

#Menambahkan path ffmpeg secara manual, ffmpeg digunakan untuk mengkonversi file audio
os.environ["PATH"] += os.pathsep + r"C:\ffmpeg\bin"

#Mengunduh NLTK tokenizer
nltk.download("punkt")

#Pengaturan Flask
app = Flask(__name__)
LOCAL_AUDIO_PATH = "audiodummy5.wav"
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Pengaturan MongoDB
load_dotenv()
MONGO_API_KEY = os.getenv("MONGO_API_KEY")
client = MongoClient(f"mongodb+srv://pemburu_mimpi:{MONGO_API_KEY}@cluster0.asss8ea.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["MyDatabase"]
collection = db["AudioCollection"]

# Pengaturan Google Dribe
SERVICE_ACCOUNT_FILE = "gen-lang-client-0752400739-f435cb86fb2c.json"
SCOPES = ['https://www.googleapis.com/auth/drive.file']
FOLDER_ID = "1PQj1cwcaPXoegou7hWmKX1McT5UPZxYC"
credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# Pengaturan ubidots
UBIDOTS_TOKEN = "BBUS-k6iBnYKTfNh1RD8QSe2e6NHeZS2CeE"
DEVICE_LABEL = "esp32-mimpikita"

def send_to_ubidots(link):
    url = f"https://industrial.api.ubidots.com/api/v1.6/devices/{DEVICE_LABEL}"
    payload = {
        "gdrive_url_string": {
            "value": 1,
            "context": {
                "link": link
            }
        }
    }
    headers = {
        "X-Auth-Token": UBIDOTS_TOKEN,
        "Content-Type": "application/json"
    }
    requests.post(url, json=payload, headers=headers)

# Kirim metadata audio (bit rate, stream rate) ke Ubidots
def send_audio_metadata_to_ubidots(audio_path):
    audio = AudioFile(audio_path)
    format_type = type(audio).__name__
    sample_rate = getattr(audio.info, 'sample_rate', None)
    bit_rate = getattr(audio.info, 'bitrate', None)

    print("Format:", format_type)
    print("Sample Rate:", sample_rate)
    print("Bit Rate:", bit_rate)

    url = f"https://industrial.api.ubidots.com/api/v1.6/devices/{DEVICE_LABEL}"
    payload = {
        "format_audio": {
            "value": 1,
            "context": {"type": format_type}
        },
        "sample_rate": sample_rate,
        "bit_rate": bit_rate
    }
    headers = {
        "X-Auth-Token": UBIDOTS_TOKEN,
        "Content-Type": "application/json"
    }
    res = requests.post(url, json=payload, headers=headers)
    print("Ubidots audio metadata status:", res.status_code)
    print("Ubidots response:", res.json())

# Inisiasing model Whisper
whisper_model = whisper.load_model("base")

# Inisiasi Gemini AI
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Inisiasi fungsi untuk upload file ke Google Drive
def upload_to_drive(file_path, filename):
    file_metadata = {'name': filename, 'parents': [FOLDER_ID]}
    media = MediaFileUpload(file_path, mimetype='audio/wav')
    uploaded_file = drive_service.files().create(
        body=file_metadata, media_body=media, fields='id'
    ).execute()
    return uploaded_file['id']

#Inisiasi fungsi untuk membuat file di Google Drive menjadi publik
def make_file_public(file_id):
    permission = {'type': 'anyone', 'role': 'reader'}
    drive_service.permissions().create(fileId=file_id, body=permission).execute()

#Inisiasi fungsi fact check menggunakan FLAN-T5
def fact_check_sentences(sentences):
    generator = pipeline("text2text-generation", model="google/flan-t5-small", device=0, framework="pt")
    explanations = []
    for sentence in sentences:
        try:
            prompt = f"Claim: {sentence}\nQuestion: Is this claim factually correct? If not, explain the correct information."
            response = generator(prompt, max_new_tokens=200)[0]['generated_text'].strip()
            explanations.append((sentence, response))
        except Exception as e:
            explanations.append((sentence, f"[Error] {e}"))
    return explanations

#Inisiasi fungsi untuk meringkas teks menggunakan Gemini AI
def summarize_with_gemini(text):
    genai.configure(api_key=GEMINI_API_KEY)
    try:
        model = genai.GenerativeModel('models/gemini-1.5-pro')
        prompt = f"Buat ringkasan disertai dengan Fact Check dalam bentuk poin-poin dari teks berikut:\n{text}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"[Gemini ERROR] {e}"

#Kesimpulan akhir dari semua proses
def process_and_analyze(file_id):
    url = f"https://drive.google.com/uc?id={file_id}"
    output_filename = "recording.wav"
    gdown.download(url, output_filename, quiet=False)

    result = whisper_model.transcribe(output_filename)
    text = result["text"]

    original_sentences = sent_tokenize(text)
    fact_check_results = fact_check_sentences(original_sentences)
    summary = summarize_with_gemini(text)

    return {
        "transcript": text,
        "fact_check": fact_check_results,
        "summary": summary
    }

#Halaman awal web
@app.route("/", methods=["GET"])
def home():
    return "<h2>Flask Aktif ✅<br>Gunakan endpoint <code>/send-local</code> untuk kirim file.</h2>"

#Upload menggunakan flask dan dikirimkan ke mongoDB
@app.route("/send-local", methods=["GET"])
def send_local_file():
    if not os.path.exists(LOCAL_AUDIO_PATH):
        return jsonify({"error": "File .wav tidak ditemukan"}), 404

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"audio_{timestamp}.wav"
    copied_path = os.path.join(UPLOAD_FOLDER, filename)
    shutil.copy(LOCAL_AUDIO_PATH, copied_path)

    # Kirim metadata audio ke Ubidots
    send_audio_metadata_to_ubidots(copied_path)

    file_id = upload_to_drive(copied_path, filename)
    make_file_public(file_id)
    
    drive_url = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    send_to_ubidots(drive_url)

    analysis_results = process_and_analyze(file_id)

    document = {
        "filename": filename,
        "timestamp": timestamp,
        "drive_url": drive_url,
        "source": "local_storage",
        "transcript": analysis_results["transcript"],
        "summary": analysis_results["summary"],
        "fact_check": [
            {"claim": claim, "explanation": explanation}
            for claim, explanation in analysis_results["fact_check"]
        ]
    }
    collection.insert_one(document)

    return jsonify({
        "message": "File berhasil dikirim & dianalisis.",
        "filename": filename,
        "drive_url": document["drive_url"],
        "transcript": document["transcript"],
        "summary": document["summary"],
        "fact_check": document["fact_check"]
    }), 200

#Menjalankan Flask
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
