#!/usr/bin/env python3
"""E-YOLO-BOARD: 板上 YOLO 可行性实测——真实 480×640 图，全管道（letterbox+推理+解码+NMS）计时。

铁律兼容：推理核就是 PC 端 yolo_onnx.py 那一份（逐字不漂移），本文件只是计时壳。
用法（板上，系统 python3，无需 ROS）:
  python3 yolo_board_bench.py --model best.onnx --image test.jpg --runs 100
"""
import argparse
import resource
import time

import cv2

from yolo_onnx import YoloOnnx

ap = argparse.ArgumentParser()
ap.add_argument('--model', default='best.onnx')
ap.add_argument('--image', default='test.jpg')
ap.add_argument('--runs', type=int, default=100)
ap.add_argument('--warmup', type=int, default=20)
a = ap.parse_args()

img = cv2.imread(a.image)
assert img is not None, a.image
print(f'image {img.shape[1]}x{img.shape[0]}  model={a.model}  runs={a.runs} warmup={a.warmup}')

rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
yolo = YoloOnnx(a.model)
for _ in range(a.warmup):
    yolo(img)

ms, det, conf = [], 0, 0.0
t0 = time.perf_counter()
for _ in range(a.runs):
    t = time.perf_counter()
    r = yolo(img)
    ms.append((time.perf_counter() - t) * 1e3)
    if len(r['xyxy']):
        det = len(r['xyxy'])
        conf = max(conf, float(r['conf'].max()))
wall = (time.perf_counter() - t0) * 1e3 / a.runs
rss1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
ms.sort()
print(f'检出={det}框 最高置信度={conf:.3f}')
print(f'全管道 ms: mean={sum(ms)/len(ms):.1f} p50={ms[len(ms)//2]:.1f} '
      f'p95={ms[int(len(ms)*0.95)]:.1f} min={ms[0]:.1f} max={ms[-1]:.1f}')
print(f'墙钟 {wall:.1f}ms/次  RSS峰值 {rss0/1024:.0f}→{rss1/1024:.0f}MB（Δ{(rss1-rss0)/1024:.0f}MB）')
