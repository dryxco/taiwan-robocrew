"""Download the optional upstream MediaPipe model for local webcam tracking."""
from pathlib import Path
from urllib.request import urlretrieve

URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
path = Path(__file__).resolve().parents[1] / 'public/models/hand_landmarker.task'
path.parent.mkdir(parents=True, exist_ok=True)
urlretrieve(URL, path)
print(path)
