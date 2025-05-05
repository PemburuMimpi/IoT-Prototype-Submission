# Import library yang dibutuhkan
import machine     # Akses ke hardware ESP32 (GPIO, SPI, I2C, dsb)
import ustruct     # Untuk manipulasi data biner (seperti header WAV)
import uos         # Untuk akses ke filesystem (SD card, dsb)
import time        # Untuk operasi berbasis waktu (delay, timestamp, dsb)
import socket      # Untuk membuat koneksi jaringan (TCP/HTTP client)
import ssd1306     # Library untuk kontrol OLED SSD1306
import sdcard      # Library untuk membaca/mount SD Card
from machine import I2S, Pin, I2C, SPI   # Import spesifik modul dari machine
import network     # Untuk setup WiFi pada ESP32

# === Variabel Global Wi-Fi ===
WIFI_SSID = "Didi"              # SSID WiFi
WIFI_PASSWORD = "23112024"     # Password WiFi

# === Variabel Global Flask ===
host = "192.168.23.170"          # Alamat IP server Flask lokal
port = 5000                      # Port server Flask

# === Setup Global Wi-Fi ===
wlan = network.WLAN(network.STA_IF)   # Membuat object WiFi sebagai Station (bukan Access Point)

# === Inisialisasi OLED (SSD1306) ===
i2c = I2C(1, scl=Pin(22), sda=Pin(21))   # Setup I2C channel 1 di pin GPIO22 (SCL) dan GPIO21 (SDA)
oled = ssd1306.SSD1306_I2C(128, 64, i2c) # Buat objek OLED resolusi 128x64 pixel menggunakan I2C

# Fungsi untuk menampilkan dua baris pesan sederhana di OLED
def show_oled_message(line1="", line2=""):
    oled.fill(0)            # Bersihkan layar OLED
    oled.text("DREAMSYNC", 0, 0)  # Judul di atas
    oled.hline(0, 12, 128, 1)          # Garis horizontal di bawah judul
    oled.text(line1, 0, 20)            # Konten baris 1
    oled.text(line2, 0, 32)            # Konten baris 2
    oled.show()             # Tampilkan perubahan ke layar

# Fungsi untuk menampilkan progress bar saat rekaman
def show_recording_progress(seconds):
    oled.fill(0)                                 # Bersihkan layar
    oled.text("DREAMSYNC", 0, 0)                             # Judul di atas
    oled.hline(0, 12, 128, 1)                                # Garis pemisah
    oled.text("Merekam...", 0, 20)                           # Geser status ke bawah
    oled.text(f"Durasi: {seconds}s", 0, 32)                  # Geser durasi
    oled.fill_rect(0, 48, int(seconds / MAX_RECORD_SECONDS * 128), 10, 1)  # Progress bar di bawah
    oled.show()                                  # Update OLED

# === Setup Wi-Fi ===
def connect_wifi(ssid, password):
    global wlan
    wlan.active(True)   # Aktifkan antarmuka Wi-Fi
    if not wlan.isconnected():
        print("Menghubungkan ke Wi-Fi...")
        wlan.connect(ssid, password) # Coba konek ke SSID dan password yang diberikan
        timeout = 15                 # Timeout dalam detik
        start = time.time()           # Catat waktu mulai
        while not wlan.isconnected() and (time.time() - start) < timeout:
            time.sleep(0.5)           # Tunggu setengah detik
        if not wlan.isconnected():
            raise Exception("Gagal koneksi Wi-Fi")  # Gagal koneksi
    print("Wi-Fi terhubung:", wlan.ifconfig())     # Print IP address

# === Setup SD Card ===
def mount_sd():
    spi = SPI(1, baudrate=1000000, polarity=0, phase=0, sck=Pin(18), mosi=Pin(23), miso=Pin(19)) # Setup SPI1
    cs = Pin(5, Pin.OUT)    # Chip select SD Card di pin GPIO5
    try:
        sd = sdcard.SDCard(spi, cs)          # Buat objek SD Card
        vfs = uos.VfsFat(sd)                 # Gunakan filesystem FAT
        uos.mount(vfs, "/sd")                # Mount filesystem ke /sd
        print("Kartu SD berhasil terpasang") 
    except Exception as e:
        print("Error kartu SD:", e)
        show_oled_message("Error SD Card!", str(e))
        raise e

