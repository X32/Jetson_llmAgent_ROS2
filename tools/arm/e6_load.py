"""E6 B4③：20Hz ACT 推理负载发生器（配合板上 tegrastats 采样）

以 20Hz 轮发夹具 obs（PC→Jetson /act/obs），板上节点持续 execute——
复现 e2_eval 推理中的真实负载形态，无需 robosuite。

运行（PC，act venv + source ROS）:
  source /opt/ros/humble/setup.bash
  /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e6_load.py --seconds 70
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
ap.add_argument('--seconds', type=float, default=70)
ap.add_argument('--hz', type=float, default=20.0)
args = ap.parse_args()

f = np.load(args.fixture)
qpos, img = f['obs_qpos'], f['obs_img']

rclpy.init()
node = Node('e6_load')
pub = node.create_publisher(UInt8MultiArray, '/act/obs', 10)
n_recv = 0


def on_chunk(m):
    global n_recv
    n_recv += 1


node.create_subscription(UInt8MultiArray, '/act/chunk', on_chunk, 10)

t0 = time.perf_counter()
while pub.get_subscription_count() == 0 and time.perf_counter() - t0 < 5:
    time.sleep(0.05)
print(f'匹配订阅 {pub.get_subscription_count()}，开始 {args.hz}Hz × {args.seconds}s')

period = 1.0 / args.hz
n_sent, lat = 0, []
i = 0
t_end = time.perf_counter() + args.seconds
while time.perf_counter() < t_end:
    ts = time.perf_counter()
    m = UInt8MultiArray()
    m.data = array('B', np.array([n_sent + 1], '<u4').tobytes()
                   + qpos[i:i + 1].astype('<f4').tobytes() + img[i:i + 1].astype('<f4').tobytes())
    pub.publish(m)
    n_sent += 1
    i = (i + 1) % len(qpos)
    rclpy.spin_once(node, timeout_sec=max(0, period - (time.perf_counter() - ts) - 0.002))
    lat.append((time.perf_counter() - ts) * 1e3)
    sleep = period - (time.perf_counter() - ts)
    if sleep > 0:
        time.sleep(sleep)

print(f'发 {n_sent} 条 / 收 {n_recv} 条 chunk；节拍误差 p95='
      f'{np.percentile(lat, 95):.2f}ms（含自旋等待）')
node.destroy_node()
rclpy.shutdown()
