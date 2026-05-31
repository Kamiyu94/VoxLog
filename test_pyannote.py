from pyannote.audio import Pipeline
p = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token="YOUR_HF_TOKEN")
print("成功")