# === Setup Mikrofon I2S ===
i2s = I2S(0, sck=Pin(14), ws=Pin(15), sd=Pin(32), mode=I2S.RX, bits=16, format=I2S.MONO, rate=16000, ibuf=32000)
# Setup I2S channel 0 sebagai receiver dengan format 16-bit mono, sample rate 16kHz, buffer 32kB

# === Inisialisasi Tombol & LED ===
button = Pin(13, Pin.IN, Pin.PULL_UP)   # Tombol input menggunakan internal pull-up resistor
led = Pin(2, Pin.OUT)                   # LED output di pin GPIO2
led.off()                               # Matikan LED saat start

# === Parameter Rekaman ===
SAMPLE_RATE = 16000          # Sample rate 16kHz
BITS = 16                   # Resolusi 16-bit per sample
CHANNELS = 1                # Mono
BUFFER_SIZE = 2048          # Buffer pembacaan I2S
MAX_RECORD_SECONDS = 20     # Durasi maksimal rekaman 30 detik

# === Membuat Header WAV ===
def create_wav_header(sample_rate, bits_per_sample, num_channels, num_samples):
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * num_channels * bits_per_sample // 8
    header = bytearray(44)                  # WAV header ukuran 44 byte
    header[0:4] = b'RIFF'                   # Chunk ID
    ustruct.pack_into('<I', header, 4, 36 + data_size) # Chunk size
    header[8:12] = b'WAVE'                  # Format
    header[12:16] = b'fmt '                 # Subchunk1 ID
    ustruct.pack_into('<I', header, 16, 16)  # Subchunk1 size (16 untuk PCM)
    ustruct.pack_into('<H', header, 20, 1)   # Audio format (1 = PCM)
    ustruct.pack_into('<H', header, 22, num_channels)   # Jumlah channel
    ustruct.pack_into('<I', header, 24, sample_rate)    # Sample rate
    ustruct.pack_into('<I', header, 28, byte_rate)      # Byte rate
    ustruct.pack_into('<H', header, 32, block_align)    # Block align
    ustruct.pack_into('<H', header, 34, bits_per_sample) # Bits per sample
    header[36:40] = b'data'                  # Subchunk2 ID
    ustruct.pack_into('<I', header, 40, data_size) # Subchunk2 size
    return header

# === Membuat Nama File Otomatis format audio_YYYYMMDD_HHMMSS.wav ===
def get_filename():
    timestamp = time.localtime()   # Ambil waktu lokal
    timestamp_str = f"{timestamp[0]}{timestamp[1]:02}{timestamp[2]:02}_{timestamp[3]:02}{timestamp[4]:02}{timestamp[5]:02}" 
    return f"/sd/audio_{timestamp_str}.wav"   # Kembalikan nama file format

# === Mengirim File ke Server Flask ===
def send_to_server(filename):
    s = None
    try:
        s = socket.socket()
        s.settimeout(30)            # Set timeout koneksi
        s.connect((host, port))      # Koneksikan ke server Flask
        
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"  # Boundary form-data
        filename_base = filename.split('/')[-1]
        file_size = uos.stat(filename)[6]                   # Ambil ukuran file
        
        # Header multipart/form-data
        header_part = (
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename_base}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode('utf-8')
        footer_part = f"\r\n--{boundary}--\r\n".encode('utf-8')
        content_length = len(header_part) + file_size + len(footer_part)
        
        # Kirim header HTTP
        request = [
            f"POST /upload HTTP/1.1",
            f"Host: {host}",
            f"Content-Type: multipart/form-data; boundary={boundary}",
            f"Content-Length: {content_length}",
            "",
            ""
        ]
        s.send('\r\n'.join(request).encode('utf-8'))
        s.send(header_part)
        
        # Kirim isi file
        with open(filename, 'rb') as f:
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                s.send(chunk)
        
        s.send(footer_part)
        
        # Terima respon server
        response = s.recv(1024).decode('utf-8')
        print("Respon server:", response)
        if "200 OK" in response:
            print("File berhasil dikirim:", filename_base)
            show_oled_message("Terkirim!", filename_base)
        else:
            raise Exception("Error dari server")
    except Exception as e:
        print("Pengiriman gagal:", e)
        show_oled_message("Gagal kirim!", str(e))
    finally:
        if s:
            s.close()

