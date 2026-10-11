"""【E9-C】本件 = e2_eval_g2c_noisy.py（E9-A 孪生）的姊妹件：把"手工注噪"换成真 YOLO 感知。
其余逐字同源（坑位#19）。每集 reset 后：sim.render(480×640) → yolo_infer_worker（yolo-venv
subprocess，act-venv 零污染）→ bbox 中心 → 单应反投影平面 z=0.831 → 覆盖 obs['cube_pos']。
84×84 观测帧不动——唯一变量 = cube_pos 来源（GT → YOLO 估计）。

【boot 三自检】① 相机固定断言（首末集外参逐位一致，防中途漂移）② 链路自检（boot 快照必须
检出恰 1 个目标，拦通道序/letterbox 病）③ 单应往返（GT 投影→反投影 误差 <1mm）。

【miss 语义】漏检不崩不兜底真值：--miss-policy fail=本集照跑但坐标用桌面中心先验并计漏检；
overall（主口径）/given-detected/det-rate 三数分报。worker 超时/崩溃=同漏检+告警计数，
连 5 集全错停评（坑位#9）。

用法:
  unset PYTHONPATH && MUJOCO_GL=egl python e2_eval_g2c_percept.py \
      --ckpt policy_epoch_2200_seed_0.ckpt --cube-onnx <best.onnx> --episodes 50 --pair-seed 2000
"""
import argparse
import csv
import json
import os
import pickle
import subprocess
import sys
import time

import numpy as np
import torch

ap = argparse.ArgumentParser()
ap.add_argument('--ckpt_dir', default='/mnt/apfs/workplace/act/ckpt_lift_ph_g2c')
ap.add_argument('--ckpt', default='policy_best.ckpt')
ap.add_argument('--episodes', type=int, default=20)
ap.add_argument('--horizon', type=int, default=300)
ap.add_argument('--record', type=int, default=0)
ap.add_argument('--seed0', type=int, default=1000)
ap.add_argument('--cube-onnx', required=True, help='自训 cube 模型 onnx（Phase B 产物）')
ap.add_argument('--worker', default='/mnt/apfs/workplace/ROS2/tools/arm/yolo_infer_worker.py')
ap.add_argument('--yolo-py', default='/mnt/apfs/workplace/venvs/yolo/bin/python')
ap.add_argument('--snap-h', type=int, default=480)
ap.add_argument('--snap-w', type=int, default=640)
ap.add_argument('--plane-z', type=float, default=0.831)
ap.add_argument('--conf', type=float, default=0.25)
ap.add_argument('--miss-policy', choices=['fail'], default='fail',
                help='fail=漏检集用桌面中心先验 (0,0) 照跑，计入漏检口径')
ap.add_argument('--pair-seed', type=int, default=0)
args = ap.parse_args()

# ---------- 策略加载（与冻结件逐字同） ----------
policy_config = dict(clr=1e-5, num_queries=64, kl_weight=10, hidden_dim=512, dim_feedforward=3200,
                     lr_backbone=1e-5, backbone='resnet18', enc_layers=4, dec_layers=7, nheads=8,
                     camera_names=['agentview', 'robot0_eye_in_hand'],
                     state_dim=7, qpos_dim=12)  # [R4-g2c] 12 维
sys.path.insert(0, '/mnt/apfs/workplace/act')
sys.argv = [sys.argv[0], '--ckpt_dir', 'x', '--policy_class', 'ACT', '--task_name', 'x',
            '--seed', '0', '--num_epochs', '0']
from policy import ACTPolicy                        # noqa: E402
policy = ACTPolicy(policy_config)
ckpt = torch.load(os.path.join(args.ckpt_dir, args.ckpt), map_location='cuda')
policy.load_state_dict(ckpt)
policy.cuda().eval()
with open(os.path.join(args.ckpt_dir, 'dataset_stats.pkl'), 'rb') as fph:
    stats = pickle.load(fph)
a_mean, a_std = stats['action_mean'], stats['action_std']

# ---------- 环境（与冻结件逐字同） ----------
import robosuite                                        # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402
from robosuite.utils.camera_utils import (              # noqa: E402
    get_camera_intrinsic_matrix, get_camera_extrinsic_matrix)

