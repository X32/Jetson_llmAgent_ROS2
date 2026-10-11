#!/usr/bin/env python3
"""E5 执行节点（手册 DOC/arm/experiment_E5.md §5.2）：robosuite 身体 + ACT/TRT 小脑

状态机 IDLE→SNAPSHOT→WAIT_GOAL→COORD→EXECUTE→REPORT（手册 2.4/2.6）
- SNAPSHOT：reset（每 task_id 仅一次）→ 768 渲染（flipud 已实测坐实）→ 发 /e5/frame
- WAIT_GOAL：等 /e5/goal，60s 超时；期间 sim 冻结（快照=ACT 首观测的同一状态）
- COORD：坐标链（K⁻¹ 射线 → z=0.825 平面交点）+ 门控（桌面范围/grade）
- EXECUTE：e2_eval 验收过的循环原样搬移（temporal 集成 + _check_success），
  新增：20Hz 节拍、512 显示帧录像、每步非阻塞 poll abort
- REPORT：/e5/result + 视频落盘

线程模型：回调只入队（快），重活全在主循环——EXECUTE 期间用非阻塞 spin_once
收 abort，无嵌套 spin（rclpy 单线程 executor 的重入坑）。

用法（venv + ROS 故意同进程，实测共存 OK——手册 2.6）：
  source /opt/ros/humble/setup.bash && source install/setup.bash
  export LD_LIBRARY_PATH=/mnt/apfs/workplace/trt-862/lib:<venv>/.../torch/lib:$LD_LIBRARY_PATH
  MUJOCO_GL=egl <venv>/python tools/arm/e5_act_node.py --backend trt \
    --engine /mnt/apfs/workplace/act/e3/act_fp32.engine \
    --ckpt_dir /mnt/apfs/workplace/act/ckpt_lift_ph_v2 --ckpt policy_epoch_2400_seed_0.ckpt
  自检（无 VLM/编排，GT 门控）：加 --selftest 3
"""
import argparse
import json
import os
import pickle
import sys
import time
import traceback
from collections import deque

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--backend', choices=['pt', 'trt', 'remote'], default='trt',
                help='remote=Jetson DDS 推理服务（E7，协议/代码逐字同 e2_eval E6 分支）')
ap.add_argument('--live-view', action='store_true',
                help='每步把 qpos 发布到 /e5/mirror，配独立进程原生窗口 tools/arm/e7_mirror_viewer.py（演示用；正式协议不开）')
ap.add_argument('--no-record', action='store_true',
                help='跳过每步 512 显示帧渲染+mp4 落盘（演示模式省 GPU；正式协议不开）')
ap.add_argument('--engine', default='/mnt/apfs/workplace/act/e3/act_fp32.engine')
ap.add_argument('--ckpt_dir', default='/mnt/apfs/workplace/act/ckpt_lift_ph_v2')
ap.add_argument('--ckpt', default='policy_epoch_2400_seed_0.ckpt')
ap.add_argument('--render', type=int, default=768, help='送检渲染边长')
ap.add_argument('--roi-half', type=float, default=0.10,
                help='送检中心窗半宽（世界系 m）。lift.py:313 方块采样±3cm → 0.10 有 3.3× 边际，'
                     '等效 2.5× 变焦（Step1 实测 9.2→2.7cm 的主修复之一）')
ap.add_argument('--send', type=int, default=1000,
                help='送检方形边长。坐标语义在"送检图像素/0-1000"间漂移，送 1000×1000 使两种语义数值恒等')
ap.add_argument('--display', type=int, default=512, help='录像显示帧边长')
ap.add_argument('--hz', type=float, default=20.0, help='控制节拍（步进 pacing）')
ap.add_argument('--horizon', type=int, default=300)
ap.add_argument('--selftest', type=int, default=0, help='GT 门控自检 N 集（ST1，无需 VLM/编排）')
ap.add_argument('--video-dir', default=os.path.join(os.path.dirname(__file__), '..', 'results'))
args = ap.parse_args()

