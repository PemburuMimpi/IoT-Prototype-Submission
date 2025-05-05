# ========================
# 📦 IMPORT LIBRARY
# ========================
import os                   # Untuk operasi sistem (buat folder, cek file, dll)
import threading            # Untuk membuat proses berjalan di background (thread)
from datetime import datetime  # Untuk ambil waktu sekarang (timestamp)
from flask import Flask, request, jsonify  # Flask = framework web server, untuk handle request & response
from pymongo import MongoClient            # Untuk koneksi ke MongoDB
from dotenv import load_dotenv             # Untuk load file .env (isi API key, token, dll)
import whisper              # Library Whisper untuk transkrip audio jadi teks
import nltk                 # Library NLP (Natural Language Processing), buat tokenisasi kalimat
import requests             # Untuk kirim HTTP request ke API lain (contohnya ke Ubidots)
from mutagen import File as AudioFile      # Untuk baca metadata dari file audio (sample rate, bitrate)
from transformers import pipeline          # Untuk pipeline NLP dari HuggingFace (fact-check model)
import google.generativeai as genai         # Untuk akses Gemini AI
from google.oauth2 import service_account  # Untuk autentikasi Google API pakai service account
from googleapiclient.discovery import build # Untuk akses Google Drive API
from googleapiclient.http import MediaFileUpload  # Untuk upload file ke Google Drive


# ========================
# ⚙️ KONFIGURASI
# ========================
nltk.download("punkt_tab")  # Download resource tokenizer dari NLTK

# Inisialisasi Flask app
app = Flask(__name__)       # Membuat server Flask instance
UPLOAD_FOLDER = "uploads"   # Nama folder tempat nyimpen file upload
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Buat folder kalau belum ada
load_dotenv()  # Baca file .env buat ambil API Key, Token, dll

# Konfigurasi MongoDB
MONGO_API_KEY = os.getenv("MONGO_API_KEY")   # Ambil Mongo API Key dari environment
client = MongoClient(f"mongodb+srv://pemburu_mimpi:{MONGO_API_KEY}@cluster0.asss8ea.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["MyDatabase"]                    # Pilih database
collection = db["AudioCollection"]            # Pilih collection

# Pengaturan Google Drive
SERVICE_ACCOUNT_FILE = "gen-lang-client-0752400739-f435cb86fb2c.json"  # File service account JSON
SCOPES = ['https://www.googleapis.com/auth/drive.file']               # Hak akses ke Google Drive
credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)  # Koneksi ke Google Drive API
FOLDER_ID = "1PQj1cwcaPXoegou7hWmKX1McT5UPZxYC"                # ID folder Google Drive untuk upload

# Pengaturan Ubidots
UBIDOTS_TOKEN = "BBUS-k6iBnYKTfNh1RD8QSe2e6NHeZS2CeE"  # Token untuk akses Ubidots
DEVICE_LABEL = "esp32-mimpikita"                      # Nama device di Ubidots

# Inisialisasi model Whisper
whisper_model = whisper.load_model("turbo")   # Load model Whisper turbo

# Inisialisai Gemini AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")   # Ambil Gemini API Key dari environment

# Set untuk melacak file yang sudah diproses
processed_files = set()  # Set untuk simpan file yang sudah diproses, biar gak dobel

# ========================
# 🔧 FUNGSI - FUNGSI
# ========================

# Fungsi upload ke Google Drive dan membuat permission public
def upload_to_drive(file_path, filename):
    """Mengupload file ke Google Drive."""
    file_metadata = {'name': filename, 'parents': [FOLDER_ID]} #inisialisasi metadata file
    media = MediaFileUpload(file_path, mimetype='audio/wav') 
    uploaded = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    drive_service.permissions().create(fileId=uploaded['id'], body={'type': 'anyone', 'role': 'reader'}).execute()
    return uploaded['id']

# Fungsi kirim data ke Ubidots
def send_to_ubidots(payload):
    """Mengirim data ke Ubidots."""
    url = f"https://industrial.api.ubidots.com/api/v1.6/devices/{DEVICE_LABEL}"
    headers = {"X-Auth-Token": UBIDOTS_TOKEN, "Content-Type": "application/json"}
    res = requests.post(url, json=payload, headers=headers)
    print(f"🔔 Status kirim ke Ubidots: {res.status_code}")
    return res.json()

# Fungsi kirim link Google Drive ke Ubidots
def send_gdrive_link_to_ubidots(link):
    """Mengirim link Google Drive ke Ubidots."""
    payload = {"gdrive_url_string": {"value": 1, "context": {"link": link}}}
    send_to_ubidots(payload)

