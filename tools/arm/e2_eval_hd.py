"""【E2-R3·HD】本件 = e2_eval.py（冻结）的孪生：仅相机 84x84→480x640、默认 ckpt_dir→ckpt_lift_ph_hd，其余逐字同源（坑位#19 同源原则）。

用法（训练完成后）:
  unset PYTHONPATH && MUJOCO_GL=egl python e2_eval.py \
      --ckpt_dir /mnt/apfs/workplace/act/ckpt_lift_ph_hd [--episodes 20] [--temporal]

验收口径（手册 6.2 表）:
  成功率      : _check_success()（lift.py:417，阈值 table+0.04=0.84）
  chunk 延迟  : torch.cuda.synchronize() 包夹，N 次均值（Day8 方法论）
  摊销延迟    : chunk 推理 ms ÷ 每 chunk 实际执行步数（两档：每步查 vs 每 k/4 步查）
  录像        : 成功 episode 存 mp4（agentview 帧 + imageio-ffmpeg）
"""
import argparse
import os
import pickle
import sys
import time

import numpy as np
import torch

ap = argparse.ArgumentParser()
ap.add_argument('--ckpt_dir', default='/mnt/apfs/workplace/act/ckpt_lift_ph_hd')
ap.add_argument('--ckpt', default='policy_best.ckpt', help='ckpt 文件名（可指后期存档——坑位#11：按成功率选档，不信 val loss）')
ap.add_argument('--episodes', type=int, default=20)
ap.add_argument('--temporal', action='store_true', help='时间集成（每步查询+指数加权）')
ap.add_argument('--query-every', type=int, default=0, help='无集成时每 N 步查一次（0=每 chunk 一次）')
ap.add_argument('--horizon', type=int, default=300)
ap.add_argument('--record', type=int, default=1, help='录像前 N 个成功 episode')
ap.add_argument('--seed0', type=int, default=1000)
ap.add_argument('--backend', choices=['pt', 'trt', 'remote'], default='pt',
                help='pt=PyTorch | trt=TensorRT 引擎（E3 L4 复测）| remote=Jetson DDS 推理服务（E6）')
ap.add_argument('--engine', default='/mnt/apfs/workplace/act/e3/act_fp32.engine', help='trt 后端的引擎文件')
args = ap.parse_args()                                   # 先解析自己的参数

# ---------- 策略加载（架构参数必须与训练逐字一致——坑位#19 同源） ----------
# remote 后端（E6）不加载本地模型：推理在 Jetson，本地只需 stats 反标准化 + policy_config
policy_config = dict(clr=1e-5, num_queries=64, kl_weight=10, hidden_dim=512, dim_feedforward=3200,
                     lr_backbone=1e-5, backbone='resnet18', enc_layers=4, dec_layers=7, nheads=8,
                     camera_names=['agentview', 'robot0_eye_in_hand'],
                     state_dim=7, qpos_dim=9)
if args.backend != 'remote':
    sys.path.insert(0, '/mnt/apfs/workplace/act')       # ACTPolicy / detr
    # 官方 build_ACT_model_and_optimizer 会 parse 当前进程 argv 再用 override 覆盖（上游设计），
    # 本脚本自己的参数与它必需项不符 → 垫一个最小满足集，构造完模型即无副作用
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

# ---------- 环境：照数据集 env_args 建（OSC_POSE、480×640 双相机）——坑位#7 ----------
import robosuite                                        # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402

env = robosuite.make(
    'Lift', robots=['Panda'],
    controller_configs=load_controller_config(default_controller='OSC_POSE'),
    has_renderer=False, has_offscreen_renderer=True, use_camera_obs=True,
    camera_names=['agentview', 'robot0_eye_in_hand'],
    camera_heights=480, camera_widths=640,
    ignore_done=True,
)


