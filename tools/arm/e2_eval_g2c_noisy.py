"""【E9-A】本件 = e2_eval_g2c.py（冻结）的孪生：感知误差定价——reset 后 t=0 前对 cube_pos 注入
指定模式的扰动，其余逐字同源（坑位#19）。目的：给"可部署版 g2c"定感知精度需求 σ*（px/cm 双刻度）。

相对 e2_eval_g2c.py 的 diff（共 5 处）：
  ① 本头注；② 新参 --noise/--sigma/--bias-xy/--outlier-*/--plane-z/--snap-h/--snap-w/--pair-seed；
  ③ 断言禁闭环（--temporal/--query-every）——开环下策略只在 t=0 查询一次，注入点唯一有效；
  ④ 相机投影工具 + 开机雅可比/行序自检（e5_act_node.py 已验证件搬移，0.63cm GT 上限同源）；
  ⑤ reset 后 t=0 前的扰动块（~20 行）。

【扰动语义】
  none   : 纯 GT 对照（锚定 ~68%）
  pixel  : GT 投影到生产分辨率像素面加 N(0,σ_px) 高斯 → 反投影回世界系（忠实模型：各向异性）
  world  : xy 直接加 N(0,σ_cm) 高斯（需求语言：世界系厘米）
  outlier: world σ=1cm 基底 + outlier_frac 概率跳 10cm 离群（重尾/悬崖诊断）
  bias   : 沿给定方向常偏 dx,dy cm（系统偏最坏情形诊断）
  z 一律写 --plane-z 平面常量（t=0 实测 0.8301-0.8319，均值 0.831）——z 误差是确定性偏差不是噪声。

【配对种子】--pair-seed N 时每集 reset 前 np.random.seed(N+ep) → 各噪声档共享同一批开局，
  可做配对 McNemar。先双跑核对每集打印的 cube_gt 逐位一致，不一致退非配对。

用法:
  unset PYTHONPATH && MUJOCO_GL=egl python e2_eval_g2c_noisy.py \
      --ckpt policy_epoch_2200_seed_0.ckpt --noise world --sigma 1 --episodes 30 --record 0
"""
import argparse
import os
import pickle
import sys
import time

import numpy as np
import torch

ap = argparse.ArgumentParser()
ap.add_argument('--ckpt_dir', default='/mnt/apfs/workplace/act/ckpt_lift_ph_g2c')
ap.add_argument('--ckpt', default='policy_best.ckpt', help='ckpt 文件名（可指后期存档——坑位#11：按成功率选档，不信 val loss）')
ap.add_argument('--episodes', type=int, default=20)
ap.add_argument('--temporal', action='store_true', help='时间集成（每步查询+指数加权）')
ap.add_argument('--query-every', type=int, default=0, help='无集成时每 N 步查一次（0=每 chunk 一次）')
ap.add_argument('--horizon', type=int, default=300)
ap.add_argument('--record', type=int, default=1, help='录像前 N 个成功 episode')
ap.add_argument('--seed0', type=int, default=1000)
# ---------- 【E9-A】感知噪声注入参数（diff ②） ----------
ap.add_argument('--noise', choices=['none', 'pixel', 'world', 'outlier', 'bias'], default='none',
                help='扰动模式（见头注语义表）')
ap.add_argument('--sigma', type=float, default=0.0, help='pixel 模式=像素 σ；world/outlier 模式=厘米 σ')
ap.add_argument('--bias-xy', default='-1,0', help='bias 模式常偏 "[cm]dx,dy"（世界系，−x=负）')
ap.add_argument('--outlier-frac', type=float, default=0.1, help='outlier 模式离群概率')
ap.add_argument('--outlier-cm', type=float, default=10.0, help='outlier 模式离群距离 cm')
ap.add_argument('--plane-z', type=float, default=0.831, help='反投影/写入的平面常量（t=0 实测 0.8301-0.8319）')
ap.add_argument('--snap-h', type=int, default=480, help='pixel 噪声网格高（生产分辨率，与 Phase C 快照一致）')
ap.add_argument('--snap-w', type=int, default=640, help='pixel 噪声网格宽')
ap.add_argument('--pair-seed', type=int, default=0, help='>0 时每集 reset 前 np.random.seed(该值+ep) 配对')
args = ap.parse_args()                                   # 先解析自己的参数

# 【diff ③】E9-A 定价只对开环成立：闭环下每步都重查询，t=0 单点注入不再代表"感知误差"
if args.temporal or args.query_every:
    raise SystemExit('E9-A 禁用 --temporal/--query-every（定价实验只对开环协议成立）')

# ---------- 策略加载（架构参数必须与训练逐字一致——坑位#19 同源） ----------
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
policy.load_state_dict(ckpt)   # 官方存的是裸 state_dict（key=model.*），不包 policy_state_dict 层
policy.cuda().eval()
with open(os.path.join(args.ckpt_dir, 'dataset_stats.pkl'), 'rb') as fph:
    stats = pickle.load(fph)