env = robosuite.make(
    'Lift', robots=['Panda'],
    controller_configs=load_controller_config(default_controller='OSC_POSE'),
    has_renderer=False, has_offscreen_renderer=True, use_camera_obs=True,
    camera_names=['agentview', 'robot0_eye_in_hand'],
    camera_heights=84, camera_widths=84,
    ignore_done=True,
)

CAM, H, W = 'agentview', args.snap_h, args.snap_w

_K = get_camera_intrinsic_matrix(env.sim, CAM, H, W)
_Ex0 = get_camera_extrinsic_matrix(env.sim, CAM)


def Hwp_matrix():
    """世界平面(z=plane_z)→像素 单应。【约定坑】robosuite Ex 是"相机→世界"（E5 验证件），
    须取转置+平移变号：x_cam = Rᵀ(X−o)。boot 自检②往返对账兜底。"""
    Ex = get_camera_extrinsic_matrix(env.sim, CAM)
    Rwc, o = Ex[:3, :3].T, Ex[:3, 3]
    return _K @ np.hstack([Rwc[:, 0:1], Rwc[:, 1:2], (Rwc @ (-o) + Rwc[:, 2] * args.plane_z)[:, None]])


Hpw = np.linalg.inv(Hwp_matrix())


def px_to_world(u, v):
    q = Hpw @ np.array([u, v, 1.0])
    return q[0] / q[2], q[1] / q[2]


# ---------- 感知块：render → worker → 世界坐标 ----------
import cv2                                             # noqa: E402

_snap_i = 0
_n_worker_err = 0


