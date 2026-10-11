"""E6 Step1: 导出跨机对齐夹具 e6_fixture.npz（PC 一次性，手册 §四）

内容（全部 float32，不批维）:
  obs_qpos(50,9)  obs_img(50,2,3,84,84)  ← 已完成全部图外预处理（z-score+ImageNet+CHW）
  ref_chunk(50,64,7)                     ← PC TRT-FP32 引擎原始输出（z-score 空间参考答案）
采样: 与 e3_align/e3_trt_bench 同一组 50 观测（ep=range(0,200,4), t=(ep*7)%64）
      ——两边共用同一份输入和答案，板上一切对齐测试以此为准

运行（环境同 e3_trt_bench.py）:
  unset PYTHONPATH
  export LD_LIBRARY_PATH=/mnt/apfs/workplace/trt-862/lib:/mnt/apfs/workplace/venvs/act/lib/python3.10/site-packages/torch/lib
  /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e6_make_fixture.py
"""
import pickle
import sys

import numpy as np

sys.path.insert(0, '/mnt/apfs/workplace/act')
sys.argv = [sys.argv[0], '--ckpt_dir', 'x', '--policy_class', 'ACT', '--task_name', 'x',
            '--seed', '0', '--num_epochs', '0']
import h5py                    # noqa: E402
import tensorrt as trt         # noqa: E402
import torch                   # noqa: E402

STATS = '/mnt/apfs/workplace/act/ckpt_lift_ph_v2/dataset_stats.pkl'   # 部署线 = v2（E5 同源）
DATA = '/mnt/apfs/workplace/act/data/lift_ph_act'
ENGINE = '/mnt/apfs/workplace/act/e3/act_fp32.engine'
OUT = '/mnt/apfs/workplace/act/e6/e6_fixture.npz'

stats = pickle.load(open(STATS, 'rb'))
qm, qs = stats['qpos_mean'].astype(np.float32), stats['qpos_std'].astype(np.float32)
IM_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
IM_STD = np.array([0.229, 0.224, 0.225], np.float32)


def prep(ep, t):
    """与 e3_trt_bench.prep 逐字同款（保证与 E3 对齐的是同一组观测）"""
    with h5py.File(f'{DATA}/episode_{ep}.hdf5', 'r') as g:
        q = g['observations/qpos'][t]
        imgs = np.stack([g['observations/images/agentview'][t],
                         g['observations/images/robot0_eye_in_hand'][t]]).astype(np.float32) / 255.0
    imgs = ((imgs - IM_MEAN) / IM_STD).transpose(0, 3, 1, 2)
    # [E3 坑位#12] transpose 后是 strided 视图，必须连续化
    return np.ascontiguousarray(((q - qm) / qs).astype(np.float32)), np.ascontiguousarray(imgs.astype(np.float32))


obs = [prep(ep, (ep * 7) % 64) for ep in range(0, 200, 4)]   # 50 组

# ---------- PC TRT-FP32 引擎出参考答案 ----------
logger = trt.Logger(trt.Logger.ERROR)
with open(ENGINE, 'rb') as f, trt.Runtime(logger) as rt:
    eng = rt.deserialize_cuda_engine(f.read())
ctx = eng.create_execution_context()
outs = []
for q, im in obs:
    d_q = torch.from_numpy(q).cuda()[None]
    d_i = torch.from_numpy(im).cuda()[None]
    d_o = torch.empty(1, 64, 7, device='cuda')
    ctx.execute_v2([d_q.data_ptr(), d_i.data_ptr(), d_o.data_ptr()])
    outs.append(d_o.cpu().numpy()[0])
ref = np.asarray(outs, dtype=np.float32)

np.savez(OUT,
         obs_qpos=np.asarray([o[0] for o in obs], dtype=np.float32),
         obs_img=np.asarray([o[1] for o in obs], dtype=np.float32),
         ref_chunk=ref,
         meta=np.array(f'engine={ENGINE} stats={STATS} sample=ep0..196@t(ep*7)%64 (e3 同款)'))
print(f'saved {OUT}: obs_qpos{ref.shape and ""} 50 组, ref_chunk {ref.shape}')