a_mean, a_std = stats['action_mean'], stats['action_std']

# ---------- 环境：照数据集 env_args 建（OSC_POSE、84×84 双相机）——坑位#7 ----------
import robosuite                                        # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402
from robosuite.utils.camera_utils import (              # 【diff ④】E5 已验证投影件搬移
    get_camera_intrinsic_matrix, get_camera_extrinsic_matrix, get_camera_transform_matrix)

env = robosuite.make(
    'Lift', robots=['Panda'],
    controller_configs=load_controller_config(default_controller='OSC_POSE'),
    has_renderer=False, has_offscreen_renderer=True, use_camera_obs=True,
    camera_names=['agentview', 'robot0_eye_in_hand'],
    camera_heights=84, camera_widths=84,
    ignore_done=True,
)

CAM = 'agentview'


def world_to_pixel(p, H, W):
    """世界系 → 像素 (u,v)，v 自图顶向下（与 flipud 后的渲染图同约定，E5 坑位#5）"""
    T = get_camera_transform_matrix(env.sim, CAM, H, W)
    q = T @ np.array([p[0], p[1], p[2], 1.0])
    return q[0] / q[2], q[1] / q[2]


def pixel_to_world_xy(u, v, H, W):
    """像素 + 平面 z 常量 → 世界系 xy（K⁻¹ 射线 ∩ z=args.plane_z，e5_act_node.py:148 同源）"""
    K = get_camera_intrinsic_matrix(env.sim, CAM, H, W)
    Ex = get_camera_extrinsic_matrix(env.sim, CAM)
    d_w = Ex[:3, :3] @ (np.linalg.inv(K) @ np.array([u, v, 1.0]))
    o = Ex[:3, 3]
    t = (args.plane_z - o[2]) / d_w[2]
    return (o + t * d_w)[:2]


# ---------- 【diff ④】开机自检：行序 + 雅可比（mm/px 双向） ----------
_obs0 = env.reset()
_seg = np.asarray(env.sim.render(camera_name=CAM, height=args.snap_h, width=args.snap_w,
                                 segmentation=True))
_bid = env.cube_body_id
_adr, _num = int(env.sim.model.body_geomadr[_bid]), int(env.sim.model.body_geomnum[_bid])
_m = np.isin(_seg[..., 1].astype(int), list(range(_adr, _adr + _num)))
_ys, _xs = np.nonzero(_m)
_gt = world_to_pixel(_obs0['cube_pos'], args.snap_h, args.snap_w)
FLIP = (np.hypot(_xs.mean() - _gt[0], (args.snap_h - 1 - _ys.mean()) - _gt[1])
        < np.hypot(_xs.mean() - _gt[0], _ys.mean() - _gt[1]))
_proj_err = min(np.hypot(_xs.mean() - _gt[0], _ys.mean() - _gt[1]),
                np.hypot(_xs.mean() - _gt[0], (args.snap_h - 1 - _ys.mean()) - _gt[1]))
print(f'[自检] 行序 flipud={FLIP}  分割质心-GT投影距离={_proj_err:.1f}px（>10px = K/通道病，pixel 模式不可信）')
if args.noise == 'pixel' and _proj_err > 10:
    raise SystemExit('pixel 模式投影自检失败——先查 K/行序（E9 压测坑：H/W 传反=1.33× 静默错误）')
_p = _obs0['cube_pos'].copy()
J = np.zeros((2, 2))
for _ax in range(2):
    _q = _p.copy(); _q[_ax] += 0.01                      # +1cm 有限差分
    _u0, _v0 = world_to_pixel(_p, args.snap_h, args.snap_w)
    _u1, _v1 = world_to_pixel(_q, args.snap_h, args.snap_w)
    J[:, _ax] = [_u1 - _u0, _v1 - _v0]                   # d(u,v)/d(该轴 1cm) —— 注意轴混叠：
                                                          # x 动主要动 v，y 动主要动 u（相机斜装）
Ji = np.linalg.inv(J)                                     # cm/px
print(f'[雅可比] 世界→像素 J（列=该轴 1cm 位移引起的 (du,dv) px）= {np.round(J, 2).tolist()}'
      f'  ⇒ |x→px| {np.linalg.norm(J[:, 0]):.2f}px/cm, |y→px| {np.linalg.norm(J[:, 1]):.2f}px/cm')
print(f'[雅可比] 像素→世界 J⁻¹ = {np.round(Ji, 4).tolist()} cm/px'
      f'  ⇒ 1px(u) → 世界 {np.linalg.norm(Ji[:, 0]):.2f}cm, 1px(v) → 世界 {np.linalg.norm(Ji[:, 1]):.2f}cm'
      f'（各向异性比 {np.linalg.norm(Ji[:, 0]) / np.linalg.norm(Ji[:, 1]):.2f}:1）')


