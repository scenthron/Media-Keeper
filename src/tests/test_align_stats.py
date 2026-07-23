import cv2
import numpy as np
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from modules.cleaner.logic_scrfd import SCRFD

def save_aligned():
    scrfd_path = os.path.expanduser('~/.mediakeeper/models/det_10g.onnx')
    detector = SCRFD(scrfd_path)
    
    img = cv2.imread("lena.jpg")
    bboxes, kpss = detector.detect(img, input_size=(320, 320))
    largest_idx = np.argmax((bboxes[:, 2] - bboxes[:, 0]) * (bboxes[:, 3] - bboxes[:, 1]))
    kps = kpss[largest_idx]
    
    arcface_dst = np.array([
        [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
        [41.5493, 92.3655], [70.7299, 92.2041]
    ], dtype=np.float32)
    
    tform = cv2.estimateAffinePartial2D(kps, arcface_dst)[0]
    aligned_face = cv2.warpAffine(img, tform, (112, 112))
    
    cv2.imwrite("aligned_lena.jpg", aligned_face)
    
    # Let's print some stats about aligned_face to see if it's completely black
    print(f"Shape: {aligned_face.shape}")
    print(f"Mean: {aligned_face.mean()}")
    print(f"Std: {aligned_face.std()}")
    print(f"Min: {aligned_face.min()}, Max: {aligned_face.max()}")

if __name__ == '__main__':
    save_aligned()
