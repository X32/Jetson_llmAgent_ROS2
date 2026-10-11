"""【E9】YOLO onnxruntime 推理核（纯 numpy/cv2/onnxruntime，零 ultralytics 依赖）——
PC 端 worker（tools/yolo_infer_worker.py）与 ROS2 节点（yolo_grounding_node.py）共用同一份，
防两处实现漂移。letterbox/NMS/解码逻辑逐字提取自 /mnt/nvme01/workplace/yolo/pc_onnx_test.py
（该件是 RKNN 转换链路的 FP32 黄金参照，已被板端验证）。

约定：输入 BGR(np.uint8) 任意分辨率 → 输出原图像素坐标 xyxy + conf（已反 letterbox）。
输出通道数自适应：arr 行数 = 4 + nc（COCO 84 / 单类 5）。
"""
import cv2
import numpy as np
import onnxruntime as ort


def letterbox(im, s=640):
    """BGR uint8 → float32 CHW RGB /255 + 灰边补齐；返回 (x, r, l, t)"""
    h, w = im.shape[:2]; r = min(s / w, s / h)
    im = cv2.resize(im, (round(w * r), round(h * r)), interpolation=cv2.INTER_LINEAR)
    dh, dw = (s - im.shape[0]) / 2, (s - im.shape[1]) / 2
    t, b = round(dh - 0.1), round(dh + 0.1); l, rr = round(dw - 0.1), round(dw + 0.1)
    im = cv2.copyMakeBorder(im, t, b, l, rr, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    x = np.ascontiguousarray(im[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255)[None]
    return x, r, l, t


def nms(xyxy, conf, cls, thr=0.45):
    keep, supp = [], np.zeros(len(conf), bool)
    for i in conf.argsort()[::-1]:
        if supp[i]: continue
        keep.append(i)
        cand = np.where((cls == cls[i]) & ~supp)[0]; cand = cand[cand != i]
        if not len(cand): continue
        xx1 = np.maximum(xyxy[i, 0], xyxy[cand, 0]); yy1 = np.maximum(xyxy[i, 1], xyxy[cand, 1])
        xx2 = np.minimum(xyxy[i, 2], xyxy[cand, 2]); yy2 = np.minimum(xyxy[i, 3], xyxy[cand, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        a1 = (xyxy[i, 2] - xyxy[i, 0]) * (xyxy[i, 3] - xyxy[i, 1])
        a2 = (xyxy[cand, 2] - xyxy[cand, 0]) * (xyxy[cand, 3] - xyxy[cand, 1])
        supp[cand[inter / np.maximum(a1 + a2 - inter, 1e-9) > thr]] = True
    return np.array(keep, int)


class YoloOnnx:
    def __init__(self, model_path, providers=('CPUExecutionProvider',)):
        self.sess = ort.InferenceSession(model_path, ort.SessionOptions(), providers=list(providers))
        self.iname = self.sess.get_inputs()[0].name

    def __call__(self, bgr_img, conf_thr=0.25, iou_thr=0.45):
        """→ dict(xyxy=(k,4) 原图像素, conf=(k,), cls=(k,))；k=0 表示无检出"""
        x, r, l, t = letterbox(bgr_img)
        out = np.asarray(self.sess.run(None, {self.iname: x})[0], np.float32)
        arr = out.reshape(out.shape[1], -1) if out.ndim == 3 else out.reshape(-1, out.shape[-1]).T
        box, sc = arr[:4], arr[4:]
        idx, conf = sc.argmax(0), sc.max(0)
        m = conf > conf_thr
        if not m.any():
            return dict(xyxy=np.zeros((0, 4)), conf=np.zeros(0), cls=np.zeros(0, int))
        cx, cy, bw, bh = box[:, m]
        xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1)
        c, s = idx[m], conf[m]
        keep = nms(xyxy, s, c, iou_thr)
        xyxy, c, s = xyxy[keep], c[keep], s[keep]
        xyxy = xyxy.copy()
        xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - l) / r
        xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - t) / r
        return dict(xyxy=xyxy, conf=s, cls=c.astype(int))
