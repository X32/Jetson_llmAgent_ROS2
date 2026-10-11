"""E2 考卷·活窗口变体：e2_eval.py 逐字复用 + qpos 镜像广播（不覆盖冻结原脚本）

评测协议（开局/horizon/成功判定/temporal/make_obs/后端三选）与 e2_eval.py 完全一致，
仅旁路加一件事：每步把全量 qpos（nq=16：臂7+爪2+方块自由关节7）发到 /e5/mirror，
由**独立进程**的 e7_mirror_viewer.py 开原生 MuJoCo 窗口实时渲染——坑位#15 终解部件
直接复用（EGL 离屏与 GLFW 窗口同进程互斥，窗口必须独立进程）。
默认 --record 0（不写 mp4；要看回放再手动给 --record N）。

结构总览（六阶段，正文有分节横幅）：
  阶段0 参数 + 模型/统计量加载      —— 坑#19 垫 argv、坑#11 选档纪律
  阶段1 搭考场（robosuite Lift）    —— 坑#7 照数据集出生证明建环境
  阶段2 [live] qpos 镜像广播        —— 本变体唯一新增段（坑#15 独立进程窗口）
  阶段3 预处理工厂 make_obs         —— pt/trt 两套口径，坑#12 连续化
  阶段4 可选后端装备（trt/remote）  —— E3 引擎 / E6 DDS-RPC（seq/超时/三振）
  阶段5 主考试循环（看→想→动→判→直播）+ 阶段6 结账打印

用法（两个终端，建议先开窗口）：
  # 终端1（窗口）：
  source /opt/ros/humble/setup.bash
  /mnt/apfs/workplace/venvs/act/bin/python /mnt/apfs/workplace/ROS2/tools/arm/e7_mirror_viewer.py

  # 终端2（考卷）：
  cd /mnt/apfs/workplace/act
  unset PYTHONPATH; source /opt/ros/humble/setup.bash
  MUJOCO_GL=egl /mnt/apfs/workplace/venvs/act/bin/python /mnt/apfs/workplace/ROS2/tools/arm/e2_eval_live.py \
      --ckpt_dir /mnt/apfs/workplace/act/ckpt_lift_ph_v2 \
      --ckpt policy_epoch_2400_seed_0.ckpt --episodes 3 --temporal
"""
import argparse
import os
import pickle
import sys
import time

import numpy as np
import torch

# ==================== 阶段0 · 参数 + 模型加载 ====================
ap = argparse.ArgumentParser()
ap.add_argument('--ckpt_dir', default='/mnt/apfs/workplace/act/ckpt_lift_ph')
ap.add_argument('--ckpt', default='policy_best.ckpt', help='ckpt 文件名（可指后期存档——坑位#11：按成功率选档，不信 val loss）')
ap.add_argument('--episodes', type=int, default=20)      # 正式口径 20；快评随意（3 集 0/3 是 25% 策略的正常涨落）
ap.add_argument('--temporal', action='store_true', help='时间集成（每步查询+指数加权）')
ap.add_argument('--query-every', type=int, default=0, help='无集成时每 N 步查一次（0=每 chunk 一次）')
ap.add_argument('--horizon', type=int, default=300)      # 每集步数上限（成功集 39-48 步就收卷，失败集顶满 300）
ap.add_argument('--record', type=int, default=0, help='[live 变体默认 0] 录像前 N 个成功 episode（原版默认 1）')
ap.add_argument('--seed0', type=int, default=1000)
ap.add_argument('--backend', choices=['pt', 'trt', 'remote'], default='pt',
                help='pt=PyTorch | trt=TensorRT 引擎（E3 L4 复测）| remote=Jetson DDS 推理服务（E6）')
ap.add_argument('--engine', default='/mnt/apfs/workplace/act/e3/act_fp32.engine', help='trt 后端的引擎文件')
args = ap.parse_args()                                   # 先解析自己的参数

# ---------- 策略加载（架构参数必须与训练逐字一致——坑位#19 同源） ----------
# remote 后端（E6）不加载本地模型：推理在 Jetson，本地只需 stats 反标准化 + policy_config
# 这套 config 就是 E2 训练时的超参照抄：chunk k=64（坑#19：k≤轨迹长）、qpos 9 维、action 7 维
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
    policy.cuda().eval()           # eval 模式：关 dropout/BN 更新——E2 五问#2 的推理分支（z=0）
