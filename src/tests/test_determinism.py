import cv2
import numpy as np
import os
import sys
import onnxruntime as ort

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from modules.cleaner.logic_scrfd import SCRFD

def main():
    img_path = sys.argv[1]
    detector = SCRFD(os.path.expanduser('~/.mediakeeper/models/det_10g.onnx'))
    arcface_session = ort.InferenceSession(os.path.expanduser('~/.mediakeeper/models/w600k_r50.onnx'), providers=['CPUExecutionProvider'])
    
    img = cv2.imread(img_path)
    bboxes, kpss = detector.detect(img, input_size=(320, 320))
    largest_idx = np.argmax((bboxes[:, 2] - bboxes[:, 0]) * (bboxes[:, 3] - bboxes[:, 1]))
    kps = kpss[largest_idx]
    
    arcface_dst = np.array([
        [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
        [41.5493, 92.3655], [70.7299, 92.2041]
    ], dtype=np.float32)
    
    # Test deterministic affine
    for i in range(5):
        tform = cv2.estimateAffinePartial2D(kps, arcface_dst, method=cv2.LMEDS)[0]
        aligned_face = cv2.warpAffine(img, tform, (112, 112))
        blob = cv2.dnn.blobFromImage(aligned_face, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        feat = arcface_session.run(None, {arcface_session.get_inputs()[0].name: blob})[0][0]
        feat = feat / np.linalg.norm(feat)
        print(f"Run {i} feat sum:", feat.sum())

if __name__ == '__main__':
    main()
