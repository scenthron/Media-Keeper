import sys
import os
import numpy as np
sys.path.append('src')
from logic_paths import get_models_dir
import onnxruntime as ort

clip_dir = os.path.join(get_models_dir(), "clip")
text_model_dir = os.path.join(clip_dir, "text_multi")
text_model_path = os.path.join(text_model_dir, "model.onnx")

sess = ort.InferenceSession(text_model_path, providers=['CPUExecutionProvider'])

def get_emb(input_ids, attention_mask):
    text_out = sess.run(None, {
        "input_ids": input_ids,
        "attention_mask": attention_mask
    })[0]
    if len(text_out.shape) == 3:
        mask_expanded = np.expand_dims(attention_mask, -1)
        sum_embeddings = np.sum(text_out * mask_expanded, axis=1)
        sum_mask = np.clip(np.sum(mask_expanded, axis=1), a_min=1e-9, a_max=None)
        text_out = sum_embeddings / sum_mask
    text_out = text_out / np.linalg.norm(text_out, axis=-1, keepdims=True)
    return text_out[0]

# 1. Without padding (like Transformers padding=True for single text)
from tokenizers import Tokenizer
t = Tokenizer.from_file(os.path.join(text_model_dir, "tokenizer.json"))
enc = t.encode("собака")
emb1 = get_emb(np.array([enc.ids], dtype=np.int64), np.array([enc.attention_mask], dtype=np.int64))

# 2. With padding to 77
t.enable_padding(length=77)
enc2 = t.encode("собака")
emb2 = get_emb(np.array([enc2.ids], dtype=np.int64), np.array([enc2.attention_mask], dtype=np.int64))

print("Diff padding:", np.linalg.norm(emb1 - emb2))
print("Sim:", np.dot(emb1, emb2))