# Fungsi kirim metadata audio ke Ubidots
def send_audio_metadata_to_ubidots(audio_path):
    """Mengirim metadata audio ke Ubidots."""
    audio = AudioFile(audio_path)
    payload = {
        "format_audio": {"value": 1, "context": {"type": type(audio).__name__}},
        "sample_rate": getattr(audio.info, 'sample_rate', 0),
        "bit_rate": getattr(audio.info, 'bitrate', 0)
    }
    send_to_ubidots(payload)

# Fungsi buat ringkasan + fact check pakai Gemini
def summarize_with_gemini(text):
    """Meringkas teks dan fact-check menggunakan Gemini AI, lengkap dengan sumber terpercaya."""
    genai.configure(api_key=GEMINI_API_KEY)
    try:
        model = genai.GenerativeModel('models/gemini-2.0-flash')
        prompt = (
            f"Buatlah:\n"
            f"- Ringkasan singkat berbentuk poin-poin dari teks berikut.\n"
            f"- Lakukan fact-check terhadap isi teks tersebut.\n"
            f"- Sertakan sumber terpercaya berupa link URL untuk setiap fact-check.\n\n"
            f"Teks:\n{text}\n\n"
            f"Format jawaban:\n"
            f"Ringkasan:\n- ...\n- ...\n\nFact-Check:\n- Klaim: ...\n  Status: Benar/Salah\n  Penjelasan: ...\n  Sumber: [link]"
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"[Gemini ERROR] {e}"

# Fungsi utama proses DREAMSYNC (pengecekan file duplikat, transkripsi, upload ke Google Drive, kirim ke Ubidots, simpan ke MongoDB)
def process_audio(filepath, filename, timestamp):
    """Memproses file audio."""
    if filename in processed_files:
        print(f"⚠️ File duplikat ditemukan, melewati: {filename}")
        try:
            os.remove(filepath)
            print(f"🗑️ File duplikat dihapus: {filepath}")
        except Exception as e:
            print(f"❌ Gagal menghapus file duplikat {filepath}: {e}")
        return
    processed_files.add(filename)

    try:
        print(f"🛠️ Mulai memproses file: {filename}")

        # Transkripsi audio
        result = whisper_model.transcribe(filepath)
        text = result["text"]

        # Ringkasan + Fact Check langsung dari Gemini
        summary = summarize_with_gemini(text)

        # Upload ke Google Drive
        file_id = upload_to_drive(filepath, filename)
        drive_url = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
        
        # Kirim link gdrive ke ubidots
        send_gdrive_link_to_ubidots(drive_url)

        # Kirim metadata audio
        send_audio_metadata_to_ubidots(filepath)

        # Simpan ke MongoDB
        document = {
            "filename": filename,
            "timestamp": timestamp,
            "drive_url": drive_url,
            "source": "iot_esp32",
            "transcript": text,
            "summary": summary
        }
        collection.insert_one(document)

        print(f"✅ Berhasil memproses file: {filename}")
    except Exception as e:
        print(f"❌ Terjadi kesalahan saat memproses {filename}: {e}")
    finally:
        try:
            os.remove(filepath)
            print(f"🗑️ File telah dihapus dari server: {filepath}")
            print("======================================================================")
        except Exception as e:
            print(f"❌ Gagal menghapus file {filepath}: {e}")
        processed_files.discard(filename)


# ========================
# 🌐 FLASK ROUTES
# ========================

# Endpoint utama untuk menandakan server aktif
@app.route("/", methods=["GET"])
def home():
    """Endpoint utama, menandakan server aktif."""
    print("🌐 Ada yang mengakses halaman utama server.")
    return "<h2>Server Flask Aktif ✅ - Endpoint /upload untuk ESP32 kirim file</h2>"

# Endpoint untuk upload file
@app.route("/upload", methods=["POST"])
def upload_file():
    """Menerima file upload dari ESP32."""
    if 'file' not in request.files:
        print("⚠️ Tidak ada file dikirim oleh client!")
        return jsonify({"error": "Tidak ada file dikirim oleh client!"}), 400
    
    file = request.files['file']
    if file.filename == '':
        print("⚠️ Nama file kosong!")
        return jsonify({"error": "Nama file kosong!"}), 400

    # Nama file yang disimpan di server sesuai dengan nama file dari esp32
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = file.filename
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    print(f"📥 File diterima: {filename}")

    # Proses total DREAMSYNC dilakukan di background
    threading.Thread(target=process_audio, args=(filepath, filename, timestamp), daemon=True).start()

    # Kirim response ke ESP32 bahwa file diterima dan sedang diproses
    return jsonify({"message": "File diterima, diproses di background"}), 200

# ========================
# 🚀 MAIN
# ========================

# Menjalankan server Flask
# Kode ini membuat server Flask hidup, siap menerima permintaan dari luar
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
