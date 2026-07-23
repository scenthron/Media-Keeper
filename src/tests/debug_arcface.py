import onnxruntime as ort
import os

model_path = os.path.expanduser('~/.mediakeeper/models/w600k_r50.onnx')
session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
print("Inputs:")
for i in session.get_inputs():
    print(f"{i.name}: {i.shape} {i.type}")
print("Outputs:")
for o in session.get_outputs():
    print(f"{o.name}: {o.shape} {o.type}")
