"""E2 探针：Lift 环境的观测/动作契约 —— 输出填进手册记录表 环境探针

用法:
  python e2_env_probe.py --headless          # 自动化验证（offscreen EGL，不开窗口）
  python e2_env_probe.py                     # 开窗口肉眼看渲染（本地有显示器时）
"""
import argparse

import numpy as np
import robosuite

ap = argparse.ArgumentParser()
ap.add_argument('--headless', action='store_true', help='offscreen 渲染验证，不开窗口')
ap.add_argument('--frames', type=int, default=3, help='headless 模式步进次数')
args = ap.parse_args()

from robosuite.controllers import load_controller_config
env = robosuite.make(
    'Lift', robots=['Panda'],
    # ⚠️ 必须显式指定：默认是 JointVelocity(8维)，与数据集的 OSC_POSE(7维) 语义错位（坑位#7）
    controller_configs=load_controller_config(default_controller='OSC_POSE'),
    has_renderer=not args.headless,
    has_offscreen_renderer=args.headless,   # headless：顺便验证 1080 Ti EGL 出图
    use_camera_obs=args.headless,           # 窗口模式先纯状态跑通；headless 顺便看相机 key
    camera_names=['agentview', 'robot0_eye_in_hand'],
    camera_heights=84, camera_widths=84,
    ignore_done=True,
)
obs = env.reset()
print('obs keys:', list(obs.keys()))
for k, v in obs.items():
    v = np.asarray(v)
    print(f'  {k}: {v.shape} {v.dtype}')
print('action_dim:', env.action_dim)        # 预期 7（OSC_POSE），实测为准

print('controller:', type(env.robots[0].controller).__name__)
low, high = env.action_spec                     # robosuite 1.4.1 没有 action_sample()（那是 dm_control 的 API）
a = np.random.uniform(low, high)
obs2, r, done, info = env.step(a)
print('step 返回:', type(obs2).__name__, f'reward={r}', f'done={done}', f'info={info}')

if args.headless:
    for _ in range(args.frames - 1):
        obs2, r, done, info = env.step(np.random.uniform(low, high))
    for k, v in obs2.items():
        if 'image' in k:
            v = np.asarray(v)
            print(f'  图像 {k}: 非零像素占比 {float((v > 0).mean()):.2%}（=0 说明渲染黑屏）')

print('_check_success():', env._check_success())   # 成功判定 API——Step4 eval 直接用它
# 收尾：解释器退出前显式析构，避免 EGL 上下文在关灯阶段 __del__ 报错（噪声，但难看）
del env
import gc; gc.collect()
print('✅ 探针通过：环境建立/复位/步进/渲染 全链路 OK')
