from machine import I2S, Pin, I2C
import ustruct
import time
import uos
import ssd1306 #Library untuk OLED

# === OLED SSD1306 ===
i2c = I2C(scl=Pin(22), sda=Pin(21))  # sesuaikan jika perlu
oled = ssd1306.SSD1306_I2C(128, 64, i2c)  # ✅ ini sudah benar

def show_oled_message(line1="", line2=""):
    oled.fill(0)
    oled.text(line1, 0, 0)
    oled.text(line2, 0, 10)
    oled.show()

# === KONFIG I2S untuk INMP441 ===
i2s = I2S(
    0,
    sck=Pin(14),
    ws=Pin(15),
    sd=Pin(32),
    mode=I2S.RX,
    bits=16,
    format=I2S.MONO,
    rate=16000,
    ibuf=8000
)

# === TOMBOL & LED ===
button = Pin(13, Pin.IN, Pin.PULL_UP)
led = Pin(2, Pin.OUT)
led.off()

# === PARAMETER REKAMAN ===
DURATION_SECONDS = 5
SAMPLE_RATE = 16000
BITS = 16
CHANNELS = 1
BUFFER_SIZE = 1024
TOTAL_SAMPLES = SAMPLE_RATE * DURATION_SECONDS
filename = "recorded.wav"

# === HEADER WAV ===
def create_wav_header(sample_rate, bits_per_sample, num_channels, num_samples):
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * num_channels * bits_per_sample // 8
    header = b'RIFF'
    header += ustruct.pack('<I', 36 + data_size)
    header += b'WAVEfmt '
    header += ustruct.pack('<I', 16)
    header += ustruct.pack('<H', 1)
    header += ustruct.pack('<H', num_channels)
    header += ustruct.pack('<I', sample_rate)
    header += ustruct.pack('<I', byte_rate)
    header += ustruct.pack('<H', block_align)
    header += ustruct.pack('<H', bits_per_sample)
    header += b'data'
    header += ustruct.pack('<I', data_size)
    return header

# === FUNGSI REKAMAN ===
def record_audio():
    print("🎙 Merekam...")
    show_oled_message("🎙 Merekam...", "Tunggu 5 detik")
    led.on()

    with open(filename, "wb") as f:
        wav_header = create_wav_header(SAMPLE_RATE, BITS, CHANNELS, TOTAL_SAMPLES)
        f.write(wav_header)

        samples_recorded = 0
        buffer = bytearray(BUFFER_SIZE)
        while samples_recorded < TOTAL_SAMPLES:
            num_bytes = i2s.readinto(buffer)
            if num_bytes:
                f.write(buffer[:num_bytes])
                samples_recorded += num_bytes // 2

    print("✅ Selesai merekam:", filename)
    show_oled_message("✅ Rekaman selesai", "Disimpan lokal")
    led.off()

# === LOOP UTAMA ===
print("📲 Tekan tombol untuk mulai")
show_oled_message("Siap merekam", "Tekan tombol...")

while True:
    if button.value() == 0:
        print("🟢 Tombol ditekan!")
        time.sleep(0.2)  # debounce
        record_audio()
        show_oled_message("🔁 Tekan lagi", "Untuk rekaman baru")
        print("🕹 Tunggu tombol dilepas...")
        while button.value() == 0:
            time.sleep(0.1)
    time.sleep(0.1)