# === Finalisasi Rekaman ===
def finalize_recording(file_handle, samples, filename):
    try:
        file_handle.flush()
        file_handle.seek(0)   # Pindah ke awal file
        file_handle.write(create_wav_header(SAMPLE_RATE, BITS, CHANNELS, samples)) # Update header WAV
        file_handle.close()
        print("Rekaman disimpan:", filename)
        return True
    except Exception as e:
        print("Gagal simpan:", e)
        show_oled_message("Gagal simpan!", str(e))
        try:
            file_handle.close()
        except:
            pass
        return False

# === Program Utama ===
try:
    connect_wifi(WIFI_SSID, WIFI_PASSWORD)  # Hubungkan ke WiFi
    mount_sd()                              # Mount SD card
except Exception as e:
    print("Gagal saat startup:", e)
    show_oled_message("Startup gagal", str(e))
    while True:
        time.sleep(1)                       # Jika gagal, berhenti di loop

# === Variabel kontrol ===
is_recording = False
record_file = None
samples_recorded = 0
start_time = 0

print("Tekan tombol untuk mulai")
show_oled_message("Siap", "Tekan tombol...")

# === Loop utama ===
while True:
    if button.value() == 0:  # Tombol ditekan
        time.sleep(0.2)      # Debounce 200ms
        if not is_recording:
            filename = get_filename()
            print("Mulai merekam:", filename)
            wlan.active(False)  # Matikan WiFi untuk kestabilan I2S + SD
            led.on()
            time.sleep(0.5)  # Delay agar SD siap
            try:
                record_file = open(filename, "wb")
                record_file.write(create_wav_header(SAMPLE_RATE, BITS, CHANNELS, 0)) # Header dummy
                samples_recorded = 0
                start_time = time.ticks_ms()
                is_recording = True
            except Exception as e:
                print("Gagal mulai rekaman:", e)
                show_oled_message("Error SD!", str(e))
                led.off()
        else:
            print("Menghentikan rekaman...")
            is_recording = False
            led.off()
            if finalize_recording(record_file, samples_recorded, filename):
                wlan.active(True)             # Aktifkan WiFi kembali
                time.sleep(1)
                connect_wifi(WIFI_SSID, WIFI_PASSWORD)
                send_to_server(filename)      # Upload file
        
        # Tunggu tombol dilepas
        while button.value() == 0:
            time.sleep(0.05)

    if is_recording:
        elapsed_seconds = (time.ticks_ms() - start_time) // 1000
        if elapsed_seconds >= MAX_RECORD_SECONDS:
            print("Waktu rekam habis!")
            is_recording = False
            led.off()
            if finalize_recording(record_file, samples_recorded, filename):
                wlan.active(True)
                time.sleep(1)
                connect_wifi(WIFI_SSID, WIFI_PASSWORD)
                send_to_server(filename)
            continue
        
        show_recording_progress(elapsed_seconds)
        
        try:
            raw_buffer = bytearray(BUFFER_SIZE)
            num_bytes = i2s.readinto(raw_buffer)  # Membaca data audio dari mikrofon
            if num_bytes:
                record_file.write(raw_buffer[:num_bytes])
                samples_recorded += num_bytes // 2   # Karena 16 bit per sample
        except Exception as e:
            print("Error saat merekam:", e)
            is_recording = False
            led.off()
            if finalize_recording(record_file, samples_recorded, filename):
                wlan.active(True)
                time.sleep(1)
                connect_wifi(WIFI_SSID, WIFI_PASSWORD)
                send_to_server(filename)
            show_oled_message("Error rekam!", str(e))