with open(os.path.join(args.ckpt_dir, 'dataset_stats.pkl'), 'rb') as fph:
    stats = pickle.load(fph)       # 训练集的 qpos/action 均值方差——反标准化必需，缺了权重就废
a_mean, a_std = stats['action_mean'], stats['action_std']

# ==================== 阶段1 · 搭考场（照数据集出生证明建——坑位#7） ====================
import robosuite                                        # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402

env = robosuite.make(
    'Lift', robots=['Panda'],
    controller_configs=load_controller_config(default_controller='OSC_POSE'),  # 必须同款控制器：
    # 不显式指定默认是 JointVelocity 8 维——动作语义整个错位还不报错（坑#7 主坑）
    has_renderer=False, has_offscreen_renderer=True, use_camera_obs=True,     # 无窗口、EGL 离屏：
    # 每步渲染 84² 策略观测必需（EGL 与 GLFW 同进程互斥=坑#15，所以窗口外包给阶段2）
    camera_names=['agentview', 'robot0_eye_in_hand'],  # 与训练数据同款双相机
    camera_heights=84, camera_widths=84,               # 与训练数据同款分辨率
    ignore_done=True,                                  # 不让环境自己提前收卷（成功判定我们自己调 _check_success）
)

# ==================== 阶段2 · [live 唯一新增段] qpos 镜像广播 ====================
# 坑位#15 终解复用：本进程离不开 EGL（策略观测），原生窗口必须住在另一个进程里。
# 链路：本脚本 --(DDS /e5/mirror, Float64MultiArray=qpos16)--> e7_mirror_viewer.py（GLFW 窗口）
import rclpy                                            # noqa: E402
from std_msgs.msg import Float64MultiArray              # noqa: E402

rclpy.init()
_mnode = rclpy.create_node('e2_eval_live')
_pub_mirror = _mnode.create_publisher(Float64MultiArray, '/e5/mirror', 10)
time.sleep(1.5)                                         # DDS 发现宽限（另一终端的 viewer 先开更稳）


def mirror_pub():
    """全量 qpos（含方块自由关节）广播给 e7_mirror_viewer.py；窗口没开时零成本"""
    _pub_mirror.publish(Float64MultiArray(data=env.sim.data.qpos.tolist()))


print('[live] /e5/mirror 广播已开（配合 e7_mirror_viewer.py 独立进程窗口）', flush=True)


# ==================== 阶段3 · 预处理工厂：robosuite 裸观测 → 模型输入 ====================
def make_obs(obs):
    """robosuite obs → ACT 输入。pt 后端：图像 /255（ImageNet 归一化在 policy 内）；
    trt 后端：图外做全预处理（/255+ImageNet+z-score，见 e3 手册 2.3 落位表）"""
    # (1) qpos：三个分散字段拼成训练时的 9 维本体态（eef_pos3 + eef_quat4 + gripper2）
    qpos = np.concatenate([obs['robot0_eef_pos'], obs['robot0_eef_quat'],
                           obs['robot0_gripper_qpos']]).astype(np.float32)
    qpos = (qpos - stats['qpos_mean']) / stats['qpos_std']   # (2) z-score（用训练集统计量）
    imgs = np.stack([obs['agentview_image'], obs['robot0_eye_in_hand_image']])  # (2,84,84,3)
    if args.backend in ('trt', 'remote'):
        # remote 与 trt 逐字同一份全预处理（z-score+ImageNet+CHW+连续化）——
        # L4 对照唯一变量 = 引擎+链路（手册 2.3 设计 a）
        IM_MEAN = np.array([0.485, 0.456, 0.406], np.float32)   # ImageNet 三通道均值
        IM_STD = np.array([0.229, 0.224, 0.225], np.float32)    # ImageNet 三通道方差
        imgs = ((imgs.astype(np.float32) / 255.0) - IM_MEAN) / IM_STD
        imgs = np.ascontiguousarray(imgs.transpose(0, 3, 1, 2))   # [坑位#12] strided → 连续：
        # transpose 只换元数据不搬数据，裸指针(data_ptr)给 TRT 会被按连续内存误读（余弦-0.97 案）
        if args.backend == 'remote':
            return np.ascontiguousarray(qpos.astype(np.float32)[None]), \
                   np.ascontiguousarray(imgs.astype(np.float32)[None])   # numpy：直接序列化发字节
        return torch.from_numpy(np.ascontiguousarray(qpos)).cuda().unsqueeze(0), \
               torch.from_numpy(imgs).cuda().float().unsqueeze(0)        # torch：本地引擎执行
    imgs = torch.from_numpy(imgs.copy()).cuda().float().unsqueeze(0) / 255.0  # pt：只做 /255，
    imgs = torch.einsum('k h w c -> k c h w', imgs[0]).unsqueeze(0)      # ImageNet 在 policy 内做
    # （pt 走 einsum 转轴交给 torch，它会自己处理布局，没有坑#12 的裸指针问题）
    return torch.from_numpy(qpos).cuda().float().unsqueeze(0), imgs