sys.path.insert(0, '/mnt/apfs/workplace/act')
sys.argv = [sys.argv[0], '--ckpt_dir', 'x', '--policy_class', 'ACT', '--task_name', 'x',
            '--seed', '0', '--num_epochs', '0']        # 官方 build 函数 parse argv 的老坑（e2_eval 同款垫片）

import torch                                       # noqa: E402
from policy import ACTPolicy                       # noqa: E402

policy_config = dict(clr=1e-5, num_queries=64, kl_weight=10, hidden_dim=512, dim_feedforward=3200,
                     lr_backbone=1e-5, backbone='resnet18', enc_layers=4, dec_layers=7, nheads=8,
                     camera_names=['agentview', 'robot0_eye_in_hand'],
                     state_dim=7, qpos_dim=9)
K_CHUNK = policy_config['num_queries']

policy = None
if args.backend == 'pt':
    policy = ACTPolicy(policy_config)
    policy.load_state_dict(torch.load(os.path.join(args.ckpt_dir, args.ckpt), map_location='cuda'))
    policy.cuda().eval()
with open(os.path.join(args.ckpt_dir, 'dataset_stats.pkl'), 'rb') as fph:
    stats = pickle.load(fph)
Q_MEAN, Q_STD = stats['qpos_mean'], stats['qpos_std']
A_MEAN, A_STD = stats['action_mean'], stats['action_std']

trt_ctx, trt_out = None, None
if args.backend == 'trt':
    import tensorrt as trt                         # LD_LIBRARY_PATH 见文件头
    with open(args.engine, 'rb') as fe, trt.Logger(trt.Logger.ERROR) as tlog, \
            trt.Runtime(tlog) as trt_rt:
        trt_engine = trt_rt.deserialize_cuda_engine(fe.read())
    trt_ctx = trt_engine.create_execution_context()
    trt_out = torch.empty(1, K_CHUNK, 7, device='cuda')


_REMOTE = None   # E5ActNode 实例（remote 后端时由 main() 注入；见类内 remote 基建）

# --live-view 方案（坑位#15 终版）：原生 GLFW 窗口与 egl 离屏上下文**同进程**互斥，
# 但**独立进程**里 GLFW 单独跑完全健康（vtest1 实证）。所以窗口搬去独立进程
# tools/arm/e7_mirror_viewer.py：本进程每步把 qpos 发布到 /e5/mirror（Float64MultiArray），
# 镜像进程自建同款 robosuite 环境（离屏全关）→ 贴 qpos → mj_forward → viewer.sync()，
# 得到可旋转视角的原生 MuJoCo 窗口。20Hz×16 floats，DDS 负载可忽略。
MIRROR_TOPIC = '/e5/mirror'


class Aborted(Exception):
    """remote 等待中收到 abort——区别于 TimeoutError：不吃三振、不睡宽限（坑位#2）"""


def policy_call(qpos_t, img_t):
    if args.backend == 'remote':
        return _REMOTE.remote_call(qpos_t, img_t)      # numpy 进 → torch(1,64,7) CPU 出
    if trt_ctx is None:
        return policy(qpos_t, img_t)
    trt_ctx.execute_v2([qpos_t.data_ptr(), img_t.data_ptr(), trt_out.data_ptr()])
    return trt_out.clone()


