#!/usr/bin/env python3
"""E6 Step4.1: 板上 ACT 推理服务节点（手册 §7.1 / §2.3 topic-pair RPC）

无状态 chunk 服务器：收字节 → GPU buffer → execute_async_v3 → 回字节。
零预处理、零 stats 依赖、不存历史（时间集成全在 PC e2_eval）——挂了重启即恢复。

协议（UInt8MultiArray.data，全部小端裸字节）:
  /act/obs   (PC→Jetson): [seq u32][qpos(9) f32][image(2,3,84,84) f32]
  /act/chunk (Jetson→PC): [seq u32][action_chunk(64,7) f32]（z-score 空间原始输出）
  单客户端、在途恒 1（20Hz 逐次等答）→ seq 配对退化为等值比较，无乱序。
  [坑#13 实录] 手册原定 ByteMultiArray，rclpy Humble 的 int8[] 断言/反序列化有怪癖
  （setter 只认逐元素 bytes、收端给 list[bytes]）——换 UInt8MultiArray（uint8 原生
  int 路径，169KB 序列化 1.5ms / 反序列化 0.1ms，roundtrip 逐位一致）。
诊断: 每 100 次推理发 /latency_diag {node:'e6_jetson', stage:'infer', seq, infer_ms, q_ms}
  q_ms = 上次推理完成 → 本次到达的间隔（服务端可见的到达抖动）

运行（板上，系统 python3 + cuda-python，无 torch——venv torch cu130 与 JP6 驱动不兼容）:
  source /opt/ros/humble/setup.bash
  cd ~/Desktop/workplace/e6_act && python3 e6_act_infer_node.py --engine act_fp16_orin.engine
回调内同步推理（4ms << 50ms 周期，单客户端在途1）；executor 吞回调异常——必须自带
try/except 显式打日志（rclpy Humble 坑，memory 在案）。
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
ap.add_argument('--engine', default='act_fp16_orin.engine')
ap.add_argument('--warmup', type=int, default=50, help='启动 warmup 次数（boot 成本不计入 B3）')
args = ap.parse_args()

H2D = cudart.cudaMemcpyKind.cudaMemcpyHostToDevice
D2H = cudart.cudaMemcpyKind.cudaMemcpyDeviceToHost


def check(err, what=''):
    if isinstance(err, tuple):
        err = err[0]
    if err != cudart.cudaError_t.cudaSuccess:
        raise RuntimeError(f'cuda error {err} @ {what}')


# ---------- TRT 10 引擎 + device buffer（常驻，服务生命周期内不释放） ----------
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
NAME_Q = [n for n in names if shapes[n] == (1, 9)][0]
NAME_I = [n for n in names if shapes[n] == (1, 2, 3, 84, 84)][0]
NAME_O = [n for n in names if n not in (NAME_Q, NAME_I)][0]
out_host = np.empty(shapes[NAME_O], np.float32)          # (1,64,7)


def infer_once(q, im):
    """q:(1,9) im:(1,2,3,84,84) 连续 float32 → out_host 更新，返回墙钟推理 ms"""
    t0 = time.perf_counter()
    check(cudart.cudaMemcpy(ptrs[NAME_Q], q.ctypes.data, q.nbytes, H2D), 'H2D q')
    check(cudart.cudaMemcpy(ptrs[NAME_I], im.ctypes.data, im.nbytes, H2D), 'H2D im')
    if not ctx.execute_async_v3(stream):
        raise RuntimeError('execute_async_v3 returned False')
    check(cudart.cudaStreamSynchronize(stream), 'sync')
    check(cudart.cudaMemcpy(out_host.ctypes.data, ptrs[NAME_O], out_host.nbytes, D2H), 'D2H')
    return (time.perf_counter() - t0) * 1e3


# warmup（零输入；boot 成本不计入延迟口径）
zq = np.zeros(shapes[NAME_Q], np.float32)
zi = np.zeros(shapes[NAME_I], np.float32)
for _ in range(args.warmup):
    infer_once(zq, zi)
print(f'[e6_act_infer] engine={args.engine} warmup={args.warmup} '
      f'boot={time.perf_counter() - t_boot:.1f}s 就绪 (q={NAME_Q} im={NAME_I} out={NAME_O})')


class InferNode(Node):
    def __init__(self):
        super().__init__('e6_act_infer')
        self.pub_chunk = self.create_publisher(UInt8MultiArray, '/act/chunk', 10)
        self.pub_diag = self.create_publisher(String, '/latency_diag', 20)
        self.create_subscription(UInt8MultiArray, '/act/obs', self.on_obs, 10)
        self.n = 0
        self.last_done = time.perf_counter()

    def on_obs(self, msg):
        try:
            q_ms = (time.perf_counter() - self.last_done) * 1e3
            raw = bytes(msg.data)                    # UInt8MultiArray → array('B')，直转
            if len(raw) != 4 + (9 + 2 * 3 * 84 * 84) * 4:
                self.get_logger().error(f'载荷长度异常: {len(raw)}B')
                return
            seq = int(np.frombuffer(raw[:4], '<u4')[0])
            body = np.frombuffer(raw[4:], '<f4')
            q = np.ascontiguousarray(body[:9].reshape(shapes[NAME_Q]))
            im = np.ascontiguousarray(body[9:].reshape(shapes[NAME_I]))
            infer_ms = infer_once(q, im)
            out = UInt8MultiArray()
            out.data = array.array('B', np.array([seq], '<u4').tobytes() + out_host.tobytes())
            self.pub_chunk.publish(out)
            self.last_done = time.perf_counter()
            self.n += 1
            if self.n % 100 == 0:
                d = String()
                d.data = json.dumps({'node': 'e6_jetson', 'stage': 'infer', 'seq': seq,
                                     'infer_ms': round(infer_ms, 2), 'q_ms': round(q_ms, 2),
                                     'n': self.n, 'ts': time.time()})
                self.pub_diag.publish(d)
                self.get_logger().info(f'n={self.n} seq={seq} infer={infer_ms:.2f}ms q={q_ms:.1f}ms')
        except Exception as e:                        # executor 静默吞异常——显式打
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
