#!/usr/bin/env python3
"""E-YOLO-BOARD: 板上 YOLO 推理服务（TRT-FP16 引擎 + cuda-python，照 e6b 模板）。

与 e6b_act_infer_node_g2c.py 同款话题对 RPC（板上零自定义接口依赖，std_msgs 走天下）:
  /yolo_board/req  (PC→Jetson, UInt8MultiArray): [seq u32][tlen u32][target utf8][jpg bytes]
  /yolo_board/resp (Jetson→PC, String JSON): {"seq":n,"objects":[{label,x1,y1,x2,y2,confidence,grade}],
                                              "infer_ms":ms,"error":""}
前后处理复用 PC 同一份 yolo_onnx.py（letterbox/NMS 逐字不漂移）；解码体照抄其 __call__ 50-64 行。

运行（板上，系统 python3）:
  cd ~/Desktop/workplace/yolo_board && python3 yolo_board_serve_node.py --engine best_fp16.engine
"""
import argparse
import array
import json
import time

import cv2
import numpy as np
import tensorrt as trt
from cuda import cudart

import rclpy
from rclpy.node import Node
from std_msgs.msg import UInt8MultiArray, String

from yolo_onnx import letterbox, nms

ap = argparse.ArgumentParser()
ap.add_argument('--engine', default='best_fp16.engine')
ap.add_argument('--conf-thr', type=float, default=0.25)
ap.add_argument('--iou-thr', type=float, default=0.45)
ap.add_argument('--warmup', type=int, default=20)
args = ap.parse_args()

H2D = cudart.cudaMemcpyKind.cudaMemcpyHostToDevice
D2H = cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost


def check(err, what=''):
    if isinstance(err, tuple):
        err = err[0]
    if err != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f'cuda error {err} @ {what}')


logger = trt.Logger(trt.Logger.ERROR)
t_boot = time.perf_counter()
with open(args.engine, 'rb') as fh, trt.Runtime(logger) as rt:
    eng = rt.deserialize_cuda_engine(fh.read())
ctx = eng.create_execution_context()
names = [eng.get_tensor_name(i) for i in range(eng.num_io_tensors)]
shapes = {n: tuple(eng.get_tensor_shape(n)) for n in names}
err, stream = cudart.cudaStreamCreate()
check(err, 'streamCreate')
ptrs = {}
for n in names:
    err, p = cudart.cudaMalloc(int(np.prod(shapes[n])) * 4)
    check(err, f'malloc {n}')
    ptrs[n] = p
    ctx.set_tensor_address(n, p)
NAME_I = [n for n in names if eng.get_tensor_mode(n) == trt.TensorIOMode.INPUT][0]
NAME_O = [n for n in names if eng.get_tensor_mode(n) == trt.TensorIOMode.OUTPUT][0]
out_host = np.empty(shapes[NAME_O], np.float32)


def infer_once(x):
    check(cudart.cudaMemcpy(ptrs[NAME_I], x.ctypes.data, x.nbytes, H2D), 'H2D x')
    if not ctx.execute_async_v3(stream):
        raise RuntimeError('execute_async_v3 returned False')
    check(cudart.cudaStreamSynchronize(stream), 'sync')
    check(cudart.cudaMemcpy(out_host.ctypes.data, ptrs[NAME_O], out_host.nbytes, D2H), 'D2H')
    return out_host


zx = np.zeros(shapes[NAME_I], np.float32)
for _ in range(args.warmup):
    infer_once(zx)
print(f'[yolo_board_serve] engine={args.engine} in={NAME_I}{shapes[NAME_I]} '
      f'out={NAME_O}{shapes[NAME_O]} warmup={args.warmup} '
      f'boot={time.perf_counter() - t_boot:.1f}s 就绪', flush=True)


def decode(out, r, l, t):
    """照抄 yolo_onnx.YoloOnnx.__call__ 解码体（50-64 行），只把 ort 输出换成 TRT 输出。"""
    arr = out.reshape(out.shape[1], -1) if out.ndim == 3 else out.reshape(-1, out.shape[-1]).T
    box, sc = arr[:4], arr[4:]
    idx, conf = sc.argmax(0), sc.max(0)
    m = conf > args.conf_thr
    if not m.any():
        return [], []
    cx, cy, bw, bh = box[:, m]
    xyxy = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1)
    c, s = idx[m], conf[m]
    keep = nms(xyxy, s, c, args.iou_thr)
    xyxy, s = xyxy[keep], s[keep]
    xyxy = xyxy.copy()
    xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - l) / r
    xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - t) / r
    return xyxy.tolist(), s.tolist()


class ServeNode(Node):
    def __init__(self):
        super().__init__('yolo_board_serve')
        self.create_subscription(UInt8MultiArray, '/yolo_board/req', self.on_req, 10)
        self.pub_resp = self.create_publisher(String, '/yolo_board/resp', 10)
        self.n = 0

    def on_req(self, msg):
        try:
            t0 = time.perf_counter()
            raw = bytes(msg.data)
            seq, tlen = np.frombuffer(raw[:8], '<u4')
            target = raw[8:8 + tlen].decode('utf-8')
            img = cv2.imdecode(np.frombuffer(raw[8 + tlen:], np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                self._reply(seq, target, [], 0.0, 'jpg 解码失败')
                return
            x, r, l, t = letterbox(img)                       # 与 PC 同一份 letterbox
            out = infer_once(np.ascontiguousarray(x))
            boxes, confs = decode(out.copy(), r, l, t)
            infer_ms = (time.perf_counter() - t0) * 1e3
            objs = [dict(label=target, x1=round(b[0], 2), y1=round(b[1], 2),
                         x2=round(b[2], 2), y2=round(b[3], 2),
                         confidence=round(float(s), 4), grade='TRT')
                    for b, s in zip(boxes, confs)]
            self._reply(seq, target, objs, infer_ms, '')
            self.n += 1
            if self.n % 100 == 0:
                self.get_logger().info(f'n={self.n} infer={infer_ms:.1f}ms')
        except Exception as e:
            self.get_logger().error(f'on_req 异常: {e!r}')
            try:
                self._reply(0, '?', [], 0.0, repr(e))
            except Exception:
                pass

    def _reply(self, seq, target, objs, infer_ms, err):
        m = String()
        m.data = json.dumps(dict(seq=int(seq), objects=objs, infer_ms=round(infer_ms, 2),
                                 error=err, target=target))
        self.pub_resp.publish(m)


def main():
    rclpy.init()
    node = ServeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
