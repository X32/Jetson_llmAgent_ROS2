"""E3-b: g2c ACT（12 维 qpos）→ ONNX 导出 + ORT 对齐（e3_export_onnx.py 的 g2c 版，原脚本不动）

与 e3_export_onnx.py 的差异（就两处）：
  - policy_config.qpos_dim = 12（[R4-g2c] 拼 g2c 向量），ckpt = ckpt_lift_ph_g2c epoch2200
  - 导出后立即做 L1 对齐：ORT vs torch 同输入，max abs diff 必须打印留档
注意：包装器 trace 的是 DETRVAE（policy.py:53-55 的 ImageNet 归一化在 ACTPolicy 层，
不在 DETRVAE 内）→ 图输入 = 已 z-score 的 qpos(1,12) + 已 /255+ImageNet 的图像。
图外预处理清单见 export_meta_g2c.json（与 e2_eval_g2c trt/remote 分支逐字一致）。

用法: /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e3b_export_onnx_g2c.py
产物: /mnt/apfs/workplace/act/e3/act_lift_ph_g2c.onnx + export_meta_g2c.json + parity_g2c.npz
"""
import json
import os
import sys

import numpy as np
import torch

ap = __import__('argparse').ArgumentParser()
ap.add_argument('--ckpt', default='/mnt/apfs/workplace/act/ckpt_lift_ph_g2c/policy_epoch_2200_seed_0.ckpt')
ap.add_argument('--out-dir', default='/mnt/apfs/workplace/act/e3')
args = ap.parse_args()                       # 先解析自己的参数（官方 build 会 parse 进程 argv）

sys.path.insert(0, '/mnt/apfs/workplace/act')
sys.argv = [sys.argv[0], '--ckpt_dir', 'x', '--policy_class', 'ACT', '--task_name', 'x',
            '--seed', '0', '--num_epochs', '0']   # 垫最小满足集（E2 已踩：官方 build parse argv）
from policy import ACTPolicy                    # noqa: E402
import torch.nn as nn                           # noqa: E402

policy_config = dict(clr=1e-5, num_queries=64, kl_weight=10, hidden_dim=512, dim_feedforward=3200,
                     lr_backbone=1e-5, backbone='resnet18', enc_layers=4, dec_layers=7, nheads=8,
                     camera_names=['agentview', 'robot0_eye_in_hand'],
                     state_dim=7, qpos_dim=12)  # [R4-g2c] 12 维（v2 节点逐字同）


class InferenceWrapper(nn.Module):
    """CVAE 推理路径封装：z=0、encoder 旁路，只返回 a_hat（e3 同款）"""

    def __init__(self, policy):
        super().__init__()
        self.model = policy.model              # DETRVAE（不含 ACTPolicy 层的 ImageNet 归一化）

    def forward(self, qpos, image):
        a_hat, _, _ = self.model(qpos, image, None)
        return a_hat                           # (1, 64, 7) z-score 空间


policy = ACTPolicy(policy_config)
policy.load_state_dict(torch.load(args.ckpt, map_location='cpu'))
wrapper = InferenceWrapper(policy).cuda().eval()

os.makedirs(args.out_dir, exist_ok=True)
onnx_path = os.path.join(args.out_dir, 'act_lift_ph_g2c.onnx')
qpos = torch.randn(1, 12).cuda()               # 已 z-score 空间的假输入（trace 用）
img = torch.randn(1, 2, 3, 84, 84).cuda()      # 已 /255+ImageNet 空间
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
ins = [(i.name, [d.dim_value for d in i.type.tensor_type.shape.dim]) for i in m.graph.input]
outs = [(o.name, [d.dim_value for d in o.type.tensor_type.shape.dim]) for o in m.graph.output]
print(f'✅ 导出+checker 通过: {onnx_path}（{os.path.getsize(onnx_path) / 1e6:.1f}MB）')
print('输入:', ins)
print('输出:', outs)

# L1：ORT vs torch 同输入对齐（随机输入，图等价性）
import onnxruntime as ort                          # noqa: E402
sess = ort.InferenceSession(onnx_path, providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
q_np = qpos.cpu().numpy()
i_np = img.cpu().numpy()
with torch.no_grad():
    ref = wrapper(torch.from_numpy(q_np).cuda(), torch.from_numpy(i_np).cuda()).cpu().numpy()
ort_out = sess.run(None, {'qpos': q_np, 'image': i_np})[0]
diff = float(np.abs(ref - ort_out).max())
print(f'L1 对齐: max|torch−ORT| = {diff:.2e}（<1e-3 为过）')
assert diff < 1e-3, 'ORT 与 torch 不齐——查 trace'

np.savez(os.path.join(args.out_dir, 'parity_g2c.npz'), q=q_np, im=i_np, ref=ref)

meta = dict(
    input=dict(qpos=[1, 12], image=[1, 2, 3, 84, 84]),
    output=dict(action_chunk=[1, 64, 7]),
    preprocess=dict(
        image='/255 → ImageNet(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225])，HWC→CHW，相机序 [agentview, eye_in_hand]',
        qpos='z-score（ckpt_lift_ph_g2c/dataset_stats.pkl: qpos_mean/qpos_std，12 维）',
        post='action_chunk × action_std + action_mean（z-score 反变换）'),
    note='图内不含归一化（DETRVAE 直 trace，绕过 ACTPolicy 层 normalize）——图外全预处理；batch 恒 1')
with open(os.path.join(args.out_dir, 'export_meta_g2c.json'), 'w') as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)
print('✅ export_meta_g2c.json 落盘')
