import os
import urllib.request
import zipfile
import onnxruntime as ort
import numpy as np
import cv2
import json

text_model_path = "scratch/models/clip_text_multi/model.onnx"
vision_model_path = "scratch/models/clip_vision/model.onnx"

try:
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained('scratch/models/clip_text_multi')
    print("Tokenizer loaded!")
except Exception as e:
    print(f"Tokenizer error: {e}")

try:
    text_sess = ort.InferenceSession(text_model_path, providers=['CPUExecutionProvider'])
    print("ONNX sessions loaded!")
except Exception as e:
    print(f"ONNX error: {e}")

# Mean Pooling - Take attention mask into account for correct averaging
def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output
    input_mask_expanded = np.expand_dims(attention_mask, -1)
    input_mask_expanded = np.broadcast_to(input_mask_expanded, token_embeddings.shape)
    sum_embeddings = np.sum(token_embeddings * input_mask_expanded, axis=1)
    sum_mask = np.clip(np.sum(input_mask_expanded, axis=1), a_min=1e-9, a_max=None)
    return sum_embeddings / sum_mask

# Try encoding text
try:
    inputs = tokenizer(["красная машина", "red car", "собака", "черный кот", "кот"], padding=True, truncation=True, return_tensors="np")
    text_out = text_sess.run(None, {
        "input_ids": inputs["input_ids"].astype(np.int64),
        "attention_mask": inputs["attention_mask"].astype(np.int64)
    })[0]
    
    text_emb = mean_pooling(text_out, inputs["attention_mask"].astype(np.int64))
    
    # L2 normalize
    text_emb = text_emb / np.linalg.norm(text_emb, axis=-1, keepdims=True)
    print("Text embeddings shape:", text_emb.shape)
    
    print("Sim 'красная машина' vs 'red car':", np.dot(text_emb[0], text_emb[1]))
    print("Sim 'красная машина' vs 'собака':", np.dot(text_emb[0], text_emb[2]))
    print("Sim 'собака' vs 'черный кот':", np.dot(text_emb[2], text_emb[3]))
    print("Sim 'черный кот' vs 'кот':", np.dot(text_emb[3], text_emb[4]))
except Exception as e:
    print(f"Encode error: {e}")
