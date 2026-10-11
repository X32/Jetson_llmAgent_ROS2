"""E6 R1 冒烟：PC 手动 pub 夹具 obs → 等 /act/chunk → 与参考对答案（手册 §7.3）

抓三件事：seq 匹配 / 维度 64×7 / 字节序与数值正确（坑位#8 专抓 float32 LE 字节序——
数值全错放大 1e38 级即中招）。

运行（PC，act venv + source ROS——E5 实测共存 OK）:
  source /opt/ros/humble/setup.bash && source install/setup.bash
  /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e6_r1_smoke.py [--n 5]
"""
import argparse
import time
from array import array

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import UInt8MultiArray

ap = argparse.ArgumentParser()
ap.add_argument('--fixture', default='/mnt/apfs/workplace/act/e6/e6_fixture.npz')
ap.add_argument('--n', type=int, default=5, help='连发 n 组夹具（seq 递增，逐次等答）')
ap.add_argument('--timeout', type=float, default=1.0)
args = ap.parse_args()

f = np.load(args.fixture)
qpos, img, ref = f['obs_qpos'], f['obs_img'], f['ref_chunk']

rclpy.init()
node = Node('e6_r1_smoke')
pub = node.create_publisher(UInt8MultiArray, '/act/obs', 10)
inbox = {}


def on_chunk(m):
    raw = bytes(m.data)          # UInt8MultiArray 反序列化即 array('B')，bytes() 直转
    s = int(np.frombuffer(raw[:4], '<u4')[0])
    inbox[s] = np.frombuffer(raw[4:], '<f4').copy()


node.create_subscription(UInt8MultiArray, '/act/chunk', on_chunk, 10)

# 等 DDS discovery 完成再发（否则首条消息在远端订阅匹配前发出→白丢，伪超时）
t0 = time.perf_counter()
while pub.get_subscription_count() == 0 and time.perf_counter() - t0 < 5:
    time.sleep(0.05)
print(f'pub 匹配订阅数: {pub.get_subscription_count()}'
      f'（discovery 用时 {(time.perf_counter() - t0) * 1e3:.0f}ms）')

ok_all = True
for i in range(args.n):
    seq = i + 1
    m = UInt8MultiArray()
    payload = np.array([seq], '<u4').tobytes() \
        + qpos[i:i + 1].astype('<f4').tobytes() + img[i:i + 1].astype('<f4').tobytes()
    m.data = array('B', payload)
    t0 = time.perf_counter()
    pub.publish(m)
    rtt = None
    while time.perf_counter() - t0 < args.timeout:
        rclpy.spin_once(node, timeout_sec=0.01)
        if seq in inbox:
            rtt = (time.perf_counter() - t0) * 1e3
            break
    if rtt is None:
        print(f'seq={seq}: ❌ 超时（{args.timeout * 1e3:.0f}ms 内无 chunk）')
        ok_all = False
        continue
    c = inbox.pop(seq).reshape(64, 7)
    d = np.abs(c - ref[i])
    cos = float(np.sum(c * ref[i]) / (np.linalg.norm(c) * np.linalg.norm(ref[i])))
    flag = '✅' if d.max() < 1e-1 and cos > 0.999 else '❌'   # FP16 引擎容差（L2 实测 4.95e-2）
    ok_all &= flag == '✅'
    print(f'seq={seq}: {flag} RTT={rtt:6.1f}ms  维度={c.shape}  max|Δref|={d.max():.2e}  余弦={cos:.6f}')
    if d.max() > 1e30:
        print('  ⚠️ 数值放大 1e30 级——字节序中招（坑位#8）')

print('\nR1 冒烟:', '全过 ✅' if ok_all else '有失败 ❌')
node.destroy_node()
rclpy.shutdown()
