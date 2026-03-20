import re

path = r'c:\67160005\Panya\backend\main.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Upgrade model to small.en
old_model = re.compile(r'app\.state\.whisper_model\s*=\s*WhisperModel\([\s\S]*?download_root=model_cache_dir\s*\)', re.MULTILINE)
new_model = """app.state.whisper_model = WhisperModel(
                "small.en",        # 244M params - robust to accents without crushing CPU
                device="auto",     
                compute_type="int8", # Essential for CPU speed
                cpu_threads=4,       # Prevent context-switching latency
                download_root=model_cache_dir
            )"""
content = old_model.sub(new_model, content, count=1)

content = content.replace('logger.info("🎤 Loading Whisper model (base.en with int8)...")', 'logger.info("🎤 Loading Whisper model (small.en with int8, threads=4, no VAD)...")')

# 2. Upgrade transcription settings
old_transcribe = re.compile(r'segments, _ = app\.state\.whisper_model\.transcribe\([\s\S]*?vad_parameters=dict\(min_silence_duration_ms=500\)\s*\)', re.MULTILINE)
new_transcribe = """segments, _ = app.state.whisper_model.transcribe(
            tmp_path,
            language="en",
            beam_size=5,          # Better beam search helps fix broken accents programmatically
            condition_on_previous_text=False,
            initial_prompt="A technical engineering conversation about Mitsubishi PLC automation, hardware modules, cables, networking, Q-series and clear English.",
            vad_filter=False      # Disabled VAD to remove the 2-3 second initialization latency on CPUs
        )"""
content = old_transcribe.sub(new_transcribe, content, count=1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Accent & Latency Patch successful!")