# ==================== 阶段4 · 可选后端装备 ====================
# ---------- TRT 后端加载（E3 L4：同一协议复测，仅换推理后端） ----------
trt_ctx = None
if args.backend == 'trt':
    import tensorrt as trt                              # LD_LIBRARY_PATH 见 e3_build_engine.py 头注
    with open(args.engine, 'rb') as fe, trt.Logger(trt.Logger.ERROR) as tlog, \
         trt.Runtime(tlog) as trt_rt:
        trt_engine = trt_rt.deserialize_cuda_engine(fe.read())   # .engine 绑定 GPU 架构+TRT 版本
    trt_ctx = trt_engine.create_execution_context()
    trt_out = torch.empty(1, policy_config['num_queries'], 7, device='cuda')  # 输出缓冲 (1,64,7)

# ---------- remote 后端（E6）：DDS topic-pair RPC → Jetson 推理服务 ----------
if args.backend == 'remote':
    import array as _array
    from std_msgs.msg import UInt8MultiArray

    _rnode = rclpy.create_node('e6_eval_remote')
    _obs_pub = _rnode.create_publisher(UInt8MultiArray, '/act/obs', 10)    # 请求话题
    _inbox = {}                                        # seq → chunk(1,64,7) f32（应答信箱）

    def _on_chunk(m):
        raw = bytes(m.data)                            # UInt8MultiArray → array('B') 直转
        s = int(np.frombuffer(raw[:4], '<u4')[0])      # 头 4 字节 = seq（防串包配对号）
        _inbox[s] = np.frombuffer(raw[4:], '<f4').reshape(1, policy_config['num_queries'], 7).copy()

    _rnode.create_subscription(UInt8MultiArray, '/act/chunk', _on_chunk, 10)  # 应答话题
    _rseq = 0
    _rfails = 0                                        # 连续整集超时计数（坑位#9：连 3 停评）

    def _send(s, q_np, im_np):
        m = UInt8MultiArray()
        m.data = _array.array('B', np.array([s], '<u4').tobytes()
                              + q_np.astype('<f4').tobytes() + im_np.astype('<f4').tobytes())  # seq+qpos+图
        _obs_pub.publish(m)

    def remote_call(q_np, im_np):
        """发布 obs → 等 seq 匹配 chunk。200ms 超时重发一次；再超时抛 TimeoutError
        （主循环判本集失败、下集自愈——手册 7.3 R3）"""
        global _rseq, _rfails
        _rseq += 1
        _send(_rseq, q_np, im_np)
        for _attempt in (0, 1):                        # 两次机会：首发 + 超时重发 1 次
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 0.2:      # 每轮最多等 200ms
                rclpy.spin_once(_rnode, timeout_sec=0.005)
                if _rseq in _inbox:                    # seq 对上号 = 本次的回包到了
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
        return policy(qpos_t, img_t)                   # pt：ACTPolicy 前向（内含 ImageNet）
    trt_ctx.execute_v2([qpos_t.data_ptr(), img_t.data_ptr(), trt_out.data_ptr()])  # trt：裸指针三进一出
    return trt_out.clone()


# ==================== 阶段5 · 主考试循环（看→想→动→判→直播） ====================
lat_ms = []
# 时间集成的账本：行=查询时刻，列=预测时刻；第 j 行 chunk 写入 [j, j+64) 的对角带，
# 每步取第 t 列 = 所有覆盖到 t 的历史预测，加权平均
all_time_actions = torch.zeros(args.horizon, args.horizon + policy_config['num_queries'], 7).cuda()
succ, rets, rec = [], [], 0

