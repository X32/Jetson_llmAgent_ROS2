"""【E5-v2】语音抓取链第二代：VLM 门禁 → YOLO 定位 → g2c ACT → 营救环（单节点整合）

链路（用户 2026-10-09 定稿设计）：
  /voice_text（或 --text 打字指令）→ 意图识别（关键词，只认方块类目标）
    → 快照 → 【VLM 门禁】grounding 服务问"有没有方块"——没有 → 拒绝执行（如实上报）
    → 有 → 【YOLO】grounding_yolo 服务（remap 后的 yolo_grounding 节点，52ms）给精确 bbox
    → bbox 中心 → 单应反投影 → obs['cube_pos'] → 【g2c ACT 开环 64 步】
    → 【营救环】指距检测抓紧；抓空则重调 YOLO 看新位置重抓（最多 3 次，深度阶梯）
  → /e5v2/result + /latency_diag + 全程录像

新旧分工：VLM 只干"有没有"的语义判断（它慢但什么都能看）；YOLO 干"在哪"的精确定位
（快 160 倍、准 4.5 倍但只认方块）；ACT 干"怎么抓"（凭经验）；脚本干"抓没抓住/重抓"（传感器+减法）。

前置（三个终端，VLM 那个可后补）：
  T1: Jetson llama-server（qwen2.5-vl-3b，E5/E7 同款）
  T2: ros2 run vision_agent grounding                          # VLM 节点（服务名 grounding）
  T3: ros2 run vision_agent yolo_grounding -r /grounding:=/grounding_yolo   # YOLO 节点（remap 避重名）
  T0(本节点): source /opt/ros/humble/setup.bash && source install/setup.bash && \
      MUJOCO_GL=egl /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e5_grasp_v2_node.py \
      --ckpt policy_epoch_2200_seed_0.ckpt --text "把桌上的方块抓起来"     # --text 缺省=等语音
  无方块拒绝演示：--gate-image <无方块图片路径>（门禁只看这张图，不 reset 场景）
"""
import argparse
import json
import os
import pickle
import sys
import time
from collections import deque

import numpy as np
import torch

ap = argparse.ArgumentParser()
ap.add_argument('--ckpt_dir', default='/mnt/apfs/workplace/act/ckpt_lift_ph_g2c')
ap.add_argument('--ckpt', default='policy_epoch_2200_seed_0.ckpt')
ap.add_argument('--text', default='', help='打字指令（缺省=订阅 /voice_text 等语音）')
ap.add_argument('--gate-image', default='', help='非空=门禁只看这张图（无方块拒绝演示用），不跑抓取')
ap.add_argument('--hide-cube', action='store_true',
                help='拒绝演示：reset 后把方块挪出视野再过门禁（VLM 应说没有→拒绝执行）')
ap.add_argument('--vlm-url', default='http://192.168.4.52:8000',
                help='VLM 门禁直连 HTTP（是/否问答式——强迫框坐标时 3B 模型没东西也编框，'
                     'bus.jpg 实测假阳性；问"有没有"是它擅长的问答）')
ap.add_argument('--near-miss', type=float, default=0.025)
ap.add_argument('--retries', type=int, default=3)
ap.add_argument('--plane-z', type=float, default=0.831)
ap.add_argument('--snap-h', type=int, default=480)
ap.add_argument('--snap-w', type=int, default=640)
ap.add_argument('--video-dir', default='/mnt/apfs/workplace/act/ckpt_lift_ph_g2c')
ap.add_argument('--mirror', action='store_true',
                help='开实时窗口：每步把 qpos 发到 mirror 话题，配 e7_mirror_viewer.py --topic 同名（坑位#15：'
                     'GLFW 窗口须独立进程，本进程 EGL 离屏不变）')
ap.add_argument('--mirror-topic', default='e5v2_mirror')
args = ap.parse_args()

# ---------- 策略加载（与 e2_eval_g2c 系列逐字同，坑位#19） ----------
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

