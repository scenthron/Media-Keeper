import cv2
import numpy as np
import onnxruntime as ort
import os

def test_arcface():
    img = np.zeros((320, 320, 3), dtype=np.uint8)
    
    # Just to check if onnxruntime can load w600k_r50.onnx
    model_path = os.path.expanduser('~/.mediakeeper/models/w600k_r50.onnx')
    print("Loading:", model_path)
    session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    
    input_name = session.get_inputs()[0].name
    input_shape = session.get_inputs()[0].shape
    print("Input shape:", input_shape)
    
    # Create fake aligned face 112x112
    face = np.zeros((112, 112, 3), dtype=np.uint8)
    
    # ArcFace preprocess:
    # (x / 127.5) - 1.0, RGB format, NCHW
    blob = cv2.dnn.blobFromImage(face, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
    
    out = session.run(None, {input_name: blob})[0]
    print("Output shape:", out.shape)
    
if __name__ == '__main__':
    test_arcface()
