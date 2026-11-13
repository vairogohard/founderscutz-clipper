"""Spraak naar tekst met tijd per woord (faster-whisper, draait gratis op de CPU).

Het geluid halen we zelf met ffmpeg uit de video en geven we als getallenreeks door. Zo gebruikt
faster-whisper zijn eigen audiolezer (PyAV) niet, die bij nieuwe versies weleens breekt."""
import subprocess
import wave
from pathlib import Path

import numpy as np


def extract_audio(video_path, workdir, max_minutes):
    wav = Path(workdir) / "audio.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
                    "-t", str(int(max_minutes * 60)), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(wav)], check=True)
    return wav


def load_wav(wav):
    with wave.open(str(wav), "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def transcribe(video_path, workdir, model_name="base.en", max_minutes=75):
    from faster_whisper import WhisperModel

    try:
        audio = load_wav(extract_audio(video_path, workdir, max_minutes))
    except subprocess.CalledProcessError:
        print("Geen geluidsspoor gevonden; verder zonder ondertitels.")
        return []
    if audio.size < 16000 * 0.5:
        return []
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(audio, word_timestamps=True, vad_filter=True, beam_size=1)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"start": float(w.start), "end": float(w.end), "word": text})
    return words
