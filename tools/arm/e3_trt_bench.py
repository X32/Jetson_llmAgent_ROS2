"""E3 Step2/3: TRT 引擎 L2/L3 对齐 + 延迟实测（手册 §4.3/§5.1）

设计：用 torch 管 CUDA 显存/流/计时（免 pycuda 依赖）——buffer = torch tensor，
       context.execute_v2 吃 data_ptr()，cuda.Event 计时。
口径：延迟 = 图外预处理后 → action_chunk 出来（纯前向），warmup 50 + N=500；
      与 PyTorch 对比时另测一版 PT 纯前向（同口径，E2 的 18.2ms 含张量准备，见记录表口径行）。
运行环境同 e3_build_engine.py（LD_LIBRARY_PATH 两行）。
"""
import pickle
import sys
import time

import numpy as np
import torch

sys.path.insert(0, '/mnt/apfs/workplace/act')
sys.argv = [sys.argv[0], '--ckpt_dir', 'x', '--policy_class', 'ACT', '--task_name', 'x',
            '--seed', '0', '--num_epochs', '0']
from policy import ACTPolicy  # noqa: E402
import h5py                    # noqa: E402
import tensorrt as trt         # noqa: E402

CKPT = '/mnt/apfs/workplace/act/ckpt_lift_ph_v2/policy_epoch_2400_seed_0.ckpt'
STATS = '/mnt/apfs/workplace/act/ckpt_lift_ph_v2/dataset_stats.pkl'
DATA = '/mnt/apfs/workplace/act/data/lift_ph_act'
E3 = '/mnt/apfs/workplace/act/e3'

stats = pickle.load(open(STATS, 'rb'))
qm, qs = stats['qpos_mean'].astype(np.float32), stats['qpos_std'].astype(np.float32)
IM_MEAN = np.array([0.485, 0.456, 0.406], np.float32); IM_STD = np.array([0.229, 0.224, 0.225], np.float32)

def prep(ep, t):
    with h5py.File(f'{DATA}/episode_{ep}.hdf5', 'r') as g:
        q = g['observations/qpos'][t]
        imgs = np.stack([g['observations/images/agentview'][t],
                         g['observations/images/robot0_eye_in_hand'][t]]).astype(np.float32) / 255.0
    imgs = ((imgs - IM_MEAN) / IM_STD).transpose(0, 3, 1, 2)
    # [坑位#12] transpose 后是 strided 视图：直接给 TRT data_ptr 会按连续布局误读（实测余弦-0.97 的元凶）
    return np.ascontiguousarray(((q - qm) / qs).astype(np.float32)), np.ascontiguousarray(imgs.astype(np.float32))

obs = [prep(ep, (ep * 7) % 64) for ep in range(0, 200, 4)]   # 与 e3_align 同一组 50 观测

# ---------- PyTorch 参照（同卡同输入） ----------
policy_config = dict(lr=1e-5, num_queries=64, kl_weight=10, hidden_dim=512, dim_feedforward=3200,
                     lr_backbone=1e-5, backbone='resnet18', enc_layers=4, dec_layers=7, nheads=8,
                     camera_names=['agentview', 'robot0_eye_in_hand'], state_dim=7, qpos_dim=9)
policy = ACTPolicy(policy_config)
policy.load_state_dict(torch.load(CKPT, map_location='cpu'))
policy.cuda().eval()
ref = []
with torch.no_grad():
    for q, im in obs:
        a = policy.model(torch.from_numpy(q).cuda()[None], torch.from_numpy(im).cuda()[None], None)[0]
        ref.append(a.cpu().numpy())
ref = np.array(ref)

# ---------- TRT 双引擎 ----------
logger = trt.Logger(trt.Logger.ERROR)

def run_engine(path, inputs):
    with open(path, 'rb') as f, trt.Runtime(logger) as rt:
        eng = rt.deserialize_cuda_engine(f.read())
    ctx = eng.create_execution_context()
    outs = []
    for q, im in inputs:
        d_in0 = torch.from_numpy(q).cuda()[None]; d_in1 = torch.from_numpy(im).cuda()[None]
        d_out = torch.empty(1, 64, 7, device='cuda')
        ctx.execute_v2([d_in0.data_ptr(), d_in1.data_ptr(), d_out.data_ptr()])
        outs.append(d_out.cpu().numpy())
    return np.array(outs), ctx, eng

fp32, ctx32, eng32 = run_engine(f'{E3}/act_fp32.engine', obs)
fp16, ctx16, eng16 = run_engine(f'{E3}/act_fp16.engine', obs)

def report(tag, out):
    d = np.abs(out - ref)
    cos = np.sum(out * ref, -1) / (np.linalg.norm(out, axis=-1) * np.linalg.norm(ref, axis=-1) + 1e-12)
    print(f'{tag}: max|Δ|={d.max():.2e}  余弦min={cos.min():.6f}  相对误差max='
          f'{(d/(np.abs(ref)+1e-6)).max():.2e}')

print(f'== L2/L3 对齐（50 组真实观测，vs PyTorch 同卡参照）==')
report('TRT-FP32', fp32)
report('TRT-FP16', fp16)

# ---------- 延迟：cuda.Event 包夹，warmup50 + N=500 ----------
def bench(ctx, eng, n=500):
    q, im = obs[0]
    d_in0 = torch.from_numpy(q).cuda()[None]; d_in1 = torch.from_numpy(im).cuda()[None]
    d_out = torch.empty(1, 64, 7, device='cuda')
    names = [eng.get_binding_name(i) for i in range(eng.num_bindings)]
    for _ in range(50):
        ctx.execute_v2([d_in0.data_ptr(), d_in1.data_ptr(), d_out.data_ptr()])
    ev = [(torch.cuda.Event(True), torch.cuda.Event(True)) for _ in range(n)]
    torch.cuda.synchronize()
    for s, e in ev:
        s.record(); ctx.execute_v2([d_in0.data_ptr(), d_in1.data_ptr(), d_out.data_ptr()]); e.record()
    torch.cuda.synchronize()
    ts = np.array([s.elapsed_time(e) for s, e in ev])
    return ts

def bench_pt(n=500):
    q, im = obs[0]
    d_in0 = torch.from_numpy(q).cuda()[None]; d_in1 = torch.from_numpy(im).cuda()[None]
    with torch.no_grad():
        for _ in range(50):
            policy.model(d_in0, d_in1, None)
        ev = [(torch.cuda.Event(True), torch.cuda.Event(True)) for _ in range(n)]
        torch.cuda.synchronize()
        for s, e in ev:
            s.record(); policy.model(d_in0, d_in1, None); e.record()
        torch.cuda.synchronize()
    return np.array([s.elapsed_time(e) for s, e in ev])

print(f'\n== 延迟实测（图外预处理后 → chunk 输出，cuda.Event 包夹，warmup50+N=500）==')
for tag, fn in [('PyTorch(纯前向,同口径)', bench_pt),
                ('TRT-FP32', lambda: bench(ctx32, eng32)),
                ('TRT-FP16', lambda: bench(ctx16, eng16))]:
    ts = fn()
    print(f'{tag:28s}: mean={ts.mean():6.2f}ms p50={np.percentile(ts,50):6.2f} p95={np.percentile(ts,95):6.2f}')
