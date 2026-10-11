"""E3 Step1: ACT(PyTorch) → ONNX 导出（手册 experiment_E3.md §3.2）

要点（对照坑位 #1/#2/#3）：
  - InferenceWrapper：只留推理路径，forward 只返回 a_hat（剥掉 is_pad 与 [mu,logvar]=None）
  - 归一化全部图外（numpy 预处理）：图内输入 = 已 z-score 的 qpos(1,9) + 已 /255+ImageNet 的图像(1,2,3,84,84)
  - 固定 shape（batch=1）、opset 17、eval + no_grad
产物:
  - /mnt/apfs/workplace/act/e3/act_lift_ph.onnx
  - /mnt/apfs/workplace/act/e3/export_meta.json（shape 表 + 归一化常量，给 e3_align/e3_infer 用）
"""
import argparse
import json
import os
import sys

import numpy as np
import torch

ap = argparse.ArgumentParser()
ap.add_argument('--ckpt', default='/mnt/apfs/workplace/act/ckpt_lift_ph_v2/policy_epoch_2400_seed_0.ckpt')
ap.add_argument('--out-dir', default='/mnt/apfs/workplace/act/e3')
args = ap.parse_args()                       # 先解析自己的参数（官方 build 会 parse 进程 argv）

sys.path.insert(0, '/mnt/apfs/workplace/act')
sys.argv = [sys.argv[0], '--ckpt_dir', 'x', '--policy_class', 'ACT', '--task_name', 'x',
            '--seed', '0', '--num_epochs', '0']   # 垫最小满足集（E2 已踩：官方 build parse argv）
from policy import ACTPolicy                    # noqa: E402
import torch.nn as nn                           # noqa: E402

# ---------- 架构参数必须与训练逐字一致（E2 冻结口径） ----------
policy_config = dict(lr=1e-5, num_queries=64, kl_weight=10, hidden_dim=512, dim_feedforward=3200,
                     lr_backbone=1e-5, backbone='resnet18', enc_layers=4, dec_layers=7, nheads=8,
                     camera_names=['agentview', 'robot0_eye_in_hand'],
                     state_dim=7, qpos_dim=9)


class InferenceWrapper(nn.Module):
    """CVAE 推理路径封装：z=0、encoder 旁路（detr_vae.py:111-113），只返回 a_hat"""

    def __init__(self, policy):
        super().__init__()
        self.model = policy.model  # DETRVAE

    def forward(self, qpos, image):
        # 调 DETRVAE.forward 的推理分支（actions=None）→ (a_hat, is_pad_hat, [None, None])
        a_hat, _, _ = self.model(qpos, image, None)
        return a_hat  # (1, 64, 7) z-score 空间（反标准化在图外 numpy）


policy = ACTPolicy(policy_config)
policy.load_state_dict(torch.load(args.ckpt, map_location='cpu'))  # E2 已踩：裸 state_dict
wrapper = InferenceWrapper(policy).cuda().eval()

os.makedirs(args.out_dir, exist_ok=True)
onnx_path = os.path.join(args.out_dir, 'act_lift_ph.onnx')

qpos = torch.randn(1, 9).cuda()                    # 已 z-score 空间的假输入（trace 用）
img = torch.randn(1, 2, 3, 84, 84).cuda()          # 已 /255+ImageNet 空间
with torch.no_grad():
    torch.onnx.export(wrapper, (qpos, img), onnx_path,
                      input_names=['qpos', 'image'],
                      output_names=['action_chunk'],
                      opset_version=17,
                      do_constant_folding=True)

# L0：结构校验
import onnx                                       # noqa: E402
m = onnx.load(onnx_path)
onnx.checker.check_model(m)
n_nodes = len(m.graph.node)
ins = [(i.name, [d.dim_value for d in i.type.tensor_type.shape.dim]) for i in m.graph.input]
outs = [(o.name, [d.dim_value for d in o.type.tensor_type.shape.dim]) for o in m.graph.output]
print(f'✅ 导出+checker 通过: {onnx_path}（{os.path.getsize(onnx_path)/1e6:.1f}MB, {n_nodes} nodes）')
print('输入:', ins)
print('输出:', outs)

# 预处理常量落盘（图外 numpy 用；qpos/action 统计量在 ckpt 目录 dataset_stats.pkl）
meta = dict(
    input=dict(qpos=[1, 9], image=[1, 2, 3, 84, 84]),
    output=dict(action_chunk=[1, 64, 7]),
    preprocess=dict(  # 图外三步（顺序不可换）
        image='/255 → ImageNet(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])，HWC→CHW，相机序 [agentview, eye_in_hand]',
        qpos='z-score（dataset_stats.pkl: qpos_mean/qpos_std）',
        post='action_chunk × action_std + action_mean（z-score 反变换）'),
    note='数值全部 float32；batch 恒为 1（部署形态）')
with open(os.path.join(args.out_dir, 'export_meta.json'), 'w') as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)
print('✅ export_meta.json 落盘')
