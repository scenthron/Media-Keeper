import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import numpy as np
import cv2
import onnxruntime as ort

def distance2bbox(points, distance, max_shape=None):
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    if max_shape is not None:
        x1 = np.clip(x1, 0, max_shape[1])
        y1 = np.clip(y1, 0, max_shape[0])
        x2 = np.clip(x2, 0, max_shape[1])
        y2 = np.clip(y2, 0, max_shape[0])
    return np.column_stack([x1, y1, x2, y2])

def distance2kps(points, distance, max_shape=None):
    preds = []
    for i in range(0, distance.shape[1], 2):
        px = points[:, i%2] + distance[:, i]
        py = points[:, i%2+1] + distance[:, i+1]
        if max_shape is not None:
            px = np.clip(px, 0, max_shape[1])
            py = np.clip(py, 0, max_shape[0])
        preds.append(px)
        preds.append(py)
    return np.column_stack(preds).reshape(-1, 5, 2)

class SCRFD:
    def __init__(self, model_file):
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        self.session = ort.InferenceSession(model_file, sess_options=opts, providers=['CPUExecutionProvider'])
        self.input_name = self.session.get_inputs()[0].name
        self._feat_stride_fpn = [8, 16, 32]
        self._num_anchors = 2
        
    def detect(self, img, input_size=(640, 640), conf_thresh=0.5, nms_thresh=0.4):
        im_ratio = float(img.shape[0]) / img.shape[1]
        model_ratio = float(input_size[1]) / input_size[0]
        if im_ratio > model_ratio:
            new_height = input_size[1]
            new_width = int(new_height / im_ratio)
        else:
            new_width = input_size[0]
            new_height = int(new_width * im_ratio)
        det_scale = float(new_height) / img.shape[0]
        resized_img = cv2.resize(img, (new_width, new_height))
        det_img = np.zeros((input_size[1], input_size[0], 3), dtype=np.uint8)
        det_img[:new_height, :new_width, :] = resized_img
        
        blob = cv2.dnn.blobFromImage(det_img, 1.0/128.0, input_size, (127.5, 127.5, 127.5), swapRB=True)
        blob = np.ascontiguousarray(blob, dtype=np.float32)
        net_outs = self.session.run(None, {self.input_name : blob})
        
        scores_list = []
        bboxes_list = []
        kpss_list = []
        
        for idx, stride in enumerate(self._feat_stride_fpn):
            scores = net_outs[idx]
            bbox_preds = net_outs[idx+3]
            kps_preds = net_outs[idx+6]
            
            # Since shape is (N, 1), (N, 4), (N, 10), we can deduce feature map size
            # N = height * width * num_anchors
            feat_h = input_size[1] // stride
            feat_w = input_size[0] // stride
            
            y, x = np.mgrid[0:feat_h, 0:feat_w]
            anchor_centers = np.column_stack([x.ravel(), y.ravel()]) * stride
            anchor_centers = np.repeat(anchor_centers, self._num_anchors, axis=0)
            
            scores = scores.ravel()
            keep = scores >= conf_thresh
            
            scores = scores[keep]
            anchor_centers = anchor_centers[keep]
            bbox_preds = bbox_preds.reshape(-1, 4)[keep]
            kps_preds = kps_preds.reshape(-1, 10)[keep]
            
            if scores.shape[0] == 0:
                continue
            
            bbox_preds = bbox_preds * stride
            kps_preds = kps_preds * stride
            
            bboxes = distance2bbox(anchor_centers, bbox_preds)
            kpss = distance2kps(anchor_centers, kps_preds)
            
            bboxes /= det_scale
            kpss /= det_scale
            
            scores_list.append(scores)
            bboxes_list.append(bboxes)
            kpss_list.append(kpss)
            
        if not scores_list:
            return np.empty((0, 4)), np.empty((0, 5, 2))
            
        scores = np.concatenate(scores_list, axis=0)
        bboxes = np.concatenate(bboxes_list, axis=0)
        kpss = np.concatenate(kpss_list, axis=0)
        
        bboxes_cv = []
        for i in range(bboxes.shape[0]):
            x1, y1, x2, y2 = bboxes[i]
            bboxes_cv.append([float(x1), float(y1), float(x2 - x1), float(y2 - y1)])
            
        keep = cv2.dnn.NMSBoxes(bboxes_cv, scores.tolist(), conf_thresh, nms_thresh)
        if len(keep) > 0:
            keep = keep.flatten()
            bboxes = bboxes[keep]
            scores = scores[keep]
            kpss = kpss[keep]
            
            kpss = kpss.reshape(-1, 5, 2)
            order = scores.argsort()[::-1]
            return bboxes[order], kpss[order]
        else:
            return np.empty((0, 4)), np.empty((0, 5, 2))
