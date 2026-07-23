import cv2
import numpy as np
import os
import sys
import onnxruntime as ort

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from modules.cleaner.logic_scrfd import SCRFD

def get_face_feature(img_path, detector, arcface_session):
    img = cv2.imread(img_path)
    if img is None: return None
    bboxes, kpss = detector.detect(img, input_size=(320, 320))
    if bboxes.shape[0] == 0: return None
    largest_idx = np.argmax((bboxes[:, 2] - bboxes[:, 0]) * (bboxes[:, 3] - bboxes[:, 1]))
    kps = kpss[largest_idx]
    arcface_dst = np.array([
        [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
        [41.5493, 92.3655], [70.7299, 92.2041]
    ], dtype=np.float32)
    tform = cv2.estimateAffinePartial2D(kps, arcface_dst, method=cv2.LMEDS)[0]
    if tform is None: return None
    aligned_face = cv2.warpAffine(img, tform, (112, 112))
    input_name = arcface_session.get_inputs()[0].name
    blob = cv2.dnn.blobFromImage(aligned_face, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
    feature = arcface_session.run(None, {input_name: blob})[0][0]
    feature = feature / np.linalg.norm(feature)
    return feature

def main():
    ref_dir = sys.argv[1]
    target_dir = sys.argv[2]
    
    detector = SCRFD(os.path.expanduser('~/.mediakeeper/models/det_10g.onnx'))
    arcface_session = ort.InferenceSession(os.path.expanduser('~/.mediakeeper/models/w600k_r50.onnx'), providers=['CPUExecutionProvider'])
    
    refs = {}
    for f in os.listdir(ref_dir):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            feat = get_face_feature(os.path.join(ref_dir, f), detector, arcface_session)
            if feat is not None: refs[f] = feat
                
    for tf in os.listdir(target_dir):
        if tf.lower().endswith(('.jpg', '.jpeg', '.png')):
            feat = get_face_feature(os.path.join(target_dir, tf), detector, arcface_session)
            if feat is not None:
                print(f"\n--- Target: {tf} ---")
                for rf, rfeat in refs.items():
                    sim = np.dot(rfeat, feat)
                    print(f"  vs {rf}: {sim:.4f}")

if __name__ == '__main__':
    main()
