#!/usr/bin/env python3
"""E5 Step1 坐标链验证（手册 DOC/arm/experiment_E5.md §四）

验证链：渲染快照(768) → [VLM grounding | --gt-only 分割真值] → bbox 像素
      → K⁻¹ 射线 → 桌面 z=0.8 平面求交 → 世界系目标点 → 与 cube_pos 对账
      → GT 反投影 84 系（ACT 观测帧对齐，手册 2.2 尾部）

行序自检（坑位#5）：首跑用分割真值质心 vs GT 反投影自动判翻转，并打印
raw 渲染与 obs 84 图的方向相关性——以实测为准，不信文档（包括本注释）。

用法（venv + ROS；坐标链本体无 torch/TRT 依赖）：
  source /opt/ros/humble/setup.bash && source install/setup.bash
  MUJOCO_GL=egl /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e5_coord_check.py --runs 10
  VLM 不在线时：加 --gt-only（分割真值当 pseudo-VLM，先验证坐标链数学）
"""
import argparse
import csv
import os
import time

import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument('--runs', type=int, default=10)
ap.add_argument('--size', type=int, default=768, help='送检渲染边长（方形）')
ap.add_argument('--target', default='红色方块')
ap.add_argument('--gt-only', action='store_true', help='跳过 VLM，用分割真值验证坐标链')
ap.add_argument('--roi', default='none',
                help="none|auto|x1,y1,x2,y2 —— 送检前裁剪放大（坑位#8 招②：小目标有效分辨率翻倍；"
                     "auto=桌面四角±0.4投影定窗）。VLM 坐标自动映射回全帧")
ap.add_argument('--send', type=int, default=1000,
                help='送检方形边长。实测破案：模型坐标语义在"送检图像素/0-1000归一化"间漂移'
                     '（E1 的 V9 不是铁律），数值层无法区分；送 1000×1000 使两种语义数值恒等，歧义消失')
ap.add_argument('--plane-z', type=float, default=0.825,
                help='射线求交平面高度=方块中心（桌面0.8+半高0.025）。实测教训：交桌面z=0.8时'
                     '方块质心高出台面→视差致x向恒偏~3.0cm（10次2.87-3.23cm、y轴零偏，GT-only实测）')
ap.add_argument('--csv', default=os.path.join(os.path.dirname(__file__), '..', 'results', 'e5_coord.csv'))
ap.add_argument('--save-first', type=int, default=3, help='前 N 次存叠加图到 tools/')
args = ap.parse_args()

import robosuite                                   # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402
from robosuite.utils.camera_utils import (         # noqa: E402
    get_camera_intrinsic_matrix, get_camera_extrinsic_matrix, get_camera_transform_matrix)

CAM, TABLE_Z = 'agentview', 0.8                    # lift.py:171 table_offset
PLANE_Z_DEFAULT = 0.825                            # 桌面+方块半高（求交平面，Step1 实测教训）
ENV_ARGS = dict(                                   # 与 e2_eval.py:59-66 逐字同款（坑位#7：考场照数据集建）
    robots=['Panda'],
    controller_configs=load_controller_config(default_controller='OSC_POSE'),
    has_renderer=False, has_offscreen_renderer=True, use_camera_obs=True,
    camera_names=['agentview', 'robot0_eye_in_hand'],
    camera_heights=84, camera_widths=84, ignore_done=True)
env = robosuite.make('Lift', **ENV_ARGS)


# ---------- 相机数学（手册 2.2） ----------
def pixel_to_world_xy(u, v, H):
    """送检图像素 (u,v) → 相机射线 → 与桌面 z=TABLE_Z 相交 → 世界系 (x,y)"""
    K = get_camera_intrinsic_matrix(env.sim, CAM, H, H)
    Ex = get_camera_extrinsic_matrix(env.sim, CAM)            # camera-to-world（OpenCV 轴向修正后）
    d_cam = np.linalg.inv(K) @ np.array([u, v, 1.0])
    d_w = Ex[:3, :3] @ d_cam
    o = Ex[:3, 3]
    t = (args.plane_z - o[2]) / d_w[2]
    return (o + t * d_w)[:2]