for ep in range(args.episodes):
    obs = env.reset()                                    # robosuite 1.4.1 reset 无 seed 参数；
    mirror_pub()                                         # [live] 开局姿势也镜像一帧
    ep_frames, done_t, ep_ret = [], None, 0             # 连续 reset 内部随机化 → 天然不同开局（坑位#10）
    chunk, t_exec = None, 0                              # chunk=最近一次预测块；t_exec=块内执行到第几步
    for t in range(args.horizon):
        # ---- ① 看：本步观测 → 模型输入 ----
        qpos_t, img_t = make_obs(obs)
        k = policy_config['num_queries']
        # ---- ② 想：要不要重新查询？temporal 开=每步查；关=chunk 吃完才再查 ----
        if args.temporal or chunk is None or (args.query_every and t % args.query_every == 0):
            torch.cuda.synchronize(); t0 = time.perf_counter()   # 包夹计时：GPU 异步，不 synchronize 会测出假 0.2ms
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
        # ---- ③ 取动作：时间集成 or 整块执行 ----
        if args.temporal:                                # 官方时间集成（imitate_episodes.py:250-260 同款）
            all_time_actions[[t], t:t + k] = torch.from_numpy(chunk).cuda()  # 本步预测写入对角带
            afcs = all_time_actions[:, t]               # 取第 t 列：所有覆盖 t 的历史预测
            afcs = afcs[torch.all(afcs != 0, dim=1)]    # 滤掉全零行（= 未覆盖 t 的旧查询/padding）
            w = np.exp(-0.01 * np.arange(len(afcs)))    # 按查询先后 exp(-0.01·i) 衰减（κ=0.01）
            w = torch.from_numpy(w / w.sum()).cuda().unsqueeze(1)   # 归一化成权重
            a = (afcs * w).sum(0).cpu().numpy()         # 加权平均 → 本步最终动作
        else:
            a = chunk[min(t_exec, k - 1)]               # 无集成：顺着 chunk 逐步执行
        # ---- ④ 动：反标准化 → 限幅 → env.step ----
        a = a * a_std + a_mean                           # 反标准化 → OSC [-1,1]
        obs, r, _, _ = env.step(np.clip(a, -1, 1))
        mirror_pub()                                     # [live] 每步广播 qpos → 独立进程窗口
        ep_ret += r
        t_exec += 1
        if rec < args.record:                            # 只有还差录像额度才存帧（默认 0=不存）
            ep_frames.append(obs['agentview_image'].copy())
        # ---- ⑤ 判：物理成功判定，成了收卷 ----
        if env._check_success():                         # cube z > 0.84（lift.py:417，不是想当然的 0.9）
            done_t = t
            break
    # ---- ⑥ 收卷：记成绩 + 可选录像 ----
    ok = done_t is not None
    succ.append(ok); rets.append(ep_ret)
    if ok and rec < args.record and ep_frames:
        import imageio                                    # 录像（6.3）
        imageio.mimwrite(os.path.join(args.ckpt_dir, f'e2_success_ep{ep}.mp4'),
                         ep_frames, fps=20, quality=8)
        rec += 1
    print(f'ep{ep:02d}: {"✅成功" if ok else "❌失败"} @t={done_t} return={ep_ret:.1f}')

# ==================== 阶段6 · 结账 ====================
lat = np.array(lat_ms)
_lat_kind = '远端在环（publish→chunk 到达墙钟，含 P2-P4 链路）' if args.backend == 'remote' \
            else 'chunk 推理（本地）'                     # 口径声明：remote 含链路，不带口径的数不可比
print(f'\n==== E2 评估结果 ====')
print(f'成功率: {sum(succ)}/{args.episodes} = {np.mean(succ):.0%}   (temporal_agg={"开" if args.temporal else "关"})')
print(f'{_lat_kind}: mean={lat.mean():.1f}ms p50={np.percentile(lat,50):.1f}ms p95={np.percentile(lat,95):.1f}ms (N={len(lat)})')
print(f'摊销延迟: {lat.mean()/(64 if not args.query_every else args.query_every):.2f} ms/步')  # chunk 延迟÷64 步

_mnode.destroy_node()
rclpy.shutdown()                                         # [live] 干净退出 DDS