def perturb(cube_gt, rng):
    """t=0 感知估计器：GT → 指定噪声模式的估计位置（z 一律平面常量）。返回 est。"""
    if args.noise == 'none':
        return cube_gt                                    # 纯 GT 对照：不动（含真实 z）
    if args.noise == 'pixel':
        u, v = world_to_pixel(cube_gt, args.snap_h, args.snap_w)
        u2 = u + rng.normal(0, args.sigma)
        v2 = v + rng.normal(0, args.sigma)
        xy = pixel_to_world_xy(u2, v2, args.snap_h, args.snap_w)
        return np.array([xy[0], xy[1], args.plane_z])
    if args.noise in ('world', 'outlier'):
        eps = rng.normal(0, args.sigma / 100.0, 2)        # σ: cm → m
        if args.noise == 'outlier' and rng.random() < args.outlier_frac:
            th = rng.random() * 2 * np.pi
            eps = np.array([np.cos(th), np.sin(th)]) * args.outlier_cm / 100.0
        return np.array([cube_gt[0] + eps[0], cube_gt[1] + eps[1], args.plane_z])
    dx, dy = (float(x) for x in args.bias_xy.split(','))
    return np.array([cube_gt[0] + dx / 100.0, cube_gt[1] + dy / 100.0, args.plane_z])


def make_obs(obs):
    """robosuite obs → ACT 输入。pt 后端：图像 /255（ImageNet 归一化在 policy 内）"""
    qpos = np.concatenate([obs['robot0_eef_pos'], obs['robot0_eef_quat'],
                           obs['robot0_gripper_qpos'],
                           obs['robot0_eef_pos'] - obs['cube_pos']]).astype(np.float32)  # [R4-g2c] 拼 12 维
    qpos = (qpos - stats['qpos_mean']) / stats['qpos_std']
    imgs = np.stack([obs['agentview_image'], obs['robot0_eye_in_hand_image']])  # (2,84,84,3)
    imgs = torch.from_numpy(imgs.copy()).cuda().float().unsqueeze(0) / 255.0
    imgs = torch.einsum('k h w c -> k c h w', imgs[0]).unsqueeze(0)
    return torch.from_numpy(qpos).cuda().float().unsqueeze(0), imgs


lat_ms = []
succ, rets, rec = [], [], 0

for ep in range(args.episodes):
    if args.pair_seed:
        np.random.seed(args.pair_seed + ep)               # 配对：各档共享开局（reset 采样吃 np.random）
    obs = env.reset()                                    # robosuite 1.4.1 reset 无 seed 参数；
    cube_gt = obs['cube_pos'].copy()
    obs['cube_pos'] = perturb(cube_gt, np.random)        # 【diff ⑤】t=0 注入（开环下仅首个 make_obs 消费）
    err_cm = float(np.hypot(*(obs['cube_pos'][:2] - cube_gt[:2])) * 100)
    ep_frames, done_t, ep_ret = [], None, 0
    chunk, t_exec = None, 0
    for t in range(args.horizon):
        qpos_t, img_t = make_obs(obs)
        k = policy_config['num_queries']
        if chunk is None:
            torch.cuda.synchronize(); t0 = time.perf_counter()
            chunk = policy(qpos_t, img_t).detach().cpu().numpy().squeeze(0)  # (k,7) z-score 空间
            torch.cuda.synchronize(); lat_ms.append((time.perf_counter() - t0) * 1e3)
            t_exec = 0
        a = chunk[min(t_exec, k - 1)]
        a = a * a_std + a_mean                           # 反标准化 → OSC [-1,1]
        obs, r, _, _ = env.step(np.clip(a, -1, 1))
        ep_ret += r
        t_exec += 1
        if rec < args.record:
            ep_frames.append(obs['agentview_image'].copy())
        if env._check_success():
            done_t = t
            break
    ok = done_t is not None
    succ.append(ok); rets.append(ep_ret)
    if ok and rec < args.record and ep_frames:
        import imageio                                    # 录像（6.3）
        imageio.mimwrite(os.path.join(args.ckpt_dir, f'e2_noisy_ep{ep}.mp4'),
                         ep_frames, fps=20, quality=8)
        rec += 1
    print(f'ep{ep:02d}: {"✅成功" if ok else "❌失败"} @t={done_t} return={ep_ret:.1f} '
          f'err_xy={err_cm:.1f}cm cube_gt=({cube_gt[0]:.4f},{cube_gt[1]:.4f},{cube_gt[2]:.4f})')

lat = np.array(lat_ms)
print(f'\n==== E9-A 感知误差定价评估 ====')
print(f'噪声模式: {args.noise} σ={args.sigma} plane_z={args.plane_z} pair_seed={args.pair_seed or "非配对"}')
print(f'成功率: {sum(succ)}/{args.episodes} = {np.mean(succ):.0%}   (开环 GT锚定参考 ~68%)')
print(f'chunk 推理: mean={lat.mean():.1f}ms p95={np.percentile(lat, 95):.1f}ms (N={len(lat)})')
