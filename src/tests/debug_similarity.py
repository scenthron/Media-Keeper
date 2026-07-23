import cv2
import numpy as np
import os
import sys
import onnxruntime as ort

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from modules.cleaner.logic_scrfd import SCRFD

def get_face_feature(img_path, detector, arcface_session):
    img = cv2.imread(img_path)
    if img is None:
        print(f"[{os.path.basename(img_path)}] ERROR: Could not read image.")
        return None
        
    bboxes, kpss = detector.detect(img, input_size=(320, 320))
    if bboxes.shape[0] == 0:
        print(f"[{os.path.basename(img_path)}] ERROR: No face detected.")
        return None
        
    largest_idx = np.argmax((bboxes[:, 2] - bboxes[:, 0]) * (bboxes[:, 3] - bboxes[:, 1]))
    kps = kpss[largest_idx]
    
    # Save a debug image with the keypoints drawn
    debug_img = img.copy()
    for kp in kps:
        cv2.circle(debug_img, (int(kp[0]), int(kp[1])), 2, (0, 255, 0), -1)
    
    arcface_dst = np.array([
        [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
        [41.5493, 92.3655], [70.7299, 92.2041]
    ], dtype=np.float32)
    
    tform = cv2.estimateAffinePartial2D(kps, arcface_dst, method=cv2.LMEDS)[0]
    if tform is None:
        print(f"[{os.path.basename(img_path)}] ERROR: Affine transform failed.")
        return None
        
    aligned_face = cv2.warpAffine(img, tform, (112, 112))
    cv2.imwrite(f"debug_aligned_{os.path.basename(img_path)}", aligned_face)
    cv2.imwrite(f"debug_kps_{os.path.basename(img_path)}", debug_img)
    
    input_name = arcface_session.get_inputs()[0].name
    blob = cv2.dnn.blobFromImage(aligned_face, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
    feature = arcface_session.run(None, {input_name: blob})[0][0]
    feature = feature / np.linalg.norm(feature)
    
    print(f"[{os.path.basename(img_path)}] SUCCESS: Feature extracted.")
    return feature

def main():
    if len(sys.argv) < 3:
        print("Usage: python debug_similarity.py <reference_folder> <target_folder>")
        return
        
    ref_dir = sys.argv[1]
    target_dir = sys.argv[2]
    
    scrfd_path = os.path.expanduser('~/.mediakeeper/models/det_10g.onnx')
    arcface_path = os.path.expanduser('~/.mediakeeper/models/w600k_r50.onnx')
    
    detector = SCRFD(scrfd_path)
    arcface_session = ort.InferenceSession(arcface_path, providers=['CPUExecutionProvider'])
    
    print(f"Loading reference images from {ref_dir}...")
    ref_features = []
    for f in os.listdir(ref_dir):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            feat = get_face_feature(os.path.join(ref_dir, f), detector, arcface_session)
            if feat is not None:
                ref_features.append(feat)
                
    if not ref_features:
        print("CRITICAL ERROR: No valid faces found in reference folder.")
        return
        
    avg_ref = np.mean(ref_features, axis=0)
    avg_ref = avg_ref / np.linalg.norm(avg_ref)
    
    print(f"\nComparing target images in {target_dir} against average reference...")
    for f in os.listdir(target_dir):
        if f.lower().endswith(('.jpg', '.jpeg', '.png')):
            feat = get_face_feature(os.path.join(target_dir, f), detector, arcface_session)
            if feat is not None:
                score_raw = np.dot(avg_ref, feat)
                mapped_score = (score_raw - 0.55) / (0.85 - 0.55) * 100
                mapped_score = max(0, min(100, mapped_score))
                print(f"RESULT: {f} -> Raw Score: {score_raw:.4f}, Mapped: {mapped_score:.1f}%")

if __name__ == '__main__':
    main()