def make_obs(obs):
    """robosuite obs → ACT 输入（e2_eval.py:69-85 逐字搬移：pt 含 ImageNet，trt 图外全预处理）"""
    qpos = np.concatenate([obs['robot0_eef_pos'], obs['robot0_eef_quat'],
                           obs['robot0_gripper_qpos']]).astype(np.float32)
    qpos = (qpos - Q_MEAN) / Q_STD
    imgs = np.stack([obs['agentview_image'], obs['robot0_eye_in_hand_image']])
    if args.backend in ('trt', 'remote'):
        IM_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
        IM_STD = np.array([0.229, 0.224, 0.225], np.float32)
        imgs = ((imgs.astype(np.float32) / 255.0) - IM_MEAN) / IM_STD
        imgs = np.ascontiguousarray(imgs.transpose(0, 3, 1, 2))   # [E3坑位#12] strided → 连续
        if args.backend == 'remote':
            return np.ascontiguousarray(qpos.astype(np.float32)[None]), \
                   np.ascontiguousarray(imgs.astype(np.float32)[None])
        return torch.from_numpy(np.ascontiguousarray(qpos)).cuda().unsqueeze(0), \
               torch.from_numpy(imgs).cuda().float().unsqueeze(0)
    imgs = torch.from_numpy(imgs.copy()).cuda().float().unsqueeze(0) / 255.0
    imgs = torch.einsum('k h w c -> k c h w', imgs[0]).unsqueeze(0)
    return torch.from_numpy(qpos).cuda().float().unsqueeze(0), imgs


# ---------- 环境（照数据集建——坑位#7）+ 相机数学（Step1 已验证到 0.63cm） ----------
import robosuite                                       # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402
from robosuite.utils.camera_utils import (              # noqa: E402
    get_camera_intrinsic_matrix, get_camera_extrinsic_matrix, get_camera_transform_matrix)

CAM, PLANE_Z, TABLE_HALF = 'agentview', 0.825, 0.35     # 求交平面=方块中心；门控桌界 0.4-余量
env = robosuite.make('Lift', robots=['Panda'],
                     controller_configs=load_controller_config(default_controller='OSC_POSE'),
                     has_renderer=False, has_offscreen_renderer=True, use_camera_obs=True,
                     camera_names=['agentview', 'robot0_eye_in_hand'],
                     camera_heights=84, camera_widths=84, ignore_done=True)


def pixel_to_world_xy(u, v, H):
    K = get_camera_intrinsic_matrix(env.sim, CAM, H, H)
    Ex = get_camera_extrinsic_matrix(env.sim, CAM)
    d_w = Ex[:3, :3] @ (np.linalg.inv(K) @ np.array([u, v, 1.0]))
    o = Ex[:3, 3]
    t = (PLANE_Z - o[2]) / d_w[2]
    return (o + t * d_w)[:2]


def world_to_pixel(p, H):
    T = get_camera_transform_matrix(env.sim, CAM, H, H)
    q = T @ np.array([p[0], p[1], p[2], 1.0])
    return q[0] / q[2], q[1] / q[2]


def render_frame(H, flip=True):
    img = env.sim.render(camera_name=CAM, height=H, width=H)
    return img[::-1] if flip else img


# 行序自检（坑位#5 已实锤需翻转；仍按实测自判，防 robosuite 版本变化）
_obs0 = env.reset()
_seg = np.asarray(env.sim.render(camera_name=CAM, height=256, width=256, segmentation=True))
_bid = env.cube_body_id
_adr, _num = int(env.sim.model.body_geomadr[_bid]), int(env.sim.model.body_geomnum[_bid])
_m = np.isin(_seg[..., 1].astype(int), list(range(_adr, _adr + _num)))
_ys, _xs = np.nonzero(_m)
_gt = world_to_pixel(env.sim.data.body_xpos[_bid], 256)
FLIP = (np.hypot(_xs.mean() - _gt[0], (255 - _ys.mean()) - _gt[1])
        < np.hypot(_xs.mean() - _gt[0], _ys.mean() - _gt[1]))
print(f'[行序] sim.render 直出需 flipud = {FLIP}（分割质心 vs GT 投影实测）')

# 送检 ROI：世界系中心窗投影定窗（Step1 定稿协议：roi-half + send=1000 + 大框重查在编排侧）
_cs = [world_to_pixel((sx * args.roi_half, sy * args.roi_half, PLANE_Z), args.render)
       for sx in (-1, 1) for sy in (-1, 1)]
_xs, _ys = [c[0] for c in _cs], [c[1] for c in _cs]
ROI = (max(0, int(min(_xs)) - 10), max(0, int(min(_ys)) - 10),
       min(args.render, int(max(_xs)) + 10), min(args.render, int(max(_ys)) + 10))
