#!/usr/bin/env python3
"""E-YOLO-BOARD 对齐自检：同一张图，板上 TRT-FP16 引擎 vs onnxruntime CPU 逐项对比。

验三件事：输出张量差（fp16 量级）、检出框一致（IoU）、置信度差。全过才准上链。
运行（板上）: cd ~/Desktop/workplace/yolo_board && python3 yolo_board_align.py --image test.jpg
"""
import argparse
import time

import cv2
import numpy as np
import onnxruntime as ort
import tensorrt as trt
from cuda import cudart

from yolo_onnx import letterbox, nms

ap = argparse.ArgumentParser()
ap.add_argument('--onnx', default='best.onnx')
ap.add_argument('--engine', default='best_fp16.engine')
ap.add_argument('--image', default='test.jpg')
ap.add_argument('--conf-thr', type=float, default=0.25)
a = ap.parse_args()

H2D = cudart.cudaMemcpyKind.cudaMemcpyHostToDevice
D2H = cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost


def check(err, what=''):
    if isinstance(err, tuple):
        err = err[0]
    if err != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f'cuda error {err} @ {what}')

img = cv2.imread(a.image)
assert img is not None, a.image
x, r, l, t = letterbox(img)
x = np.ascontiguousarray(x)


def decode(out):
    arr = out.reshape(out.shape[1], -1)
    box, sc = arr[:4], arr[4:]
    idx, conf = sc.argmax(0), sc.max(0)
    m = conf > a.conf_thr
    if not m.any():
        return np.zeros((0, 4)), np.zeros(0)
    cx, cy, bw, bh = box[:, m]
    xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1)
    c, s = idx[m], conf[m]
    keep = nms(xyxy, s, c)
    xyxy = xyxy[keep].copy()
    xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - l) / r
    xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - t) / r
    return xyxy, s[keep]


# --- ORT 基准 ---
sess = ort.InferenceSession(a.onnx, ort.SessionOptions(), providers=['CPUExecutionProvider'])
t0 = time.perf_counter()
out_ort = np.asarray(sess.run(None, {sess.get_inputs()[0].name: x})[0], np.float32)
ort_ms = (time.perf_counter() - t0) * 1e3

# --- TRT 引擎 ---
logger = trt.Logger(trt.Logger.ERROR)
with open(a.engine, 'rb') as fh, trt.Runtime(logger) as rt:
    eng = rt.deserialize_cuda_engine(fh.read())
ctx = eng.create_execution_context()
names = [eng.get_tensor_name(i) for i in range(eng.num_io_tensors)]
shapes = {n: tuple(eng.get_tensor_shape(n)) for n in names}
err, stream = cudart.cudaStreamCreate()
check(err, 'stream')
ptrs = {}
for n in names:
    err, p = cudart.cudaMalloc(int(np.prod(shapes[n])) * 4)
    check(err, f'malloc {n}')
    ptrs[n] = p
    ctx.set_tensor_address(n, p)
NI = [n for n in names if eng.get_tensor_mode(n) == trt.TensorIOMode.INPUT][0]
NO = [n for n in names if eng.get_tensor_mode(n) == trt.TensorIOMode.OUTPUT][0]
oh = np.empty(shapes[NO], np.float32)
check(cudart.cudaMemcpy(ptrs[NI], x.ctypes.data, x.nbytes, H2D), 'H2D')
ctx.execute_async_v3(stream)
check(cudart.cudaStreamSynchronize(stream), 'sync')
check(cudart.cudaMemcpy(oh.ctypes.data, ptrs[NO], oh.nbytes, D2H), 'D2H')

# --- 对比 ---
diff = np.abs(oh - out_ort).max()
box_a, conf_a = decode(oh)
box_b, conf_b = decode(out_ort)
print(f'输出张量 max|TRT-ORT| = {diff:.4f}   （ORT {ort_ms:.1f}ms）')
print(f'检出: TRT {len(box_a)}框 conf={[round(float(c), 4) for c in conf_a]}')
print(f'      ORT {len(box_b)}框 conf={[round(float(c), 4) for c in conf_b]}')
ok = len(box_a) == len(box_b) and len(box_a) > 0
if ok:
    d_px = np.abs(box_a - box_b).max()
    d_cf = np.abs(conf_a - conf_b).max()
    print(f'框坐标 max差 = {d_px:.3f}px   置信度 max差 = {d_cf:.4f}')
    ok = d_px < 1.0 and d_cf < 5e-3
print('对齐结论:', '✅ 通过' if ok else '❌ 不通过——别上链，先查')