def world_to_pixel(p, H):
    """世界点 → 各分辨率像素（标准约定：原点左上）。84 系即 ACT 观测帧对齐基准"""
    T = get_camera_transform_matrix(env.sim, CAM, H, H)
    q = T @ np.array([p[0], p[1], p[2], 1.0])
    return q[0] / q[2], q[1] / q[2]


def cube_mask(H):
    """分割真值：cube geom 像素 mask（与 RGB 同一 render 调用路径 → 同行序）"""
    bid = env.cube_body_id
    adr, num = int(env.sim.model.body_geomadr[bid]), int(env.sim.model.body_geomnum[bid])
    seg = np.asarray(env.sim.render(camera_name=CAM, height=H, width=H, segmentation=True))
    return np.isin(seg[..., 1].astype(int), list(range(adr, adr + num)))


def draw_overlay(img, det_bb, gt_bb, gt_uv, text, out):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    if det_bb:
        d.rectangle(det_bb, outline=(255, 0, 0), width=3)          # 红=检测
    if gt_bb:
        d.rectangle(gt_bb, outline=(0, 255, 0), width=2)           # 绿=分割真值
    u, v = gt_uv
    d.line([(u - 12, v), (u + 12, v)], fill=(0, 90, 255), width=3)  # 蓝=GT 反投影十字
    d.line([(u, v - 12), (u, v + 12)], fill=(0, 90, 255), width=3)
    d.text((8, 8), text, fill=(255, 255, 0))
    im.save(out)


# ---------- VLM 客户端（非 gt-only 才 import，保持 gt-only 可脱离 ROS 跑） ----------
node = None
if not args.gt_only:
    import rclpy                                    # noqa: E402
    from my_package.srv import Grounding            # noqa: E402

    rclpy.init()
    node = rclpy.create_node('e5_coord_check_client')
    cli = node.create_client(Grounding, 'grounding')
    print('等待 /grounding 服务…（T1: ros2 run vision_agent grounding …）')
    if not cli.wait_for_service(timeout_sec=15.0):
        raise SystemExit('❌ /grounding 服务 15s 未出现：先起 T1（手册 5.3），或加 --gt-only 先验证坐标链')


def call_vlm(image_path):
    req = Grounding.Request()
    req.target, req.image_path = args.target, image_path
    fut = cli.call_async(req)
    rclpy.spin_until_future_complete(node, fut, timeout_sec=90.0)
    if fut.result() is None:
        return None, 0.0, 'timeout'
    r = fut.result()
    if r.error:
        return None, 0.0, r.error
    if not r.objects:
        return None, r.latency_ms, 'no_det'
    o = r.objects[0]
    return (o.x1, o.y1, o.x2, o.y2), r.latency_ms, o.grade


# ---------- 主循环 ----------
ROI = None
if args.roi != 'none':
    if args.roi.startswith('auto'):            # auto[:半宽m] —— 世界系中心窗投影定窗（几何法）
        half = float(args.roi.split(':')[1]) if ':' in args.roi else 0.4
        cs = [world_to_pixel((sx * half, sy * half, PLANE_Z_DEFAULT), args.size)
              for sx in (-1, 1) for sy in (-1, 1)]
        xs, ys = [c[0] for c in cs], [c[1] for c in cs]
        pad = 10
        ROI = (max(0, int(min(xs)) - pad), max(0, int(min(ys)) - pad),
               min(args.size, int(max(xs)) + pad), min(args.size, int(max(ys)) + pad))
    else:
        ROI = tuple(int(v) for v in args.roi.split(','))
    print(f'[ROI] 裁剪窗 {ROI}（送检放大 {args.size / max(ROI[2]-ROI[0], ROI[3]-ROI[1]):.2f}×）')

