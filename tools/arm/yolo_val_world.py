"""【E9-B 验收】t0-val 专尺：val 集每帧 YOLO 检出 → bbox 中心 → 单应反投影到世界平面(0.831)
→ 对账 hdf5 GT 世界坐标。零 robosuite 依赖（cam.json + meta.jsonl 都是渲染时导出的）。

验收线（计划 Phase B）：t=0 帧 检出 ≥39/40、世界系误差均值 ≤1cm 且 p95 ≤2cm（x/y 分列）。
同时报 Phase A 定价换算：实测 σ 等效噪声落在曲线哪个档（YOLO 目标 σ≤1.5cm）。

用法: /mnt/apfs/workplace/venvs/yolo/bin/python yolo_val_world.py \
        --dataset /mnt/nvme01/workplace/yolo/datasets/lift_cube --onnx <best.onnx> [--t0-only]
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, '/mnt/apfs/workplace/ROS2/src/vision_agent')
from vision_agent.yolo_onnx import YoloOnnx            # noqa: E402
import cv2                                             # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--dataset', default='/mnt/nvme01/workplace/yolo/datasets/lift_cube')
ap.add_argument('--onnx', required=True)
ap.add_argument('--conf', type=float, default=0.25)
ap.add_argument('--t0-only', action='store_true', help='只验 t=0 帧（评测只考 t=0）')
ap.add_argument('--split', default='val')
args = ap.parse_args()

cam = json.load(open(f'{args.dataset}/cam.json'))
Hwp = np.array(cam['H_w2p'])                            # 世界平面 → 像素
Hpw = np.linalg.inv(Hwp)                                # 像素 → 世界平面


def px_to_world(u, v):
    q = Hpw @ np.array([u, v, 1.0])
    return q[0] / q[2], q[1] / q[2]


yolo = YoloOnnx(args.onnx)
rows = [json.loads(l) for l in open(f'{args.dataset}/meta.jsonl')]
rows = [r for r in rows if r['split'] == args.split and (r['t'] == 0 or not args.t0_only)]

n_det, errs = 0, []
for r in rows:
    img = cv2.imread(os.path.join(args.dataset, r['img']))
    det = yolo(img, args.conf)
    if len(det['conf']) == 0:
        continue
    i = int(np.argmax(det['conf']))                    # 单类场景取最高置信
    x1, y1, x2, y2 = det['xyxy'][i]
    wx, wy = px_to_world((x1 + x2) / 2, (y1 + y2) / 2)
    gx, gy, _ = r['gt_world']
    errs.append((wx - gx, wy - gy))
    n_det += 1

errs = np.array(errs)
n = len(rows)
tag = 't0-val' if args.t0_only else 'val 全帧'
print(f'==== E9-B 验收（{tag}，n={n}）====')
print(f'检出: {n_det}/{n} = {n_det / n:.0%}   (验收线 ≥97.5%)')
if len(errs):
    e = errs * 100                                      # → cm
    print(f'误差均值: x {e[:, 0].mean():+.2f}cm  y {e[:, 1].mean():+.2f}cm  '
          f'|xy| {np.hypot(*e.T).mean():.2f}cm   (验收线 ≤1cm)')
    print(f'误差 p95 : x {np.percentile(abs(e[:, 0]), 95):.2f}cm  y {np.percentile(abs(e[:, 1]), 95):.2f}cm'
          f'   (验收线 ≤2cm)')
    print(f'恒偏检查: |mean| 大而 std 小 = 系统偏（查标定）；std = x {e[:, 0].std():.2f} y {e[:, 1].std():.2f}cm')
    print(f'等效随机噪声 σ: x {e[:, 0].std():.2f}cm  y {e[:, 1].std():.2f}cm   (Phase A 目标 ≤1.5cm)')
else:
    print('零检出——链路有病（通道序/letterbox/模型），先冒烟 worker')