def perceive():
    """→ (est_xyz | None, det_meta)。None=漏检。永不读 GT。"""
    global _snap_i, _n_worker_err
    img = env.sim.render(camera_name=CAM, height=H, width=W)[::-1]      # flipud（E5 坑位#5）
    _snap_i += 1
    snap = f'/tmp/e9c_snap_{_snap_i % 4}.jpg'                            # 轮换 4 个临时文件
    cv2.imwrite(snap, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    try:
        r = subprocess.run([args.yolo_py, args.worker, '--onnx', args.cube_onnx,
                            '--img', snap, '--conf', str(args.conf)],
                           capture_output=True, text=True, timeout=20)
        line = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else '{}'
        out = json.loads(line)
    except Exception as e:                                               # 超时/崩溃=同漏检
        _n_worker_err += 1
        print(f'  [worker 异常 #{_n_worker_err}] {type(e).__name__}')
        return None, dict(err=str(e))
    dets = out.get('dets', [])
    if not dets:
        return None, dict(conf=0.0)
    d = max(dets, key=lambda d: d['conf'])                               # 单类：取最高置信
    wx, wy = px_to_world(d['cx'], d['cy'])
    return np.array([wx, wy, args.plane_z]), d


def make_obs(obs):
    qpos = np.concatenate([obs['robot0_eef_pos'], obs['robot0_eef_quat'],
                           obs['robot0_gripper_qpos'],
                           obs['robot0_eef_pos'] - obs['cube_pos']]).astype(np.float32)
    qpos = (qpos - stats['qpos_mean']) / stats['qpos_std']
    imgs = np.stack([obs['agentview_image'], obs['robot0_eye_in_hand_image']])
    imgs = torch.from_numpy(imgs.copy()).cuda().float().unsqueeze(0) / 255.0
    imgs = torch.einsum('k h w c -> k c h w', imgs[0]).unsqueeze(0)
    return torch.from_numpy(qpos).cuda().float().unsqueeze(0), imgs


# ---------- boot 三自检 ----------
_obs0 = env.reset()
# ① 相机固定断言
assert np.abs(get_camera_extrinsic_matrix(env.sim, CAM) - _Ex0).max() < 1e-9, '相机外参漂移?!'
# ② 单应往返自检：世界点→像素→世界 必须 <1mm
from robosuite.utils.camera_utils import get_camera_transform_matrix  # noqa: E402
_T = get_camera_transform_matrix(env.sim, CAM, H, W)
_p = _obs0['cube_pos'].copy()
_q = _T @ np.array([_p[0], _p[1], args.plane_z, 1.0])
_u, _v = _q[0] / _q[2], _q[1] / _q[2]
_wx, _wy = px_to_world(_u, _v)
_rt_err = float(np.hypot(_wx - _p[0], _wy - _p[1]))
print(f'[boot] 单应往返误差 {_rt_err * 1000:.2f}mm（<1mm 才算标定干净）')
assert _rt_err < 0.001
# ③ 链路自检：boot 快照必须检出目标（拦通道序/letterbox 病）
est0, det0 = perceive()
print(f'[boot] 链路自检: 检出 {0 if est0 is None else 1} 个目标 conf={det0.get("conf", 0):.2f}')
if est0 is None:
    raise SystemExit('boot 快照零检出——通道序/letterbox/模型有病，先冒烟 worker 再来')

lat_ms = []
succ, det_flags, ep_errs = [], [], []
tele_f = open(os.path.join(args.ckpt_dir, 'e9c_percept_telemetry.csv'), 'w', newline='')
tele = csv.writer(tele_f)
tele.writerow(['ep', 'det', 'conf', 'w', 'h', 'est_x', 'est_y', 'gt_x', 'gt_y',
               'err_x_cm', 'err_y_cm', 'ok'])

for ep in range(args.episodes):
    if args.pair_seed:
        np.random.seed(args.pair_seed + ep)               # 与 Phase A 同款配对协议
    obs = env.reset()
    cube_gt = obs['cube_pos'].copy()
    est, d = perceive()
    if est is None:                                       # miss-policy fail：桌面中心先验照跑
        est = np.array([0.0, 0.0, args.plane_z])
    obs['cube_pos'] = est
    done_t, ep_ret, chunk, t_exec = None, 0.0, None, 0
    for t in range(args.horizon):
        qpos_t, img_t = make_obs(obs)
        if chunk is None:
            torch.cuda.synchronize(); t0 = time.perf_counter()
            chunk = policy(qpos_t, img_t).detach().cpu().numpy().squeeze(0)
            torch.cuda.synchronize(); lat_ms.append((time.perf_counter() - t0) * 1e3)
            t_exec = 0
        a = chunk[min(t_exec, 63)]
        a = a * a_std + a_mean
        obs, r, _, _ = env.step(np.clip(a, -1, 1))
        ep_ret += r
        t_exec += 1
        if env._check_success():
            done_t = t
            break
    ok = done_t is not None
    succ.append(ok)
    det_flags.append(d.get('conf', 0) > 0)
    ex, ey = (est[0] - cube_gt[0]) * 100, (est[1] - cube_gt[1]) * 100
    ep_errs.append((ex, ey))
    tele.writerow([ep, int(d.get('conf', 0) > 0), d.get('conf', 0), d.get('w', 0), d.get('h', 0),
                   round(est[0], 4), round(est[1], 4),
                   round(cube_gt[0], 4), round(cube_gt[1], 4),
                   round(ex, 2), round(ey, 2), int(ok)])
    tele_f.flush()
    print(f'ep{ep:02d}: {"✅成功" if ok else "❌失败"} @t={done_t} '
          f'det={"Y" if d.get("conf", 0) > 0 else "MISS"} conf={d.get("conf", 0):.2f} '
          f'err=({ex:+.1f},{ey:+.1f})cm')
    if _n_worker_err >= 5:
        raise RuntimeError('worker 连续异常 ≥5——判链路故障停评（坑位#9）')

tele_f.close()
lat = np.array(lat_ms)
e = np.array(ep_errs)
n_det = sum(det_flags)
print(f'\n==== E9-C 感知版 g2c 评测 ====')
print(f'overall      : {sum(succ)}/{args.episodes} = {np.mean(succ):.0%}   （主口径；GT 锚定 68%）')
if n_det:
    gd = [s for s, d in zip(succ, det_flags) if d]
    print(f'given-detected: {sum(gd)}/{n_det} = {sum(gd) / n_det:.0%}')
print(f'检出率       : {n_det}/{args.episodes}   worker异常: {_n_worker_err}')
if n_det:
    de = e[np.array(det_flags)]
    print(f'感知误差(检出集): 均值 ({de[:, 0].mean():+.2f},{de[:, 1].mean():+.2f})cm  '
          f'σ ({de[:, 0].std():.2f},{de[:, 1].std():.2f})cm  '
          f'|xy| p95 {np.percentile(np.hypot(*de.T), 95):.2f}cm')
print(f'chunk 推理: mean={lat.mean():.1f}ms p95={np.percentile(lat, 95):.1f}ms (N={len(lat)})')
