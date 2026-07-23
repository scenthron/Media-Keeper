import os
os.environ['TOKENIZERS_PARALLELISM']='false'
os.environ['TRANSFORMERS_VERBOSITY']='error'
import sys
sys.path.append('src')

print("1. import onnxruntime", flush=True)
import onnxruntime as ort
print("2. get paths", flush=True)
from logic_paths import get_models_dir
clip_dir = os.path.join(get_models_dir(), "clip")
vision_model_path = os.path.join(clip_dir, "vision", "model.onnx")
text_model_dir = os.path.join(clip_dir, "text_multi")
text_model_path = os.path.join(text_model_dir, "model.onnx")

print("3. opts", flush=True)
opts = ort.SessionOptions()
opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

print("4. vision", flush=True)
vision_sess = ort.InferenceSession(vision_model_path, sess_options=opts, providers=['CPUExecutionProvider'])
print("5. text", flush=True)
text_sess = ort.InferenceSession(text_model_path, sess_options=opts, providers=['CPUExecutionProvider'])

print("6. import AutoTokenizer", flush=True)
from transformers import AutoTokenizer
print("7. tokenizer", flush=True)
tokenizer = AutoTokenizer.from_pretrained(text_model_dir, local_files_only=True)

print("8. done", flush=True)