def make_obs(obs):
    """robosuite obs → ACT 输入。pt 后端：图像 /255（ImageNet 归一化在 policy 内）；
    trt 后端：图外做全预处理（/255+ImageNet+z-score，见 e3 手册 2.3 落位表）"""
    qpos = np.concatenate([obs['robot0_eef_pos'], obs['robot0_eef_quat'],
                           obs['robot0_gripper_qpos']]).astype(np.float32)
    qpos = (qpos - stats['qpos_mean']) / stats['qpos_std']
    imgs = np.stack([obs['agentview_image'], obs['robot0_eye_in_hand_image']])  # (2,480,640,3)
    if args.backend in ('trt', 'remote'):
        # remote 与 trt 逐字同一份全预处理（z-score+ImageNet+CHW+连续化）——
        # L4 对照唯一变量 = 引擎+链路（手册 2.3 设计 a）
        IM_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
        IM_STD = np.array([0.229, 0.224, 0.225], np.float32)
        imgs = ((imgs.astype(np.float32) / 255.0) - IM_MEAN) / IM_STD
        imgs = np.ascontiguousarray(imgs.transpose(0, 3, 1, 2))   # [坑位#12] strided → 连续
        if args.backend == 'remote':
            return np.ascontiguousarray(qpos.astype(np.float32)[None]), \
                   np.ascontiguousarray(imgs.astype(np.float32)[None])
        return torch.from_numpy(np.ascontiguousarray(qpos)).cuda().unsqueeze(0), \
               torch.from_numpy(imgs).cuda().float().unsqueeze(0)
    imgs = torch.from_numpy(imgs.copy()).cuda().float().unsqueeze(0) / 255.0
    imgs = torch.einsum('k h w c -> k c h w', imgs[0]).unsqueeze(0)
    return torch.from_numpy(qpos).cuda().float().unsqueeze(0), imgs

# ---------- TRT 后端加载（E3 L4：同一协议复测，仅换推理后端） ----------
trt_ctx = None
if args.backend == 'trt':
    import tensorrt as trt                              # LD_LIBRARY_PATH 见 e3_build_engine.py 头注
    with open(args.engine, 'rb') as fe, trt.Logger(trt.Logger.ERROR) as tlog, \
         trt.Runtime(tlog) as trt_rt:
        trt_engine = trt_rt.deserialize_cuda_engine(fe.read())
    trt_ctx = trt_engine.create_execution_context()
    trt_out = torch.empty(1, policy_config['num_queries'], 7, device='cuda')

# ---------- remote 后端（E6）：DDS topic-pair RPC → Jetson 推理服务 ----------
if args.backend == 'remote':
    import array as _array
    import rclpy
    from std_msgs.msg import UInt8MultiArray

    rclpy.init()
    _rnode = rclpy.create_node('e6_eval_remote')
    _obs_pub = _rnode.create_publisher(UInt8MultiArray, '/act/obs', 10)
    _inbox = {}                                        # seq → chunk(1,64,7) f32

    def _on_chunk(m):
        raw = bytes(m.data)                            # UInt8MultiArray → array('B') 直转
        s = int(np.frombuffer(raw[:4], '<u4')[0])
        _inbox[s] = np.frombuffer(raw[4:], '<f4').reshape(1, policy_config['num_queries'], 7).copy()

    _rnode.create_subscription(UInt8MultiArray, '/act/chunk', _on_chunk, 10)
    _rseq = 0
    _rfails = 0                                        # 连续整集超时计数（坑位#9：连 3 停评）

    def _send(s, q_np, im_np):
        m = UInt8MultiArray()
        m.data = _array.array('B', np.array([s], '<u4').tobytes()
                              + q_np.astype('<f4').tobytes() + im_np.astype('<f4').tobytes())
        _obs_pub.publish(m)

    def remote_call(q_np, im_np):
        """发布 obs → 等 seq 匹配 chunk。200ms 超时重发一次；再超时抛 TimeoutError
        （主循环判本集失败、下集自愈——手册 7.3 R3）"""
        global _rseq, _rfails
        _rseq += 1
        _send(_rseq, q_np, im_np)
        for _attempt in (0, 1):
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 0.2:
                rclpy.spin_once(_rnode, timeout_sec=0.005)
                if _rseq in _inbox:
                    _rfails = 0                        # 链路恢复，连败清零
                    return torch.from_numpy(_inbox.pop(_rseq))
            _send(_rseq, q_np, im_np)                  # 超时重发一次
        raise TimeoutError(f'remote seq={_rseq} 超时（含重发 1 次）')


