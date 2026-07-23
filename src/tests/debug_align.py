import cv2
import numpy as np
import os
import onnxruntime as ort
import sys

# add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from modules.cleaner.logic_scrfd import SCRFD

def debug_alignment():
    scrfd_path = os.path.expanduser('~/.mediakeeper/models/det_10g.onnx')
    detector = SCRFD(scrfd_path)
    
    # create a dummy image or use a real one
    # let's download a test image of a face
    import urllib.request
    urllib.request.urlretrieve("https://raw.githubusercontent.com/opencv/opencv/master/samples/data/lena.jpg", "lena.jpg")
    img = cv2.imread("lena.jpg")
    
    bboxes, kpss = detector.detect(img, input_size=(320, 320))
    if len(bboxes) == 0:
        print("No face found")
        return
        
    largest_idx = np.argmax((bboxes[:, 2] - bboxes[:, 0]) * (bboxes[:, 3] - bboxes[:, 1]))
    kps = kpss[largest_idx]
    
    arcface_dst = np.array([
        [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
        [41.5493, 92.3655], [70.7299, 92.2041]
    ], dtype=np.float32)
    
    tform = cv2.estimateAffinePartial2D(kps, arcface_dst)[0]
    aligned_face = cv2.warpAffine(img, tform, (112, 112))
    cv2.imwrite("aligned_lena.jpg", aligned_face)
    
    # draw kps
    for i in range(5):
        cv2.circle(img, (int(kps[i][0]), int(kps[i][1])), 2, (0, 0, 255), -1)
    cv2.imwrite("kps_lena.jpg", img)
    print("Done. Check aligned_lena.jpg and kps_lena.jpg")

if __name__ == '__main__':
    debug_alignment()
