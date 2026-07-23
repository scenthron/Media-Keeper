import os
import onnxruntime as ort
import numpy as np
import cv2
from safetensors.numpy import load_file
from transformers import AutoTokenizer

text_model_path = "scratch/models/clip_text_multi/model.onnx"
vision_model_path = "scratch/models/clip_vision/model.onnx"
dense_path = "scratch/models/clip_text_multi/dense.safetensors"

tokenizer = AutoTokenizer.from_pretrained('scratch/models/clip_text_multi')
text_sess = ort.InferenceSession(text_model_path, providers=['CPUExecutionProvider'])
vision_sess = ort.InferenceSession(vision_model_path, providers=['CPUExecutionProvider'])
dense_weights = load_file(dense_path)['linear.weight'] # (512, 768)

def mean_pooling(model_output, attention_mask):
    input_mask_expanded = np.expand_dims(attention_mask, -1)
    input_mask_expanded = np.broadcast_to(input_mask_expanded, model_output.shape)
    sum_embeddings = np.sum(model_output * input_mask_expanded, axis=1)
    sum_mask = np.clip(np.sum(input_mask_expanded, axis=1), a_min=1e-9, a_max=None)
    return sum_embeddings / sum_mask

# 1. ENCODE TEXT
inputs = tokenizer(["красная машина", "девушка", "собака", "Киану Ривз", "мужчина в костюме"], padding=True, truncation=True, return_tensors="np")
text_out = text_sess.run(None, {
    "input_ids": inputs["input_ids"].astype(np.int64),
    "attention_mask": inputs["attention_mask"].astype(np.int64)
})[0]
text_emb_768 = mean_pooling(text_out, inputs["attention_mask"].astype(np.int64))

# Project to 512 and Normalize
text_emb_512 = np.dot(text_emb_768, dense_weights.T)
text_emb = text_emb_512 / np.linalg.norm(text_emb_512, axis=-1, keepdims=True)

# 2. ENCODE IMAGE
# Preprocessing for CLIP-ViT-B/32
def preprocess_image(img_path):
    img = cv2.imread(img_path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Resize keeping aspect ratio, short edge to 224
    h, w = img.shape[:2]
    scale = max(224.0 / h, 224.0 / w)
    new_h, new_w = int(np.ceil(h * scale)), int(np.ceil(w * scale))
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    
    # Center crop 224x224
    start_y = (new_h - 224) // 2
    start_x = (new_w - 224) // 2
    img = img[start_y:start_y+224, start_x:start_x+224]
    
    img = img.astype(np.float32) / 255.0
    
    mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
    std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
    img = (img - mean) / std
    
    img = np.transpose(img, (2, 0, 1))
    img = np.expand_dims(img, axis=0)
    return img.astype(np.float32)

img_input = preprocess_image("C:/Users/Centhron/Desktop/Reference/1000x745_0xac120003_17550086621567090673.jpg")

vision_out = vision_sess.run(None, {"pixel_values": img_input})[0]
# The output is [batch, 512] for pooled output!
img_emb = vision_out / np.linalg.norm(vision_out, axis=-1, keepdims=True)

print("Vision output shape:", vision_out.shape)
print("--- Similarity to Image (Keanu Reeves) ---")
print("красная машина:", np.dot(text_emb[0], img_emb[0]))
print("девушка:", np.dot(text_emb[1], img_emb[0]))
print("собака:", np.dot(text_emb[2], img_emb[0]))
print("Киану Ривз:", np.dot(text_emb[3], img_emb[0]))
print("мужчина в костюме:", np.dot(text_emb[4], img_emb[0]))