def policy_call(qpos_t, img_t):
    """统一推理入口：pt 走 PyTorch（含 ImageNet），trt 走引擎（输入已全预处理），
    remote 走 DDS → Jetson TRT-FP16（输入已全预处理，numpy）"""
    if args.backend == 'remote':
        return remote_call(qpos_t, img_t)
    if trt_ctx is None:
        return policy(qpos_t, img_t)
    trt_ctx.execute_v2([qpos_t.data_ptr(), img_t.data_ptr(), trt_out.data_ptr()])
    return trt_out.clone()


lat_ms = []
all_time_actions = torch.zeros(args.horizon, args.horizon + policy_config['num_queries'], 7).cuda()
succ, rets, rec = [], [], 0

for ep in range(args.episodes):
    obs = env.reset()                                    # robosuite 1.4.1 reset 无 seed 参数；
    ep_frames, done_t, ep_ret = [], None, 0             # 连续 reset 内部随机化 → 天然不同开局（坑位#10）
    chunk, t_exec = None, 0
    for t in range(args.horizon):
        qpos_t, img_t = make_obs(obs)
        k = policy_config['num_queries']
        if args.temporal or chunk is None or (args.query_every and t % args.query_every == 0):
            torch.cuda.synchronize(); t0 = time.perf_counter()
            try:
                chunk = policy_call(qpos_t, img_t).detach().cpu().numpy().squeeze(0)  # (k,7) z-score 空间
            except TimeoutError as e:                    # remote 链路超时：本集判败、下集自愈（R3）
                print(f'ep{ep:02d} t={t} ❌ {e} — 本集判败')
                _rfails += 1
                if _rfails >= 3:
                    raise RuntimeError('连续 3 集链路超时——判链路故障停评（E6 坑位#9）')
                # 恢复宽限：板端节点重启（引擎反序列化+DDS 重发现实测 ~16-19s）窗口内
                # 不给下集立刻判死——连 3 集停评只应触发于真死链，而非服务重启期
                time.sleep(12)
                break
            torch.cuda.synchronize(); lat_ms.append((time.perf_counter() - t0) * 1e3)
            t_exec = 0
        if args.temporal:                                # 官方时间集成（imitate_episodes.py:250-260 同款）
            all_time_actions[[t], t:t + k] = torch.from_numpy(chunk).cuda()
            afcs = all_time_actions[:, t]
            afcs = afcs[torch.all(afcs != 0, dim=1)]
            w = np.exp(-0.01 * np.arange(len(afcs)))
            w = torch.from_numpy(w / w.sum()).cuda().unsqueeze(1)
            a = (afcs * w).sum(0).cpu().numpy()
        else:
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
        imageio.mimwrite(os.path.join(args.ckpt_dir, f'e2_success_ep{ep}.mp4'),
                         ep_frames, fps=20, quality=8)
        rec += 1
    print(f'ep{ep:02d}: {"✅成功" if ok else "❌失败"} @t={done_t} return={ep_ret:.1f}')

lat = np.array(lat_ms)
_lat_kind = '远端在环（publish→chunk 到达墙钟，含 P2-P4 链路）' if args.backend == 'remote' \
            else 'chunk 推理（本地）'
print(f'\n==== E2 评估结果 ====')
print(f'成功率: {sum(succ)}/{args.episodes} = {np.mean(succ):.0%}   (temporal_agg={"开" if args.temporal else "关"})')
print(f'{_lat_kind}: mean={lat.mean():.1f}ms p50={np.percentile(lat,50):.1f}ms p95={np.percentile(lat,95):.1f}ms (N={len(lat)})')
print(f'摊销延迟: {lat.mean()/(64 if not args.query_every else args.query_every):.2f} ms/步')