# ---------- 环境 + 相机数学（e2_eval_g2c_percept_retry 同源） ----------
import robosuite                                        # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402
from robosuite.utils.camera_utils import (              # noqa: E402
    get_camera_intrinsic_matrix, get_camera_extrinsic_matrix, get_camera_transform_matrix)

env = robosuite.make(
    'Lift', robots=['Panda'],
    controller_configs=load_controller_config(default_controller='OSC_POSE'),
    has_renderer=False, has_offscreen_renderer=True, use_camera_obs=True,
    camera_names=['agentview', 'robot0_eye_in_hand'],
    camera_heights=84, camera_widths=84,
    ignore_done=True,
)
CAM, H, W = 'agentview', args.snap_h, args.snap_w
_K = get_camera_intrinsic_matrix(env.sim, CAM, H, W)
_Ex0 = get_camera_extrinsic_matrix(env.sim, CAM)
_Rwc, _o = _Ex0[:3, :3].T, _Ex0[:3, 3]                    # 【约定坑】Ex 是"相机→世界"，单应须 Rᵀ(X−o)
_Hwp = _K @ np.hstack([_Rwc[:, 0:1], _Rwc[:, 1:2], (_Rwc @ (-_o) + _Rwc[:, 2] * args.plane_z)[:, None]])
Hpw = np.linalg.inv(_Hwp)


def px_to_world(u, v):
    q = Hpw @ np.array([u, v, 1.0])
    return q[0] / q[2], q[1] / q[2]


# boot 自检：单应往返 <1mm（两条独立算路对账）
_obs0 = env.reset()
_T = get_camera_transform_matrix(env.sim, CAM, H, W)
_q = _T @ np.array([_obs0['cube_pos'][0], _obs0['cube_pos'][1], args.plane_z, 1.0])
_u, _v = _q[0] / _q[2], _q[1] / _q[2]
_wx, _wy = px_to_world(_u, _v)
assert float(np.hypot(_wx - _obs0['cube_pos'][0], _wy - _obs0['cube_pos'][1])) < 0.001, '单应自检失败'
print('[boot] 单应往返 <1mm ✓')

# ---------- 运动原语 + 感知（percept_retry 同源） ----------
STEP_CM = 0.0116
GRIP_CLOSE, GRIP_OPEN = 1.0, -1.0
GSEP_BLOCKED = 0.030


def gsep(o):
    return abs(o['robot0_gripper_qpos'][0] - o['robot0_gripper_qpos'][1])


rec_frames = []
pub_mirror = None                                   # --mirror 时由节点创建（模块级，运动原语都能发）


def snap_cam():
    rec_frames.append(obs['agentview_image'].copy())
    mirror_publish()


def mirror_publish():
    """活窗口：全量 qpos（臂+夹爪+方块自由关节）→ 镜像进程 mj_forward 原生渲染"""
    if pub_mirror is None:
        return
    msg = Float64MultiArray()
    msg.data = [float(v) for v in env.sim.data.qpos]
    pub_mirror.publish(msg)


def move_to(target_xyz, grip, max_steps=90, tol=0.008):
    global obs
    for _ in range(max_steps):
        if env._check_success():
            return 'success'
        d = np.asarray(target_xyz) - obs['robot0_eef_pos']
        a = np.zeros(7)
        a[:3] = np.clip(d / STEP_CM * 0.7, -1, 1)
        a[6] = grip
        obs, _, _, _ = env.step(np.clip(a, -1, 1))
        snap_cam()
        if np.linalg.norm(d[:2]) < tol and abs(d[2]) < tol:
            break
    return 'ok' if env._check_success() else 'moved'


def close_and_check(steps=25):
    global obs
    for _ in range(steps):
        a = np.zeros(7); a[6] = GRIP_CLOSE
        obs, _, _, _ = env.step(a)
        snap_cam()
    return gsep(obs) >= GSEP_BLOCKED


