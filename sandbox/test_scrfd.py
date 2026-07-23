import cv2
import numpy as np
import os
from modules.cleaner.logic_scrfd import SCRFD

def test_scrfd():
    model_path = os.path.expanduser('~/.mediakeeper/models/det_10g.onnx')
    print("Loading SCRFD:", model_path)
    detector = SCRFD(model_path)
    
    # Fake image
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    bboxes, kpss = detector.detect(img)
    
    print("Detected bboxes:", bboxes.shape)
    print("Detected kpss:", kpss.shape)
    
if __name__ == '__main__':
    test_scrfd()
