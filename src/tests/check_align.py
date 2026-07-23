import cv2
import numpy as np
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from modules.cleaner.logic_scrfd import SCRFD

def check_aligned_face():
    scrfd_path = os.path.expanduser('~/.mediakeeper/models/det_10g.onnx')
    detector = SCRFD(scrfd_path)
    
    img = cv2.imread("aligned_lena.jpg")
    bboxes, kpss = detector.detect(img, input_size=(320, 320), conf_thresh=0.3)
    
    print(f"Detected {len(bboxes)} faces in aligned_lena.jpg")
    if len(bboxes) > 0:
        print(f"Bbox: {bboxes[0]}")

if __name__ == '__main__':
    check_aligned_face()