print(f'[ROI] 裁剪窗 {ROI} → 送检 {args.send}×{args.send}')

# 推理预热（一次性 boot 成本，不计入 S5；否则首 chunk 会有百 ms 级冷启动）
# remote 后端的预热挪到 main()：需要节点先建好（pub/sub + discovery 等待，E6 坑位#14）
if args.backend != 'remote':
    for _ in range(3):
        policy_call(torch.zeros(1, 9).cuda(), torch.zeros(1, 2, 3, 84, 84).cuda())
    torch.cuda.synchronize()
    print(f'[boot] backend={args.backend} 预热完成')

import array as _array                              # noqa: E402
import rclpy                                        # noqa: E402
from rclpy.node import Node                         # noqa: E402
from std_msgs.msg import String, UInt8MultiArray, Float64MultiArray    # noqa: E402

os.makedirs(args.video_dir, exist_ok=True)


class E5ActNode(Node):
    def __init__(self):
        super().__init__('e5_act_node')
        self.pub_frame = self.create_publisher(String, 'e5/frame', 10)
        self.pub_status = self.create_publisher(String, 'e5/status', 10)
        self.pub_result = self.create_publisher(String, 'e5/result', 10)
        self.diag = self.create_publisher(String, 'latency_diag', 20)
        self.pub_mirror = None
        if args.live_view:                       # --live-view：qpos 镜像通道（原生窗口在独立进程，坑位#15）
            self.pub_mirror = self.create_publisher(Float64MultiArray, MIRROR_TOPIC, 10)
        self.create_subscription(String, 'e5/command', self.on_command, 10)
        self.create_subscription(String, 'e5/goal', self.on_goal, 10)
        self.cmd_q, self.goal_q = deque(), deque()   # 回调只入队，重活主循环干
        self.state, self.task, self.abort = 'IDLE', None, False
        # ---- remote 基建（E7，逐字同 e2_eval E6 分支；挂本节点上使 spin_once
        #      同派发 /e5/abort 与 /act/chunk——等待中也能被打断，接线点①）----
        self._inbox = {}                             # seq → chunk(1,64,7) f32
        self._rseq, self._rfails = 0, 0
        if args.backend == 'remote':
            self.pub_obs = self.create_publisher(UInt8MultiArray, '/act/obs', 10)
            self.create_subscription(UInt8MultiArray, '/act/chunk', self._on_chunk, 10)
        self.get_logger().info(f'e5_act_node 就绪 backend={args.backend}')

    def _on_chunk(self, m):
        raw = bytes(m.data)                          # UInt8MultiArray → array('B') 直转
        s = int(np.frombuffer(raw[:4], '<u4')[0])
        self._inbox[s] = np.frombuffer(raw[4:], '<f4').reshape(1, K_CHUNK, 7).copy()

    def _send(self, s, q_np, im_np):
        m = UInt8MultiArray()
        m.data = _array.array('B', np.array([s], '<u4').tobytes()
                              + q_np.astype('<f4').tobytes() + im_np.astype('<f4').tobytes())
        self.pub_obs.publish(m)

    def remote_call(self, q_np, im_np):
        """发布 obs → 等 seq 匹配 chunk。200ms 超时重发一次；再超时抛 TimeoutError
        （step_once 判本试失败 + 12s 宽限 + 连 3 停——E6 终版语义）"""
        self._rseq += 1
        self._send(self._rseq, q_np, im_np)
        for _attempt in (0, 1):
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 0.2:
                rclpy.spin_once(self, timeout_sec=0.005)   # 同派发 abort 回调
                if self.abort:
                    raise Aborted(f'remote 等待中被 abort（seq={self._rseq}）')
                if self._rseq in self._inbox:
                    self._rfails = 0                   # 链路恢复，连败清零
                    return torch.from_numpy(self._inbox.pop(self._rseq))
            self._send(self._rseq, q_np, im_np)        # 超时重发一次
        raise TimeoutError(f'remote seq={self._rseq} 超时（含重发 1 次）')

    def diag_pub(self, stage, task_id, **kw):
        self.diag.publish(String(data=json.dumps(
            {'node': 'e5_act', 'stage': stage, 'task_id': task_id, **kw}, ensure_ascii=False)))

    def mirror_pub(self):
        """--live-view：qpos 全量（含方块自由关节）镜像给独立进程原生窗口；未开时零成本"""
        if self.pub_mirror is not None:
            self.pub_mirror.publish(Float64MultiArray(data=env.sim.data.qpos.tolist()))

    # ---- SNAPSHOT ----
    def do_snapshot(self, task_id):
        t0 = time.perf_counter()
        obs = env.reset()                              # 每 task_id 仅此一次（手册 2.4）
        cube = env.sim.data.body_xpos[env.cube_body_id].copy()
        self.mirror_pub()                              # --live-view：窗口显示重置后场景（VLM 思考期定格在这）
        jpg = f'/tmp/e5_frame_{task_id}.jpg'
        from PIL import Image
        full = render_frame(args.render, FLIP)
        src = full[ROI[1]:ROI[3], ROI[0]:ROI[2]]
        self.crop_wh = (src.shape[1], src.shape[0])
        Image.fromarray(src).resize((args.send, args.send),
                                    Image.LANCZOS).save(jpg, quality=92)
        render_ms = (time.perf_counter() - t0) * 1e3
        self.obs, self.cube = obs, cube
        self.pub_frame.publish(String(data=json.dumps(
            {'task_id': task_id, 'image_path': jpg, 'send': args.send})))
        self.diag_pub('snapshot', task_id, render_ms=round(render_ms, 1))

    # ---- COORD：坐标链 + 门控（bbox 为 send 空间，先映射回全帧） ----
    def do_coord(self, task_id, bbox, grade):
        t0 = time.perf_counter()
        x1, y1, x2, y2 = bbox                          # send×send 空间（语义坍缩协议）
        x1r, y1r, x2r, y2r = bbox                      # 面积门用原始送检空间
        sw_, sh_ = self.crop_wh
        x1, y1, x2, y2 = (ROI[0] + x1 / args.send * sw_, ROI[1] + y1 / args.send * sh_,
                          ROI[0] + x2 / args.send * sw_, ROI[1] + y2 / args.send * sh_)
        tgt = pixel_to_world_xy((x1 + x2) / 2, (y1 + y2) / 2, args.render)
        err_cm = float(np.linalg.norm(tgt - self.cube[:2]) * 100)
        gate = 'pass' if (abs(tgt[0]) <= TABLE_HALF and abs(tgt[1]) <= TABLE_HALF
                          and grade != 'C2'
                          and (x2r - x1r) * (y2r - y1r) <= 0.25 * args.send ** 2) else 'reject'
        self.diag_pub('coord', task_id, coord_ms=round((time.perf_counter() - t0) * 1e3, 1),
                      xy_err_cm=round(err_cm, 2), tgt_x=round(float(tgt[0]), 3),
                      tgt_y=round(float(tgt[1]), 3), gate=gate)
        return gate

    # ---- EXECUTE：e2_eval 循环 + 20Hz 节拍 + 录像（buffer 每集清零） ----
    def do_execute(self, task_id):
        obs, lat_ms, frames = self.obs, [], []
        all_time = torch.zeros(args.horizon, args.horizon + K_CHUNK, 7).cuda()
        t_exec0 = time.perf_counter()
        done_t, chunk = None, None
        period, next_t = 1.0 / args.hz, time.perf_counter()
        for t in range(args.horizon):
            qpos_t, img_t = make_obs(obs)
            if chunk is None:
                t_pre = (time.perf_counter() - t_exec0) * 1e3
            torch.cuda.synchronize(); t0 = time.perf_counter()
            chunk = policy_call(qpos_t, img_t).detach().cpu().numpy().squeeze(0)
            torch.cuda.synchronize()
            lat_ms.append((time.perf_counter() - t0) * 1e3)
            if len(lat_ms) == 1:                       # S5：首 chunk + 首步
                first_ms = lat_ms[0]
                self.diag_pub('exec_start', task_id, first_chunk_ms=round(first_ms, 1),
                              preproc_ms=round(t_pre, 1))
            all_time[[t], t:t + K_CHUNK] = torch.from_numpy(chunk).cuda()
            afcs = all_time[:, t]
            afcs = afcs[torch.all(afcs != 0, dim=1)]
            w = np.exp(-0.01 * np.arange(len(afcs)))
            w = torch.from_numpy(w / w.sum()).cuda().unsqueeze(1)
            a = (afcs * w).sum(0).cpu().numpy()
            a = a * A_STD + A_MEAN
            obs, r, _, _ = env.step(np.clip(a, -1, 1))
            if not args.no_record:                     # --no-record：演示模式跳过 512 显示帧渲染
                frames.append(render_frame(args.display, FLIP))
            self.mirror_pub()                          # --live-view：独立进程原生窗口 20Hz 跟随
            if len(lat_ms) == 1:                       # 首步完成时刻 = S5 终点
                self.diag_pub('first_step', task_id,
                              to_first_step_ms=round((time.perf_counter() - t_exec0) * 1e3, 1))
            if self.abort or self._poll_abort():
                break
            if env._check_success():
                done_t = t
                break
            next_t += period
            dt = next_t - time.perf_counter()
            if dt > 0:
                time.sleep(dt)
        exec_ms = (time.perf_counter() - t_exec0) * 1e3
        success = done_t is not None
        video = ''
        if frames:                                       # --no-record 时整段跳过
            video = os.path.join(args.video_dir, f'e5_act_{task_id}.mp4')
            try:
                import imageio
                imageio.mimwrite(video, frames, fps=int(args.hz), quality=8)
            except Exception as e:
                self.get_logger().warn(f'录像失败: {e}')
                video = ''
        lat = np.array(lat_ms)
        self.diag_pub('exec_done', task_id, exec_ms=round(exec_ms), steps=t + 1,
                      success=bool(success), backend=args.backend,   # remote 段对账（坑位#9）
                      chunk_p50=round(float(np.percentile(lat, 50)), 2) if len(lat) else 0)
        return {'status': 'done', 'success': success, 'steps': t + 1, 'video': video}

    def _poll_abort(self):
        rclpy.spin_once(self, timeout_sec=0.0)         # 主循环上下文里收 abort（无嵌套）
        return self.abort

    # ---- 回调：只入队 ----
    def on_command(self, msg):
        c = json.loads(msg.data)
        if c.get('type') == 'abort':
            self.abort = True
            return
        self.cmd_q.append(c)

    def on_goal(self, msg):
        self.goal_q.append(json.loads(msg.data))

    # ---- 主循环驱动 ----
    def step_once(self):
        if self.state == 'IDLE' and self.cmd_q:
            c = self.cmd_q.popleft()
            self.task = dict(task_id=c['task_id'], instr=c.get('instruction', ''),
                             try_=c.get('try_', 1))
            self.abort = False
            self.state = 'SNAPSHOT'
            self.do_snapshot(c['task_id'])
            self.state, self.goal_deadline = 'WAIT_GOAL', time.perf_counter() + 60.0
            return
        if self.state == 'WAIT_GOAL':
            if self.goal_q:
                g = self.goal_q.popleft()
                if g['task_id'] != self.task['task_id']:
                    return
                gate = self.do_coord(g['task_id'], g['bbox'], g.get('grade', ''))
                if gate != 'pass':
                    self.pub_result.publish(String(data=json.dumps(
                        {'task_id': g['task_id'], **self.task, 'status': 'rejected',
                         'success': False, 'reason': 'gate_reject', 'video': ''})))
                    self.state = 'IDLE'
                    return
                self.state = 'EXECUTE'
                try:
                    res = self.do_execute(g['task_id'])
                except TimeoutError as te:             # remote 断链：本试判败不死锁（B5）
                    self._rfails += 1
                    self.diag_pub('remote_timeout', g['task_id'], rfails=self._rfails, err=str(te))
                    if self._rfails >= 3:
                        raise RuntimeError(f'remote 链路连续 {self._rfails} 试超时——停（E6 三振语义）')
                    res = {'status': 'error', 'success': False, 'steps': 0, 'video': '',
                           'reason': f'remote_timeout: {te}'}
                    time.sleep(12)                     # 恢复宽限：板端节点重启 ~16-19s，三振窗 36s 覆盖
                except Aborted as ae:                  # 等待中 abort：判败但不算链路故障
                    res = {'status': 'aborted', 'success': False, 'steps': 0, 'video': '',
                           'reason': str(ae)}
                except Exception:
                    res = {'status': 'error', 'success': False, 'steps': 0, 'video': '',
                           'reason': traceback.format_exc()[-500:]}   # E1 教训：异常必须落 result
                self.pub_result.publish(String(data=json.dumps(
                    {'task_id': g['task_id'], **self.task, **res}, ensure_ascii=False)))
                self.state = 'IDLE'
            elif self.abort or time.perf_counter() > self.goal_deadline:
                self.pub_result.publish(String(data=json.dumps(
                    {'task_id': self.task['task_id'], **self.task, 'status': 'timeout',
                     'success': False,
                     'reason': 'aborted' if self.abort else 'goal 60s 未达', 'video': ''})))
                self.state = 'IDLE'


