"""【E9-E 合体】本件 = e2_eval_g2c_retry.py（E10-C0 营救版）的孪生：营救环里的仿真真值
全部换成 YOLO 感知，其余逐字同源（坑位#19）。这是"可部署完整系统"：ACT 粗规划 + 指距
检测 + 脚本重抓 + 摄像头找方块，全程零真值。

相对 e2_eval_g2c_retry.py 的 diff（共 5 处）：
  ① 本头注；② 新参 --cube-onnx/--worker/--yolo-py/--snap-h/--snap-w/--plane-z/--conf；
  ③ 感知块 perceive()（render 480×640 → yolo-venv worker subprocess → bbox 中心 →
     单应反投影平面 z=0.831）+ boot 三自检（相机固定/单应往返/链路检出）；
  ④ 开局：obs['cube_pos'] = YOLO 估计（g2c 向量与近失判定共用）；近失判定 min_d_xy
     改对【开局估计】量（方块落桌不动，冻结 t=0 估计=真机器人可做）；
  ⑤ 营救重抓：每次尝试前【重新 perceive 一眼】（原版重读 GT——可部署语义=重看摄像头）；
     漏检则退回开局估计。直提分支的目标 xy 同样用开局估计。

用法:
  unset PYTHONPATH && MUJOCO_GL=egl python e2_eval_g2c_percept_retry.py \
      --ckpt policy_epoch_2200_seed_0.ckpt \
      --cube-onnx /mnt/nvme01/workplace/yolo/runs/lift_cube/v1/weights/best.onnx \
      --episodes 50 --pair-seed 2000 --record 3
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
ap.add_argument('--near-miss', type=float, default=0.025, help='近距离失手门槛：min_d_xy 低于此值才触发营救')
ap.add_argument('--retries', type=int, default=3, help='重抓最大尝试次数（深度阶梯：标准/深6mm/深12mm…）')
ap.add_argument('--record', type=int, default=0, help='录前 N 个【触发营救】的回合')
ap.add_argument('--seed0', type=int, default=1000)
# ---------- 【E9-E】感知参数（diff ②） ----------
ap.add_argument('--cube-onnx', required=True)
ap.add_argument('--worker', default='/mnt/apfs/workplace/ROS2/tools/arm/yolo_infer_worker.py')
ap.add_argument('--yolo-py', default='/mnt/apfs/workplace/venvs/yolo/bin/python')
ap.add_argument('--snap-h', type=int, default=480)
ap.add_argument('--snap-w', type=int, default=640)
ap.add_argument('--plane-z', type=float, default=0.831)
ap.add_argument('--conf', type=float, default=0.25)
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
    get_camera_intrinsic_matrix, get_camera_extrinsic_matrix, get_camera_transform_matrix)

env = robosuite.make(
    'Lift', robots=['Panda'],
    controller_configs=load_controller_config(default_controller='OSC_POSE'),
    has_renderer=False, has_offscreen_renderer=True, use_camera_obs=True,
    camera_names=['agentview', 'robot0_eye_in_hand'],
    camera_heights=84, camera_widths=84,
    ignore_done=True,
)


def make_obs(obs):
    qpos = np.concatenate([obs['robot0_eef_pos'], obs['robot0_eef_quat'],
                           obs['robot0_gripper_qpos'],
                           obs['robot0_eef_pos'] - obs['cube_pos']]).astype(np.float32)  # [R4-g2c] 拼 12 维
    qpos = (qpos - stats['qpos_mean']) / stats['qpos_std']
    imgs = np.stack([obs['agentview_image'], obs['robot0_eye_in_hand_image']])
    imgs = torch.from_numpy(imgs.copy()).cuda().float().unsqueeze(0) / 255.0
    imgs = torch.einsum('k h w c -> k c h w', imgs[0]).unsqueeze(0)
    return torch.from_numpy(qpos).cuda().float().unsqueeze(0), imgs


# ---------- 【diff ③】感知块：render → worker → 世界坐标（零真值） ----------
CAM, H, W = 'agentview', args.snap_h, args.snap_w
_K = get_camera_intrinsic_matrix(env.sim, CAM, H, W)
_Ex0 = get_camera_extrinsic_matrix(env.sim, CAM)
_Rwc, _o = _Ex0[:3, :3].T, _Ex0[:3, 3]                    # 【约定坑】Ex 是"相机→世界"，建世界→像素须 Rᵀ(X−o)
_Hwp = _K @ np.hstack([_Rwc[:, 0:1], _Rwc[:, 1:2], (_Rwc @ (-_o) + _Rwc[:, 2] * args.plane_z)[:, None]])
Hpw = np.linalg.inv(_Hwp)


def px_to_world(u, v):
    q = Hpw @ np.array([u, v, 1.0])
    return q[0] / q[2], q[1] / q[2]


import cv2                                             # noqa: E402

_snap_i = 0
_n_worker_err = 0


def perceive():
    """→ (est_xyz | None, conf)。render 480×640 → yolo worker → bbox 中心 → 反投影。永不读 GT。"""
    global _snap_i, _n_worker_err
    img = env.sim.render(camera_name=CAM, height=H, width=W)[::-1]      # flipud（E5 坑位#5）
    _snap_i += 1
    snap = f'/tmp/e9e_snap_{_snap_i % 4}.jpg'
    cv2.imwrite(snap, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    try:
        r = subprocess.run([args.yolo_py, args.worker, '--onnx', args.cube_onnx,
                            '--img', snap, '--conf', str(args.conf)],
                           capture_output=True, text=True, timeout=20)
        out = json.loads(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else '{}')
    except Exception as e:
        _n_worker_err += 1
        print(f'  [worker 异常 #{_n_worker_err}] {type(e).__name__}')
        return None, 0.0
    dets = out.get('dets', [])
    if not dets:
        return None, 0.0
    d = max(dets, key=lambda d: d['conf'])
    wx, wy = px_to_world(d['cx'], d['cy'])
    return np.array([wx, wy, args.plane_z]), d['conf']


# ---------- 脚本化运动原语（实测标定：action=1 ≈ 1.16cm/步）——与营救版逐字同 ----------
STEP_CM = 0.0116          # m/步 @ action=1
GRIP_CLOSE, GRIP_OPEN = 1.0, -1.0
GSEP_BLOCKED = 0.030      # 指距 ≥3.0cm = 被方块顶住（方块宽 4.0-4.4cm；全合拢 ~0.008）


def gsep(obs):
    return abs(obs['robot0_gripper_qpos'][0] - obs['robot0_gripper_qpos'][1])


# ---------- 录像：录"触发营救"的回合 ----------
rec_frames, rec_on, rec_saved = [], False, 0


def snap():
    if rec_on:
        rec_frames.append(obs['agentview_image'].copy())


def move_to(target_xyz, grip, max_steps=90, tol=0.008):
    """比例控制移动 eef 到目标点（世界系）。每步查成功（提着方块过线即成）。"""
    global obs
    for _ in range(max_steps):
        if env._check_success():
            return 'success'
        d = np.asarray(target_xyz) - obs['robot0_eef_pos']
        a = np.zeros(7)
        a[:3] = np.clip(d / STEP_CM * 0.7, -1, 1)     # 70% 增益防过冲
        a[6] = grip
        obs, _, _, _ = env.step(np.clip(a, -1, 1))
        snap()
        if np.linalg.norm(d[:2]) < tol and abs(d[2]) < tol:
            break
    return 'ok' if env._check_success() else 'moved'


def close_and_check(steps=25):
    """合爪并等指面稳定，返回是否被方块顶住。"""
    global obs
    for _ in range(steps):
        a = np.zeros(7); a[6] = GRIP_CLOSE
        obs, _, _, _ = env.step(a)
        snap()
    return gsep(obs) >= GSEP_BLOCKED


# ---------- boot 三自检 ----------
_obs0 = env.reset()
assert np.abs(get_camera_extrinsic_matrix(env.sim, CAM) - _Ex0).max() < 1e-9, '相机外参漂移?!'
_T = get_camera_transform_matrix(env.sim, CAM, H, W)
_q = _T @ np.array([_obs0['cube_pos'][0], _obs0['cube_pos'][1], args.plane_z, 1.0])
_u, _v = _q[0] / _q[2], _q[1] / _q[2]
_wx, _wy = px_to_world(_u, _v)
_rt_err = float(np.hypot(_wx - _obs0['cube_pos'][0], _wy - _obs0['cube_pos'][1]))
print(f'[boot] 单应往返误差 {_rt_err * 1000:.2f}mm（<1mm 才算标定干净）')
assert _rt_err < 0.001
est0, conf0 = perceive()
print(f'[boot] 链路自检: 检出 {0 if est0 is None else 1} 个目标 conf={conf0:.2f}')
if est0 is None:
    raise SystemExit('boot 快照零检出——先冒烟 worker')

# ---------- 主循环：两相位（感知版） ----------
lat_ms = []
succ, rescue_log = [], []
CHUNK_ONLY = 64           # Phase 1 只播首 chunk（成功历史全在 t=40-51）
tele_f = open(os.path.join(args.ckpt_dir, 'e9e_percept_retry_telemetry.csv'), 'w', newline='')
tele = csv.writer(tele_f)
tele.writerow(['ep', 'ok', 'rescue', 'conf0', 'err0_x_cm', 'err0_y_cm', 'n_looks', 'n_miss'])

for ep in range(args.episodes):
    if args.pair_seed:
        np.random.seed(args.pair_seed + ep)               # 与 E9-A/E9-C 同批配对
    obs = env.reset()
    rec_on = rec_saved < args.record
    rec_frames.clear()
    cube_gt = obs['cube_pos'].astype(np.float64).copy()   # 只记账对账用，不喂任何环节
    est, conf0 = perceive()                               # 【diff ④】开局一眼
    n_looks, n_miss = 1, int(est is None)
    if est is None:                                       # 漏检：桌面中心先验照跑
        est = np.array([0.0, 0.0, args.plane_z])
    obs['cube_pos'] = est                                 # g2c 向量唯一消费点（开环 t=0）
    ep_ret, done_t = 0.0, None

    # ---- Phase 1：ACT 开环一次性发射 ----
    chunk, t_exec, min_d_xy, z_rise = None, 0, 9.9, 0.0
    for t in range(CHUNK_ONLY):
        qpos_t, img_t = make_obs(obs)
        if chunk is None:
            torch.cuda.synchronize(); t0 = time.perf_counter()
            chunk = policy(qpos_t, img_t).detach().cpu().numpy().squeeze(0)
            torch.cuda.synchronize(); lat_ms.append((time.perf_counter() - t0) * 1e3)
        a = chunk[min(t_exec, 63)]
        a = a * a_std + a_mean
        obs, r, _, _ = env.step(np.clip(a, -1, 1))
        snap()
        ep_ret += r; t_exec += 1
        # 【diff ④】近失判定对开局估计量（方块落桌不动；冻结 t=0 = 真机器人可做）
        min_d_xy = min(min_d_xy, np.linalg.norm(obs['robot0_eef_pos'][:2] - est[:2]))
        z_rise = max(z_rise, obs['cube_pos'][2] - cube_gt[2])
        if env._check_success():
            done_t = t
            break

    phase1 = '✅' if done_t is not None else f'❌(min_d_xy={min_d_xy:.3f},gsep={gsep(obs):.4f})'
    rescue = '—'

    # ---- Phase 2：脚本化营救（近失才救；坐标全来自感知） ----
    if done_t is None and min_d_xy < args.near_miss:
        blocked = gsep(obs) >= GSEP_BLOCKED
        if blocked:                                   # F4：抓住了没举起 → 直提（目标=开局估计）
            res = move_to([est[0], est[1], 1.0], GRIP_CLOSE)
            rescue = f'直提→{"✅" if res == "success" else "❌"}'
        else:                                         # F2 抓空 / F1' 没下压 → 重抓
            for attempt in range(args.retries):
                n_looks += 1                          # 【diff ⑤】每次重抓前重看一眼（替换原版重读 GT）
                est2, conf2 = perceive()
                if est2 is not None:
                    est = est2                         # 新鲜估计；漏检则沿用旧估计
                else:
                    n_miss += 1
                dz = -0.019 - 0.006 * attempt
                move_to([est[0], est[1], 0.90], GRIP_OPEN)
                move_to([est[0], est[1], est[2] + dz], GRIP_OPEN)
                if close_and_check():
                    res = move_to([est[0], est[1], 1.0], GRIP_CLOSE)
                    rescue = f'重抓#{attempt + 1}→{"✅" if res == "success" else "❌"}'
                    if res == 'success':
                        break
                    rescue += '(提起未过线)'
                else:
                    rescue = f'重抓#{attempt + 1}→仍空'
        if env._check_success():
            done_t = -1
    ok = done_t is not None
    succ.append(ok); rescue_log.append(rescue if not ok or done_t == -1 else '—')
    tele.writerow([ep, int(ok), rescue, round(conf0, 3),
                   round((est[0] - cube_gt[0]) * 100, 2), round((est[1] - cube_gt[1]) * 100, 2),
                   n_looks, n_miss])
    tele_f.flush()
    print(f'ep{ep:02d}: {"✅成功" if ok else "❌失败"} P1{phase1} '
          f'{"(营救)" if done_t == -1 else ""} {rescue if done_t == -1 else ""} '
          f'looks={n_looks} miss={n_miss}')
    if rec_on and rescue != '—' and rec_frames and rec_saved < args.record:
        import imageio
        frames = np.repeat(np.repeat(np.array(rec_frames), 4, axis=1), 4, 2)  # 84→336 放大
        imageio.mimwrite(os.path.join(args.ckpt_dir, f'e9e_rescue_ep{ep}.mp4'),
                         frames, fps=20, quality=8)
        rec_saved += 1
        print(f'       🎬 已录营救过程 → e9e_rescue_ep{ep}.mp4 ({len(frames)} 帧)')
    rec_on = False

tele_f.close()
lat = np.array(lat_ms)
n_rescued = sum(1 for d in rescue_log if d.startswith(('直提→✅', '重抓')))
print(f'\n==== E9-E 感知+营救 合体评测 ====')
print(f'成功率: {sum(succ)}/{args.episodes} = {np.mean(succ):.0%}   '
      f'(Phase1 开环 {sum(1 for d in rescue_log if d == "—")}/{args.episodes} + 营救 {n_rescued})')
print(f'营救明细: {[d for d in rescue_log if d != "—"]}')
if len(lat):
    print(f'chunk 推理: mean={lat.mean():.1f}ms p95={np.percentile(lat, 95):.1f}ms (N={len(lat)})')