def make_obs(o):
    qpos = np.concatenate([o['robot0_eef_pos'], o['robot0_eef_quat'],
                           o['robot0_gripper_qpos'],
                           o['robot0_eef_pos'] - o['cube_pos']]).astype(np.float32)
    qpos = (qpos - stats['qpos_mean']) / stats['qpos_std']
    imgs = np.stack([o['agentview_image'], o['robot0_eye_in_hand_image']])
    imgs = torch.from_numpy(imgs.copy()).cuda().float().unsqueeze(0) / 255.0
    imgs = torch.einsum('k h w c -> k c h w', imgs[0]).unsqueeze(0)
    return torch.from_numpy(qpos).cuda().float().unsqueeze(0), imgs


# ---------- ROS 层 ----------
import cv2                                             # noqa: E402
import rclpy                                           # noqa: E402
from rclpy.node import Node                            # noqa: E402
from std_msgs.msg import String, Float64MultiArray     # noqa: E402
from my_package.srv import Grounding                   # noqa: E402

LIFT_WORDS = ('抓', '拿', '举', '夹', '提', '拾', '捡')
CUBE_WORDS = ('方块', '正方体', '木块', 'cube')


class E5V2Node(Node):
    def __init__(self):
        super().__init__('e5_grasp_v2')
        global pub_mirror
        self.pub_result = self.create_publisher(String, 'e5v2/result', 10)
        self.diag = self.create_publisher(String, 'latency_diag', 20)
        if args.mirror:
            pub_mirror = self.create_publisher(Float64MultiArray, args.mirror_topic, 20)
        self.create_subscription(String, 'voice_text', self.on_voice, 10)
        self.cli_vlm = self.create_client(Grounding, 'grounding')            # VLM 门禁
        self.cli_yolo = self.create_client(Grounding, 'grounding_yolo')      # YOLO 精确（remap）
        self.cmd_q = deque()
        self.seq = 0
        self.get_logger().info(
            f'e5_grasp_v2 就绪（VLM 门禁=直连 {args.vlm_url}，'
            f'YOLO {"在线" if self.cli_yolo.service_is_ready() else "未上线——必须先起"})')

    def diag_pub(self, stage, **kw):
        self.diag.publish(String(data=json.dumps(
            {'node': 'e5v2', 'stage': stage, **kw}, ensure_ascii=False)))

    def on_voice(self, msg):
        self.cmd_q.append(msg.data.strip())

    # ---- 服务调用（同步等待，带超时） ----
    def call_srv(self, cli, target, img_path, timeout=75.0):
        req = Grounding.Request()
        req.target, req.image_path = target, img_path
        fut = cli.call_async(req)
        t0 = time.perf_counter()
        while not fut.done() and time.perf_counter() - t0 < timeout:
            rclpy.spin_once(self, timeout_sec=0.05)
        if not fut.done():
            fut.cancel()
            return None, -1.0
        r = fut.result()
        return r, float(r.latency_ms)

    def save_frame(self, tag='snap', size=(H, W)):
        img = env.sim.render(camera_name=CAM, height=size[0], width=size[1])[::-1]
        p = f'/tmp/e5v2_{tag}_{self.seq}.jpg'
        cv2.imwrite(p, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        return p

    # ---- VLM 门禁（是/否问答式，直连 HTTP，复用 grounding_node 同款 base64/重编码链） ----
    def vlm_gate(self, img_path):
        """→ (True/False/None, ms)。None=服务不可达（如实上报，不静默放行）"""
        import base64
        import io
        import urllib.request
        from PIL import Image
        try:
            img = Image.open(img_path).convert('RGB')
            scale = 768 / max(img.size)
            sent = img.resize((round(img.size[0] * scale), round(img.size[1] * scale)))
            buf = io.BytesIO()
            sent.save(buf, 'JPEG')
            b64 = base64.b64encode(buf.getvalue()).decode()
            payload = {'messages': [{'role': 'user', 'content': [
                {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
                {'type': 'text', 'text': '图中有没有红色的方块？只回答两个字：有 或 没有。'}]}],
                'max_tokens': 8, 'temperature': 0.0}
            req = urllib.request.Request(
                f'{args.vlm_url.rstrip("/")}/v1/chat/completions',
                data=json.dumps(payload).encode(),
                headers={'Content-Type': 'application/json'}, method='POST')
            t0 = time.perf_counter()
            with urllib.request.urlopen(req, timeout=60) as r:
                out = json.loads(r.read())
            ans = out['choices'][0]['message']['content'].strip()
            ms = (time.perf_counter() - t0) * 1e3
            return ('有' in ans and '没有' not in ans), ms
        except Exception as e:
            return None, -1.0

    # ---- 主任务：一条指令的完整生命周期 ----
    def run_task(self, text):
        global obs
        self.seq += 1
        t0 = time.perf_counter()
        self.get_logger().info(f'━━━ 指令[{self.seq}]: {text!r}')

        # ① 意图：必须是抓取指令 + 方块类目标（新链只抓方块）
        if not any(w in text for w in LIFT_WORDS):
            self.finish('no_task', False, t0, note='未识别为抓取指令')
            return
        if not any(w in text for w in CUBE_WORDS):
            self.finish('no_target', False, t0, note='本链只抓方块（杯子/球/碗走旧链）')
            return

        # ② 场景快照（门禁图 768 全帧；--gate-image 用指定图；--hide-cube 挪走方块演示拒绝）
        global obs
        if args.gate_image:
            gate_img = args.gate_image
        else:
            obs = env.reset()
            rec_frames.clear()
            snap_cam()
            if args.hide_cube:
                jid = env.sim.model.joint_name2id('cube_joint0')
                adr = env.sim.model.jnt_qposadr[jid]
                env.sim.data.qpos[adr:adr + 3] = [1.2, 1.2, 0.5]   # 挪出视野
                env.sim.forward()
                mirror_publish()               # 窗口里也同步"方块被拿走"（reset 那帧贴早了）
            gate_img = self.save_frame('gate', (768, 768))

        # ③ VLM 门禁：有没有方块？（是/否问答，直连 HTTP）
        has_cube, vlm_ms = self.vlm_gate(gate_img)
        self.diag_pub('gate', seq=self.seq, vlm_ms=round(vlm_ms), has_cube=has_cube)
        if has_cube is None:
            self.finish('vlm_down', False, t0, note='VLM 服务不可达——拒绝放行（不静默跳过门禁）')
            return
        if not has_cube:
            self.finish('gate_reject', False, t0,
                        note=f'VLM 说没方块（{vlm_ms:.0f}ms 看过）——拒绝执行')
            return
        self.get_logger().info(f'  [门禁] 有方块（VLM {vlm_ms:.0f}ms）→ 放行')

        if args.gate_image:                             # 拒绝演示模式：到门禁为止
            self.finish('gate_demo_pass', True, t0, note='指定图门禁通过（演示模式不抓取）')
            return

        # ④ YOLO 精确定位（开局一眼）
        yolo_img = self.save_frame('snap')
        resp, yolo_ms = self.call_srv(self.cli_yolo, '红色方块', yolo_img, timeout=10.0)
        if resp is None or resp.error or not resp.objects:
            est = np.array([0.0, 0.0, args.plane_z])     # 漏检：桌面中心先验照跑（如实记）
            self.get_logger().warn('  [YOLO] 漏检！用桌面中心先验继续（将记 miss）')
        else:
            o = max(resp.objects, key=lambda o: o.confidence)
            wx, wy = px_to_world((o.x1 + o.x2) / 2, (o.y1 + o.y2) / 2)
            est = np.array([wx, wy, args.plane_z])
        self.diag_pub('yolo', seq=self.seq, yolo_ms=round(yolo_ms),
                      est=[round(float(est[0]), 3), round(float(est[1]), 3)])
        obs['cube_pos'] = est                           # g2c 向量唯一消费点

        # ⑤ Phase 1：g2c ACT 开环 64 步
        chunk, t_exec, min_d_xy, done_t = None, 0, 9.9, None
        for t in range(64):
            qpos_t, img_t = make_obs(obs)
            if chunk is None:
                chunk = policy(qpos_t, img_t).detach().cpu().numpy().squeeze(0)
                t_exec = 0
            a = chunk[min(t_exec, 63)] * a_std + a_mean
            obs, r, _, _ = env.step(np.clip(a, -1, 1))
            snap_cam()
            t_exec += 1
            min_d_xy = min(min_d_xy, np.linalg.norm(obs['robot0_eef_pos'][:2] - est[:2]))
            if env._check_success():
                done_t = t
                break
        self.get_logger().info(f'  [ACT] {"成功" if done_t is not None else "未中"} '
                               f'(min_d_xy={min_d_xy:.3f}, gsep={gsep(obs):.4f})')

        # ⑥ Phase 2：营救（抓空→重看 YOLO→重抓）
        rescue = '—'
        if done_t is None and min_d_xy < args.near_miss:
            if gsep(obs) >= GSEP_BLOCKED:               # 抓住了没举起 → 直提
                res = move_to([est[0], est[1], 1.0], GRIP_CLOSE)
                rescue = f'直提→{"✅" if res == "success" else "❌"}'
            else:
                for attempt in range(args.retries):
                    yi = self.save_frame('snap')        # 重看一眼摄像头
                    resp2, _ = self.call_srv(self.cli_yolo, '红色方块', yi, timeout=10.0)
                    if resp2 is not None and not resp2.error and resp2.objects:
                        o2 = max(resp2.objects, key=lambda o: o.confidence)
                        wx, wy = px_to_world((o2.x1 + o2.x2) / 2, (o2.y1 + o2.y2) / 2)
                        est = np.array([wx, wy, args.plane_z])
                    dz = -0.019 - 0.006 * attempt
                    move_to([est[0], est[1], 0.90], GRIP_OPEN)
                    move_to([est[0], est[1], est[2] + dz], GRIP_OPEN)
                    if close_and_check():
                        res = move_to([est[0], est[1], 1.0], GRIP_CLOSE)
                        rescue = f'重抓#{attempt + 1}→{"✅" if res == "success" else "❌"}'
                        if res == 'success':
                            break
                    else:
                        rescue = f'重抓#{attempt + 1}→仍空'
            if env._check_success():
                done_t = -1
        ok = done_t is not None
        self.finish('done', ok, t0, rescue=rescue, note=f'vlm={vlm_ms:.0f}ms yolo={yolo_ms:.0f}ms')

    def finish(self, status, success, t0, rescue='—', note=''):
        total = (time.perf_counter() - t0) * 1e3
        msg = {'seq': self.seq, 'status': status, 'success': bool(success),
               'rescue': rescue, 'total_ms': round(total), 'note': note}
        self.pub_result.publish(String(data=json.dumps(msg, ensure_ascii=False)))
        self.diag_pub('e2e', **msg)
        emoji = '✅' if success else '❌'
        self.get_logger().info(f'  [结果] {emoji} {status} {note} （端到端 {total / 1000:.2f}s）')
        if rec_frames and status == 'done':
            import imageio
            frames = np.repeat(np.repeat(np.array(rec_frames), 4, 1), 4, 2)
            p = os.path.join(args.video_dir,
                             f'e5v2_ep{time.strftime("%H%M%S")}_{self.seq}.mp4')
            imageio.mimwrite(p, frames, fps=20, quality=8)
            self.get_logger().info(f'  🎬 全程录像 → {p} ({len(frames)} 帧)')


def main():
    rclpy.init()
    node = E5V2Node()
    try:
        if args.text:
            time.sleep(1.5)                             # 等 discovery 完成
            node.cmd_q.append(args.text)
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
            if node.cmd_q:
                node.run_task(node.cmd_q.popleft())
    except (KeyboardInterrupt, SystemExit):
        pass
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == '__main__':
    main()
