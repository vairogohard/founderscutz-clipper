"""Spraak naar tekst met tijd per woord (faster-whisper, draait gratis op de CPU)."""
import subprocess
from pathlib import Path


def extract_audio(video_path, workdir, max_minutes):
    wav = Path(workdir) / "audio.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
                    "-t", str(int(max_minutes * 60)), "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                   check=True)
    return wav


def transcribe(video_path, workdir, model_name="base.en", max_minutes=75):
    from faster_whisper import WhisperModel

    wav = extract_audio(video_path, workdir, max_minutes)
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(wav), word_timestamps=True, vad_filter=True, beam_size=1)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"start": float(w.start), "end": float(w.end), "word": text})
    return words
