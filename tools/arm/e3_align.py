"""E3 Step1 L1: ONNX(ORT-CPU) vs PyTorch 数值对齐（手册 §3.3，判据 max|Δ|<1e-3）

用 50 组真实观测（来自训练数据集不同 episode 的不同时刻）——比随机输入更严：
覆盖真实数据分布（含图像统计、qpos 各维真实值域）。
归一化全部在此脚本 numpy 侧做（图外），两侧吃完全相同的输入。
"""
import pickle
import sys

import numpy as np
import torch

sys.path.insert(0, '/mnt/apfs/workplace/act')
sys.argv = [sys.argv[0], '--ckpt_dir', 'x', '--policy_class', 'ACT', '--task_name', 'x',
            '--seed', '0', '--num_epochs', '0']
from policy import ACTPolicy  # noqa: E402
import h5py                    # noqa: E402
import onnxruntime as ort      # noqa: E402

CKPT = '/mnt/apfs/workplace/act/ckpt_lift_ph_v2/policy_epoch_2400_seed_0.ckpt'
STATS = '/mnt/apfs/workplace/act/ckpt_lift_ph_v2/dataset_stats.pkl'
DATA = '/mnt/apfs/workplace/act/data/lift_ph_act'
ONNX = '/mnt/apfs/workplace/act/e3/act_lift_ph.onnx'

# ---------- 预处理常量（与 e3_export_onnx.py 的 meta 一致） ----------
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

stats = pickle.load(open(STATS, 'rb'))
qm, qs = stats['qpos_mean'].astype(np.float32), stats['qpos_std'].astype(np.float32)
am, as_ = stats['action_mean'].astype(np.float32), stats['action_std'].astype(np.float32)

def prep_obs(qpos_raw, img_agent, img_wrist):
    """numpy 图外预处理（手册 2.3 落位表）"""
    q = (qpos_raw - qm) / qs
    imgs = np.stack([img_agent, img_wrist])                       # (2,84,84,3) uint8
    imgs = imgs.astype(np.float32) / 255.0
    imgs = (imgs - IMAGENET_MEAN) / IMAGENET_STD
    imgs = imgs.transpose(0, 3, 1, 2)                             # (2,3,84,84) CHW
    return q.astype(np.float32), imgs.astype(np.float32)

# ---------- 取 50 组真实观测（跨 episode 均匀抽） ----------
f = h5py.File(f'{DATA}/episode_0.hdf5', 'r')  # 先探长度
obs_list = []
for ep in range(0, 200, 4):                    # 50 个 episode
    with h5py.File(f'{DATA}/episode_{ep}.hdf5', 'r') as g:
        T = g['action'].shape[0]
        t = (ep * 7) % T                       # 每集内也错开时刻
        qpos_raw = np.concatenate([g['observations/qpos'][t][:3],   # eef_pos
                                   g['observations/qpos'][t][3:7],  # eef_quat
                                   g['observations/qpos'][t][7:9]]) # gripper
        obs_list.append(prep_obs(qpos_raw,
                                 g['observations/images/agentview'][t],
                                 g['observations/images/robot0_eye_in_hand'][t]))
f.close()

# ---------- 两侧推理 ----------
policy_config = dict(lr=1e-5, num_queries=64, kl_weight=10, hidden_dim=512, dim_feedforward=3200,
                     lr_backbone=1e-5, backbone='resnet18', enc_layers=4, dec_layers=7, nheads=8,
                     camera_names=['agentview', 'robot0_eye_in_hand'],
                     state_dim=7, qpos_dim=9)
policy = ACTPolicy(policy_config)
policy.load_state_dict(torch.load(CKPT, map_location='cpu'))
policy.cuda().eval()
sess = ort.InferenceSession(ONNX, providers=['CPUExecutionProvider'])

diffs, pt_norms = [], []
with torch.no_grad():
    for q, imgs in obs_list:
        qt = torch.from_numpy(q).cuda().float().unsqueeze(0)
        it = torch.from_numpy(imgs).cuda().float().unsqueeze(0)
        a_pt = policy.model(qt, it, None)[0].cpu().numpy()               # (1,64,7) 推理分支
        a_ort = sess.run(['action_chunk'], {'qpos': q[None], 'image': imgs[None]})[0]
        diffs.append(np.abs(a_pt - a_ort).max())
        pt_norms.append(np.abs(a_pt).max())

diffs, pt_norms = np.array(diffs), np.array(pt_norms)
print(f'样本数: {len(obs_list)}（真实观测，跨 50 个 episode）')
print(f'PyTorch 输出幅值 max|a|: {pt_norms.max():.3f}')
print(f'L1 对齐 max|Δ| 全体: {diffs.max():.2e}（判据 <1e-3）')
print(f'L1 对齐 max|Δ| 均值: {diffs.mean():.2e}')
print('✅ L1 通过' if diffs.max() < 1e-3 else '❌ L1 未过——按坑位#9 排查: opset→eval→预处理双做/漏做→dtype')
