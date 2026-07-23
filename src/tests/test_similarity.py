import cv2
import numpy as np
import os
import sys
import onnxruntime as ort
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from modules.cleaner.logic_scrfd import SCRFD

def get_feature(img_url, detector, arcface_session):
    try:
        req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req)
        arr = np.asarray(bytearray(response.read()), dtype=np.uint8)
        img = cv2.imdecode(arr, -1)
    except Exception as e:
        print(f"Failed to load {img_url}: {e}")
        return None
        
    bboxes, kpss = detector.detect(img, input_size=(320, 320))
    if len(bboxes) == 0: return None
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

def test_similarity():
    scrfd_path = os.path.expanduser('~/.mediakeeper/models/det_10g.onnx')
    arcface_path = os.path.expanduser('~/.mediakeeper/models/w600k_r50.onnx')
    
    detector = SCRFD(scrfd_path)
    arcface_session = ort.InferenceSession(arcface_path, providers=['CPUExecutionProvider'])
    
    # Let's get some faces
    urls = [
        "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c1/Lionel_Messi_20180626.jpg/220px-Lionel_Messi_20180626.jpg", # Messi
        "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ae/Michael_Jordan_in_2014.jpg/220px-Michael_Jordan_in_2014.jpg", # Jordan
        "https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/Mark_Zuckerberg_F8_2019_Keynote_%2832830578717%29_%28cropped%29.jpg/220px-Mark_Zuckerberg_F8_2019_Keynote_%2832830578717%29_%28cropped%29.jpg", # Zuckerberg
        "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b4/Angelina_Jolie_2_June_2014_%28cropped%29.jpg/220px-Angelina_Jolie_2_June_2014_%28cropped%29.jpg", # Angelina Jolie
        "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/Scarlett_Johansson_2019.jpg/220px-Scarlett_Johansson_2019.jpg", # Scarlett Johansson
        "https://upload.wikimedia.org/wikipedia/commons/thumb/3/37/Margot_Robbie_at_Somerset_House_in_2013_%28cropped%29.jpg/220px-Margot_Robbie_at_Somerset_House_in_2013_%28cropped%29.jpg" # Margot Robbie
    ]
    
    feats = []
    for u in urls:
        f = get_feature(u, detector, arcface_session)
        if f is not None:
            feats.append(f)
        else:
            print("Failed to get face for", u)
            
    print(f"Extracted {len(feats)} features")
    for i in range(len(feats)):
        for j in range(i+1, len(feats)):
            sim = np.dot(feats[i], feats[j])
            print(f"Face {i} vs Face {j}: {sim:.3f}")
            
    # Average of Jolie, Johansson, Robbie
    if len(feats) == 6:
        avg_female = np.mean(feats[3:], axis=0)
        avg_female = avg_female / np.linalg.norm(avg_female)
        
        for i in range(3):
            sim = np.dot(avg_female, feats[i])
            print(f"Avg Female vs Male {i}: {sim:.3f}")

if __name__ == '__main__':
    test_similarity()
