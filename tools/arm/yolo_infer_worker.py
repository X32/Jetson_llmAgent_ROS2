"""【E9-C】每集一 spawn 的 YOLO 推理 worker：读图 → onnxruntime → stdout 单行 JSON。

为什么 subprocess：act-venv（评测进程）不装 onnxruntime/cv2，零污染；yolo-venv 独立依赖。
失败语义（评测主程序约定）：
  exit 0 + {"n":0}     = 正常无检出（漏检 → miss-policy 分支处理）
  exit != 0 / 超时     = 同漏检 + 计数告警，评测循环绝不崩（坑位#9：连 5 集全错才停）
永不提供 GT 兜底。

用法: /mnt/apfs/workplace/venvs/yolo/bin/python yolo_infer_worker.py --onnx best.onnx --img /tmp/snap.jpg
输出: {"n":1,"dets":[{"cx":320.5,"cy":244.0,"w":33.2,"h":24.1,"conf":0.87}]}（原图像素坐标）
"""
import argparse
import json
import sys

sys.path.insert(0, '/mnt/apfs/workplace/ROS2/src/vision_agent')
from vision_agent.yolo_onnx import YoloOnnx            # 与 ROS2 节点同一份推理核（防漂移）

import cv2                                             # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('--onnx', required=True)
ap.add_argument('--img', required=True)
ap.add_argument('--conf', type=float, default=0.25)
ap.add_argument('--iou', type=float, default=0.45)
a = ap.parse_args()

img = cv2.imread(a.img)
if img is None:
    print(json.dumps({'n': 0, 'err': 'read_fail'}))
    sys.exit(0)
det = YoloOnnx(a.onnx)(img, a.conf, a.iou)
dets = [dict(cx=round(float((b[0] + b[2]) / 2), 1), cy=round(float((b[1] + b[3]) / 2), 1),
             w=round(float(b[2] - b[0]), 1), h=round(float(b[3] - b[1]), 1),
             conf=round(float(s), 3))
        for b, s in zip(det['xyxy'], det['conf'])]
print(json.dumps({'n': len(dets), 'dets': dets}))