K = get_camera_intrinsic_matrix(env.sim, CAM, args.size, args.size)
depth_est = float(np.linalg.norm(get_camera_extrinsic_matrix(env.sim, CAM)[:3, 3]))
print(f'送检 {args.size}×{args.size}  f={K[0,0]:.0f}px  相机光心距桌面≈{depth_est:.2f}m'
      f'  → 1px≈{depth_est / K[0,0] * 1000:.1f}mm   模式: {"GT-only" if args.gt_only else "VLM"}')

rows, flip_std, header_printed = [], None, False
for i in range(args.runs):
    obs = env.reset()
    cube = env.sim.data.body_xpos[env.cube_body_id].copy()
    raw = env.sim.render(camera_name=CAM, height=args.size, width=args.size)
    mask = cube_mask(args.size)
    if mask.sum() == 0:
        rows.append(dict(run=i, note='no_seg'))
        print(f'run{i}: ❌ 分割真值为空（遮挡?），跳过')
        continue

    gt_uv = world_to_pixel(cube, args.size)                    # 标准约定下的 GT 像素
    ys, xs = np.nonzero(mask)
    cen = (xs.mean(), ys.mean())

    if flip_std is None:                                        # 坑位#5 行序自检（仅首跑判定）
        e_std = np.hypot(cen[0] - gt_uv[0], cen[1] - gt_uv[1])
        e_flp = np.hypot(cen[0] - gt_uv[0], (args.size - 1 - cen[1]) - gt_uv[1])
        flip_std = e_flp < e_std
        raw84 = np.asarray(Image.fromarray(raw).resize((84, 84)))
        obs84 = obs['agentview_image']
        mae = lambda a, b: float(np.abs(a.astype(int) - b.astype(int)).mean())
        print(f'[行序自检] 分割质心 vs GT投影: 原样 err={e_std:.1f}px / 翻转 err={e_flp:.1f}px'
              f'  → {"需 flipud" if flip_std else "原样即标准方向"}')
        print(f'[行序自检] raw缩84 vs obs84: 原样 MAE={mae(raw84, obs84):.1f} /'
              f' 翻转 MAE={mae(raw84[::-1], obs84):.1f}  → obs 帧{"与标准方向一致" if mae(raw84, obs84) <= mae(raw84[::-1], obs84) else "疑似翻转(警告!)"}')

    frame = raw[::-1] if flip_std else raw                      # 标准方向送检图（VLM 坐标系）
    mstd = mask[::-1] if flip_std else mask
    gys, gxs = np.nonzero(mstd)
    gt_bb = (float(gxs.min()), float(gys.min()), float(gxs.max()), float(gys.max()))

    jpg = f'/tmp/e5_frame_{i}.jpg'
    # 送检管线：[ROI 裁剪] → 方形 send×send（两种坐标语义数值恒等）→ 坐标按轴映射回全帧
    src = frame[ROI[1]:ROI[3], ROI[0]:ROI[2]] if ROI else frame
    sh, sw = src.shape[:2]
    Image.fromarray(src).resize((args.send, args.send), Image.LANCZOS).save(jpg, quality=92)

    if args.gt_only:
        det_bb, lat, grade = gt_bb, 0.0, 'SEG-GT'
        note = ''
    else:
        def map_back(bb):
            ox, oy = (ROI[0], ROI[1]) if ROI else (0, 0)
            return (ox + bb[0] / args.send * sw, oy + bb[1] / args.send * sh,
                    ox + bb[2] / args.send * sw, oy + bb[3] / args.send * sh)

        det_bb, lat, grade = call_vlm(jpg)
        note = ''
        if det_bb is not None:
            det_bb = map_back(det_bb)
            # 垃圾框治理：面积>25% 全帧（整图/半图框）→ 重查一次（run3/4 实测模式）
            if (det_bb[2] - det_bb[0]) * (det_bb[3] - det_bb[1]) > 0.25 * args.size ** 2:
                bb2, lat2, g2 = call_vlm(jpg)
                lat += lat2
                if bb2 is not None:
                    det_bb, grade, note = map_back(bb2), f'{g2}+retry', 'bigbox_retried'
                else:
                    note = 'bigbox_retry_failed'

    if det_bb is None:
        rows.append(dict(run=i, note=grade, latency_ms=lat))
        print(f'run{i}: ❌ 无检测 ({grade})')
        continue

    u, v = (det_bb[0] + det_bb[2]) / 2, (det_bb[1] + det_bb[3]) / 2      # bbox 中心（手册 2.2 ③）
    tgt = pixel_to_world_xy(u, v, args.size)
    err_cm = float(np.linalg.norm(tgt - cube[:2]) * 100)
    gt84 = world_to_pixel(cube, 84)
    det84 = ((det_bb[0] + det_bb[2]) / 2 * 84 / args.size, (det_bb[1] + det_bb[3]) / 2 * 84 / args.size)
    d84 = float(np.hypot(det84[0] - gt84[0], det84[1] - gt84[1]))
    if not args.gt_only:                                                  # IoU vs 分割真值（E1 客观法）
        ix1, iy1 = max(det_bb[0], gt_bb[0]), max(det_bb[1], gt_bb[1])
        ix2, iy2 = min(det_bb[2], gt_bb[2]), min(det_bb[3], gt_bb[3])
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        union = (det_bb[2] - det_bb[0]) * (det_bb[3] - det_bb[1]) + \
                (gt_bb[2] - gt_bb[0]) * (gt_bb[3] - gt_bb[1]) - inter
        iou = inter / union if union > 0 else 0.0
    else:
        iou = 1.0

    rows.append(dict(run=i, x1=det_bb[0], y1=det_bb[1], x2=det_bb[2], y2=det_bb[3],
                     tgt_x=tgt[0], tgt_y=tgt[1], cube_x=cube[0], cube_y=cube[1],
                     err_xy_cm=err_cm, dist84_px=d84, iou=iou, grade=grade,
                     latency_ms=lat, note=note))
    mark = '✓' if err_cm <= 8 else '✗'
    print(f'run{i}: bbox=({det_bb[0]:.0f},{det_bb[1]:.0f},{det_bb[2]:.0f},{det_bb[3]:.0f})'
          f' tgt=({tgt[0]:+.3f},{tgt[1]:+.3f}) cube=({cube[0]:+.3f},{cube[1]:+.3f})'
          f' err={err_cm:5.2f}cm d84={d84:4.1f}px IoU={iou:.2f} {grade} {mark} {note}')

    if i < args.save_first:
        draw_overlay(frame, None if args.gt_only else det_bb, gt_bb, gt_uv,
                     f'run{i} err={err_cm:.2f}cm {grade}',
                     os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  f'e5_coord_run{i}.jpg'))

