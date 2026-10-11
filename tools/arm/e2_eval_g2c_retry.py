"""【E2-R10·C0】本件 = e2_eval_g2c.py（冻结）的孪生：开环不变 + "抓空检测→脚本化毫米级重抓"营救环。
其余逐字同源（坑位#19）。相对 e2_eval_g2c.py 的 diff：本头注 / 主循环重写为两相位（改动集中在此）。

【设计——对 E10-A 验尸的回应】
  Phase 1（ACT 开环）：只播首 chunk 64 步（成功历史全在 t=40-51，播满 300 无信息量）。
  Phase 2（脚本化营救，仅对"近距离失手"生效，诚实边界）：
    近失判定 = 全程 min(eef−cube xy) < 2.5cm（远失 F1 不救——ACT 没到地方就是没到）。
    - 指距被方块顶住（≥3.0cm，F4"抓住了没举起"）→ 脚本化直提
    - 指距合拢归零（F2 抓空 / F1' 没下压）→ 张开手指 → 悬到方块正上方（GT 坐标）
      → 下探到抓取高度 → 合爪 → 检查 → 提起。最多 2 次尝试。
  【系统定位】混合系统：ACT 负责接近与主轨迹，脚本负责最后一厘米的抓取校验——
  简历叙事须如实写"ACT 粗规划 + 抓取校验环节"，不是纯模型涨分。

【实测机械参数（2026-10-08 标定）】
  OSC action=1 ≈ 1.16 cm/步（配置标称 output_max=0.05 不可信，阻抗控制吃掉大半）
  夹爪：+1=合爪，-1=张开（实测：-1 十步指距 0.0775 / +1 十步 0.0082）
  抓取高度：成功集 eef_z_min 中位 0.810 ≈ cube_z−0.019；成功判定 = lift.py:417（cube z>0.84）

用法:
  unset PYTHONPATH && MUJOCO_GL=egl python e2_eval_g2c_retry.py \
      --ckpt policy_epoch_2200_seed_0.ckpt --episodes 50
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
ap.add_argument('--ckpt', default='policy_best.ckpt')
ap.add_argument('--episodes', type=int, default=20)
ap.add_argument('--horizon', type=int, default=300)
ap.add_argument('--near-miss', type=float, default=0.025, help='近距离失手门槛：min_d_xy 低于此值才触发营救')
ap.add_argument('--retries', type=int, default=3, help='重抓最大尝试次数（深度阶梯：标准/深6mm/深12mm…）')
ap.add_argument('--record', type=int, default=0, help='录前 N 个【触发营救】的回合（含 Phase1 抓空全程 + Phase2 重抓全程）')
ap.add_argument('--seed0', type=int, default=1000)
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


# ---------- 【孪生新增】脚本化运动原语（实测标定：action=1 ≈ 1.16cm/步） ----------
STEP_CM = 0.0116          # m/步 @ action=1
GRIP_CLOSE, GRIP_OPEN = 1.0, -1.0
GSEP_BLOCKED = 0.030      # 指距 ≥3.0cm = 被方块顶住（方块宽 4.0-4.4cm；全合拢 ~0.008）


def gsep(obs):
    return abs(obs['robot0_gripper_qpos'][0] - obs['robot0_gripper_qpos'][1])


# ---------- 【录像】录"触发营救"的回合：Phase1 + Phase2 全程帧 ----------
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


# ---------- 主循环：两相位 ----------
lat_ms = []
succ, rescue_log = [], []
CHUNK_ONLY = 64           # Phase 1 只播首 chunk（成功历史全在 t=40-51）

for ep in range(args.episodes):
    obs = env.reset()
    rec_on = rec_saved < args.record            # 配额未满则本集开录（营救没触发就丢弃）
    rec_frames.clear()
    cube0 = obs['cube_pos'].astype(np.float64).copy()
    ep_ret, done_t = 0.0, None

    # ---- Phase 1：ACT 开环一次性发射（与冻结件逐字同，仅步数封顶 64） ----
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
        min_d_xy = min(min_d_xy, np.linalg.norm(obs['robot0_eef_pos'][:2] - obs['cube_pos'][:2]))
        z_rise = max(z_rise, obs['cube_pos'][2] - cube0[2])
        if env._check_success():
            done_t = t
            break

    phase1 = '✅' if done_t is not None else f'❌(min_d_xy={min_d_xy:.3f},gsep={gsep(obs):.4f},z_rise={z_rise:.3f})'
    rescue = '—'

    # ---- Phase 2：脚本化营救（仅近距离失手） ----
    if done_t is None and min_d_xy < args.near_miss:
        blocked = gsep(obs) >= GSEP_BLOCKED
        if blocked:                                   # F4：抓住了没举起 → 直提
            res = move_to([obs['cube_pos'][0], obs['cube_pos'][1], 1.0], GRIP_CLOSE)
            rescue = f'直提→{"✅" if res == "success" else "❌"}'
        else:                                         # F2 抓空 / F1' 没下压 → 微修正重抓
            for attempt in range(args.retries):               # 深度阶梯：−0.019 起，每档再深 6mm
                cube = obs['cube_pos'].copy()                 # 【v2】每次重读——上次失败可能推歪方块
                dz = -0.019 - 0.006 * attempt
                move_to([cube[0], cube[1], 0.90], GRIP_OPEN)          # 张开+悬到方块上方
                move_to([cube[0], cube[1], cube[2] + dz], GRIP_OPEN)  # 下探
                if close_and_check():
                    res = move_to([cube[0], cube[1], 1.0], GRIP_CLOSE)
                    rescue = f'重抓#{attempt + 1}→{"✅" if res == "success" else "❌"}'
                    if res == 'success':
                        break
                    rescue += '(提起未过线)'
                else:
                    rescue = f'重抓#{attempt + 1}→仍空'
        if env._check_success():
            done_t = -1                               # 营救成功（标记 -1 区分于 Phase 1）

    ok = done_t is not None
    succ.append(ok); rescue_log.append(rescue if not ok or done_t == -1 else '—')
    print(f'ep{ep:02d}: {"✅成功" if ok else "❌失败"} P1{phase1} '
          f'{"(营救)" if done_t == -1 else ""} {rescue if done_t == -1 else ""}')
    if rec_on and rescue != '—' and rec_frames and rec_saved < args.record:
        import imageio
        frames = np.repeat(np.repeat(np.array(rec_frames), 4, axis=1), 4, axis=2)  # 84→336 放大
        imageio.mimwrite(os.path.join(args.ckpt_dir, f'e2_rescue_ep{ep}.mp4'),
                         frames, fps=20, quality=8)
        rec_saved += 1
        print(f'       🎬 已录营救过程 → e2_rescue_ep{ep}.mp4 ({len(frames)} 帧)')
    rec_on = False

lat = np.array(lat_ms)
n_rescued = sum(1 for d in rescue_log if d.startswith(('直提→✅', '重抓')))
print(f'\n==== E2 评估结果（g2c + 抓取营救） ====')
print(f'成功率: {sum(succ)}/{args.episodes} = {np.mean(succ):.0%}   '
      f'(Phase1 开环 {sum(1 for d in rescue_log if d == "—")}/内 + 营救 {n_rescued})')
print(f'营救明细: {[d for d in rescue_log if d != "—"]}')
if len(lat):
    print(f'chunk 推理: mean={lat.mean():.1f}ms p95={np.percentile(lat, 95):.1f}ms (N={len(lat)})')
