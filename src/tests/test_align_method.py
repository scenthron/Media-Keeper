import cv2
import numpy as np

def test():
    kps = np.arange(10, dtype=np.float32)
    dst = np.zeros((5, 2), dtype=np.float32)
    try:
        cv2.estimateAffinePartial2D(kps, dst)
        print("Accepted (10,)")
    except Exception as e:
        print("Failed (10,):", e)
        
    try:
        cv2.estimateAffinePartial2D(kps.reshape(5,2), dst)
        print("Accepted (5,2)")
    except Exception as e:
        print("Failed (5,2):", e)

if __name__ == '__main__':
    test()
