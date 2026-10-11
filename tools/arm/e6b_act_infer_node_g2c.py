#!/usr/bin/env python3
"""E6-b: 板上 ACT 推理服务·维度自适应版（g2c 12 维引擎用；e6_act_infer_node.py 不动照旧）

与 e6_act_infer_node.py 的唯一差异：qpos 维度不再写死 9，从引擎输入 shape 自读——
  NAME_Q = shape 为 (1, N) 的输入（N=9 旧模型 / N=12 g2c 模型均可）
  载荷长度校验与 body 切分同步跟随 QDIM。
协议（UInt8MultiArray，小端裸字节，与 E6 逐字同）:
  /act/obs   (PC→Jetson): [seq u32][qpos(QDIM) f32][image(2,3,84,84) f32]
  /act/chunk (Jetson→PC): [seq u32][action_chunk(1,64,7) f32]（z-score 空间原始输出）
图输入约定（e3b_export_onnx_g2c.py）：qpos 已 z-score；图像已 /255+ImageNet+CHW——
预处理全在 PC 客户端（e5_grasp_v3_node / e2_eval_g2c remote 分支），本服务零预处理。

运行（板上，系统 python3 + cuda-python，无 torch）:
  cd ~/Desktop/workplace/e6_act && python3 e6b_act_infer_node_g2c.py --engine act_fp16_g2c.engine
"""
import argparse
import array
import json
import time

import numpy as np
import tensorrt as trt
from cuda import cudart

import rclpy
from rclpy.node import Node
from std_msgs.msg import UInt8MultiArray, String

ap = argparse.ArgumentParser()
ap.add_argument('--engine', default='act_fp16_g2c.engine')
ap.add_argument('--warmup', type=int, default=50)
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
NAME_I = [n for n in names if shapes[n] == (1, 2, 3, 84, 84)][0]
NAME_Q = [n for n in names if len(shapes[n]) == 2 and shapes[n][0] == 1][0]
NAME_O = [n for n in names if n not in (NAME_Q, NAME_I)][0]
QDIM = shapes[NAME_Q][1]
out_host = np.empty(shapes[NAME_O], np.float32)


def infer_once(q, im):
    t0 = time.perf_counter()
    check(cudart.cudaMemcpy(ptrs[NAME_Q], q.ctypes.data, q.nbytes, H2D), 'H2D q')
    check(cudart.cudaMemcpy(ptrs[NAME_I], im.ctypes.data, im.nbytes, H2D), 'H2D im')
    if not ctx.execute_async_v3(stream):
        raise RuntimeError('execute_async_v3 returned False')
    check(cudart.cudaStreamSynchronize(stream), 'sync')
    check(cudart.cudaMemcpy(out_host.ctypes.data, ptrs[NAME_O], out_host.nbytes, D2H), 'D2H')
    return (time.perf_counter() - t0) * 1e3


zq = np.zeros(shapes[NAME_Q], np.float32)
zi = np.zeros(shapes[NAME_I], np.float32)
for _ in range(args.warmup):
    infer_once(zq, zi)
print(f'[e6b_act_infer] engine={args.engine} qpos_dim={QDIM} warmup={args.warmup} '
      f'boot={time.perf_counter() - t_boot:.1f}s 就绪 (q={NAME_Q} im={NAME_I} out={NAME_O})',
      flush=True)


class InferNode(Node):
    def __init__(self):
        super().__init__('e6b_act_infer')
        self.pub_chunk = self.create_publisher(UInt8MultiArray, '/act/chunk', 10)
        self.pub_diag = self.create_publisher(String, '/latency_diag', 20)
        self.create_subscription(UInt8MultiArray, '/act/obs', self.on_obs, 10)
        self.n = 0
        self.last_done = time.perf_counter()

    def on_obs(self, msg):
        try:
            q_ms = (time.perf_counter() - self.last_done) * 1e3
            raw = bytes(msg.data)
            expect = 4 + (QDIM + 2 * 3 * 84 * 84) * 4
            if len(raw) != expect:
                self.get_logger().error(f'载荷长度异常: {len(raw)}B（期望 {expect}，qpos_dim={QDIM}）')
                return
            seq = int(np.frombuffer(raw[:4], '<u4')[0])
            body = np.frombuffer(raw[4:], '<f4')
            q = np.ascontiguousarray(body[:QDIM].reshape(shapes[NAME_Q]))
            im = np.ascontiguousarray(body[QDIM:].reshape(shapes[NAME_I]))
            infer_ms = infer_once(q, im)
            out = UInt8MultiArray()
            out.data = array.array('B', np.array([seq], '<u4').tobytes() + out_host.tobytes())
            self.pub_chunk.publish(out)
            self.last_done = time.perf_counter()
            self.n += 1
            if self.n % 100 == 0:
                d = String()
                d.data = json.dumps({'node': 'e6b_jetson', 'stage': 'infer', 'seq': seq,
                                     'infer_ms': round(infer_ms, 2), 'q_ms': round(q_ms, 2),
                                     'n': self.n, 'ts': time.time()})
                self.pub_diag.publish(d)
                self.get_logger().info(f'n={self.n} seq={seq} infer={infer_ms:.2f}ms q={q_ms:.1f}ms')
        except Exception as e:
            self.get_logger().error(f'on_obs 异常: {e!r}')


def main():
    rclpy.init()
    node = InferNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
