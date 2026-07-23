import cv2
import numpy as np
import os
import onnxruntime as ort

def test_scrfd_shapes():
    model_path = os.path.expanduser('~/.mediakeeper/models/det_10g.onnx')
    session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
    
    input_name = session.get_inputs()[0].name
    det_img = np.zeros((1, 3, 640, 640), dtype=np.float32)
    net_outs = session.run(None, {input_name : det_img})
    
    for i, out in enumerate(net_outs):
        print(f"Output {i}: {out.shape}")
    
if __name__ == '__main__':
    test_scrfd_shapes()
