#!/usr/bin/env python3
"""E7 活窗口（独立进程）：MuJoCo 原生 viewer，订阅 /e5/mirror（qpos 全量）实时渲染。

为什么要独立进程（坑位#15 终版）：本机 NVIDIA 驱动下，原生 GLFW 窗口与 egl 离屏
上下文**同进程互斥**（后建者静默死，窗口永冻首帧）。act_node 进程离不开 egl
（84² 策略观测每步离屏渲染），所以窗口搬出来单开一个进程：

    act_node --live-view ──(DDS /e5/mirror, Float64MultiArray=qpos, 20Hz)──▶ 本进程

本进程自建同款 robosuite Lift 环境（渲染器全关、绝不碰 EGL）→ 贴 qpos →
mj_forward → viewer.sync()。窗口可拖拽旋转、滚轮缩放；关窗即退出。
阶段旁白在终端（demo 脚本 tail orchestrator 日志），窗口只管 3D 画面。

用法（须 venv python + ROS 环境，见 tools/arm/e7_live_demo.sh T5）：
    source /opt/ros/humble/setup.bash && source install/setup.bash
    /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e7_mirror_viewer.py
"""
import argparse

ap = argparse.ArgumentParser()
ap.add_argument('--topic', default='/e5/mirror')
args = ap.parse_args()

import mujoco                                   # noqa: E402
import mujoco.viewer                            # noqa: E402
import robosuite                                # noqa: E402
from robosuite.controllers import load_controller_config   # noqa: E402
import rclpy                                    # noqa: E402
from rclpy.node import Node                     # noqa: E402
from std_msgs.msg import Float64MultiArray      # noqa: E402

# ---- 同款环境（与 e5_act_node boot 逐参数一致），但渲染全关：本进程不许有 EGL ----
env = robosuite.make('Lift', robots=['Panda'],
                     controller_configs=load_controller_config(default_controller='OSC_POSE'),
                     has_renderer=False, has_offscreen_renderer=False, use_camera_obs=False,
                     ignore_done=True)
env.reset()
m = env.sim.model._model      # 真 MjModel（wrapper 见 robosuite binding_utils:274/586）
d = env.sim.data._data        # 真 MjData

viewer = mujoco.viewer.launch_passive(m, d)     # 本进程唯一 GL 上下文 = GLFW（健康组合）


class Mirror(Node):
    def __init__(self):
        super().__init__('e7_mirror_viewer')
        self.n_msg = 0
        self.create_subscription(Float64MultiArray, args.topic, self.on_q, 20)

    def on_q(self, msg):
        n = min(len(msg.data), d.qpos.size)
        d.qpos[:n] = msg.data[:n]               # 全量贴（臂 9 + 方块自由关节 7）
        mujoco.mj_forward(m, d)                 # 正向运动学摆好所有 body（不积分动力学）
        viewer.sync()
        self.n_msg += 1
        if self.n_msg % 100 == 1:
            print(f'[mirror] 帧 #{self.n_msg}（每 100 帧报一次）', flush=True)


def main():
    rclpy.init()
    node = Mirror()
    print(f'[mirror] 窗口已开（nq={d.qpos.size}），等待 {args.topic} 的 qpos ...（空闲时也可拖拽旋转视角）', flush=True)
    try:
        while rclpy.ok() and viewer.is_running():
            rclpy.spin_once(node, timeout_sec=0.05)
    except KeyboardInterrupt:
        pass
    print('[mirror] 退出', flush=True)
    viewer.close()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
