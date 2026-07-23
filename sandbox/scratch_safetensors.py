import os
import urllib.request
from safetensors.numpy import load_file
import onnxruntime as ort
import numpy as np

def download(url, path):
    if not os.path.exists(path):
        print(f"Downloading {url} to {path}...")
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(path, 'wb') as out_file:
            out_file.write(response.read())

dense_path = "scratch/models/clip_text_multi/dense.safetensors"
download("https://huggingface.co/sentence-transformers/clip-ViT-B-32-multilingual-v1/resolve/main/2_Dense/model.safetensors", dense_path)

# Load the weights
weights = load_file(dense_path)
print("Keys:", weights.keys())
print("Weight shape:", weights['linear.weight'].shape)
if 'linear.bias' in weights:
    print("Bias shape:", weights['linear.bias'].shape)