def selftest(node, n):
    """ST1：GT 门控自检（门控用真值投影像素伪造完美 bbox，其余链路全真）"""
    succ = []
    for i in range(n):
        task_id = f'self{i}'
        node.task = dict(task_id=task_id, instr='selftest', try_=1)
        node.abort = False
        node.do_snapshot(task_id)
        u, v = world_to_pixel(node.cube, args.render)
        half = round(0.025 / (1.44 / 927))            # 方块半高 2.5cm ÷ 1px≈1.6mm ≈ 16px
        gate = node.do_coord(task_id, (u - half, v - half, u + half, v + half), 'A')
        assert gate == 'pass', 'GT 门控竟被拒，检查 TABLE_HALF'
        res = node.do_execute(task_id)
        node.pub_result.publish(String(data=json.dumps(
            {'task_id': task_id, **node.task, **res}, ensure_ascii=False)))
        succ.append(res['success'])
        print(f'[selftest {i+1}/{n}] success={res["success"]} steps={res["steps"]} video={res["video"]}')
    print(f'\n==== ST1 自检: {sum(succ)}/{n} ====')


def main():
    global _REMOTE
    rclpy.init()
    node = E5ActNode()
    _REMOTE = node
    if args.backend == 'remote':
        t0 = time.perf_counter()                       # discovery 等待（E6 坑位#14）
        while node.pub_obs.get_subscription_count() == 0 and time.perf_counter() - t0 < 10:
            rclpy.spin_once(node, timeout_sec=0.05)
        n_sub = node.pub_obs.get_subscription_count()
        print(f'[boot] remote discovery {(time.perf_counter() - t0) * 1e3:.0f}ms，订阅数={n_sub}')
        assert n_sub > 0, '板端 e6_act_infer_node 未匹配（/act/chunk 无订阅）——先查服务'
        z_q = np.zeros((1, 9), np.float32)
        z_i = np.zeros((1, 2, 3, 84, 84), np.float32)
        for _ in range(3):
            node.remote_call(z_q, z_i)                 # 预热走完整链路（不计入 S5）
        print('[boot] backend=remote 预热完成（3 次全链路 chunk）')
    if args.live_view:
        print(f'[boot] live-view 镜像通道就绪（{MIRROR_TOPIC}）——窗口另进程起: tools/arm/e7_mirror_viewer.py')
    if args.selftest:
        selftest(node, args.selftest)
    else:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
            node.step_once()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