# ---------- 汇总 ----------
ok = [r for r in rows if 'err_xy_cm' in r]
os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
with open(args.csv, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['run', 'x1', 'y1', 'x2', 'y2', 'tgt_x', 'tgt_y',
                                      'cube_x', 'cube_y', 'err_xy_cm', 'dist84_px',
                                      'iou', 'grade', 'latency_ms', 'note'])
    w.writeheader()
    for r in rows:
        w.writerow({k: (f'{r[k]:.4f}' if isinstance(r.get(k), float) else r.get(k, ''))
                    for k in w.fieldnames})
if ok:
    errs = [r['err_xy_cm'] for r in ok]
    print(f'\n==== 汇总（{len(ok)}/{args.runs} 有效）====')
    print(f'xy 误差: 均值 {np.mean(errs):.2f}cm / 最大 {np.max(errs):.2f}cm /'
          f' 达标(≤8cm) {sum(e <= 8 for e in errs)}/{len(ok)}')
    print(f'84 系中心距: 均值 {np.mean([r["dist84_px"] for r in ok]):.1f}px  '
          f'IoU(对分割GT): 均值 {np.mean([r["iou"] for r in ok]):.2f}')
    print(f'CSV → {os.path.abspath(args.csv)}')
    if args.gt_only:
        print('（GT-only 模式：err 应在毫米级——验证的是坐标链数学本身；VLM 行待 llama-server 上线后补测）')

if node is not None:
    node.destroy_node()
    rclpy.shutdown()
