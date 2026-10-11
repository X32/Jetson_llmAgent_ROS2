"""【E9-B】YOLO 训练数据渲染器：从 image_v15.hdf5 的 states 确定性重放 → 渲染 480×640 agentview
+ 同分辨率分割 mask → 自动标注（mask 外接矩形，与 YOLO 输出语义一致）。

【设计要点（计划压测结论落位）】
  - 重放 = set_state_from_flattened + forward（已验证 body_xpos 与 hdf5 obs/object 逐位一致）
  - cube 半边长 0.020-0.022 → 真实边长 4.0-4.4cm → 480×640 下 bbox 约 24×33px（分辨率足够）
  - 每集 t∈{0,8,16,24,32,40,48,58} 8 帧 × 200 集 = 1600 帧；t=0 全覆盖（评测只考 t=0）
  - 划分复用 hdf5 mask['20_percent']（40 集 val / 160 集 train，与 ACT 训练同款划分）
  - mask 空（方块被手完全遮住）→ 存空标签 = 背景负样本（YOLO 语义合法）
  - 每帧 meta 记 GT 中心像素/世界坐标/带宽 → 验证脚本（yolo_val_world.py）零 robosuite 依赖
  - 质检：bbox 尺寸 sanity（w/h ∈ [15,80]px，期望 ~24-33px）+ 8 张叠加预览图人审

用法（EGL 独占，评测/训练不并发）:
  unset PYTHONPATH && MUJOCO_GL=egl python yolo_render_frames.py [--limit 4 冒烟]
"""
import argparse
import json
import os

import cv2
import h5py
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--hdf5', default='/mnt/apfs/workplace/act/data/lift_ph/image_v15.hdf5')
ap.add_argument('--out', default='/mnt/nvme01/workplace/yolo/datasets/lift_cube')
ap.add_argument('--height', type=int, default=480)
ap.add_argument('--width', type=int, default=640)
ap.add_argument('--frames', default='0,8,16,24,32,40,48,58')
ap.add_argument('--limit', type=int, default=0, help='>0 只处理前 N 集（冒烟）')
args = ap.parse_args()
FRAMES = [int(x) for x in args.frames.split(',')]

# ---------- 环境（只需 agentview；sim.render 任意分辨率随时可渲） ----------
import robosuite                                        # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402
from robosuite.utils.camera_utils import (              # noqa: E402
    get_camera_transform_matrix, get_camera_intrinsic_matrix, get_camera_extrinsic_matrix)

env = robosuite.make('Lift', robots=['Panda'],
                     controller_configs=load_controller_config(default_controller='OSC_POSE'),
                     has_renderer=False, has_offscreen_renderer=True, use_camera_obs=True,
                     camera_names=['agentview'], camera_heights=84, camera_widths=84,
                     ignore_done=True)
CAM, H, W = 'agentview', args.height, args.width
PLANE_Z = 0.831                                         # 求交平面 = t=0 方块中心实测均值

# 像素↔世界平面单应（相机固定 → 一次性导出，验证/评测脚本零 robosuite 依赖）
# 【约定坑】robosuite 的 Ex 是"相机→世界"（e5 验证件：d_w = Ex[:3,:3]@相机射线）——
# 建世界→像素单应须取转置+平移变号：x_cam = Rᵀ(X−o)。与下方 world_to_pixel 数值对账防再翻车。
_K = get_camera_intrinsic_matrix(env.sim, CAM, H, W)
_Ex = get_camera_extrinsic_matrix(env.sim, CAM)
_Rwc, _o = _Ex[:3, :3].T, _Ex[:3, 3]                    # 世界→相机旋转 / 相机光心（世界系）
_Hwp = _K @ np.hstack([_Rwc[:, 0:1], _Rwc[:, 1:2], (_Rwc @ (-_o) + _Rwc[:, 2] * PLANE_Z)[:, None]])
os.makedirs(args.out, exist_ok=True)
json.dump(dict(H_w2p=_Hwp.tolist(), plane_z=PLANE_Z, H=H, W=W),
          open(f'{args.out}/cam.json', 'w'))
_bid = env.cube_body_id
_adr, _num = int(env.sim.model.body_geomadr[_bid]), int(env.sim.model.body_geomnum[_bid])
GEOMS = list(range(_adr, _adr + _num))


def world_to_pixel(p):
    T = get_camera_transform_matrix(env.sim, CAM, H, W)
    q = T @ np.array([p[0], p[1], p[2], 1.0])
    return q[0] / q[2], q[1] / q[2]


# 单应数值对账：3 个平面点，两条路（单应 vs 官方 transform）投影差必须 <0.1px
for _pt in [(0.0, 0.0, PLANE_Z), (0.02, -0.01, PLANE_Z), (-0.02, 0.025, PLANE_Z)]:
    _u1, _v1 = world_to_pixel(_pt)
    _q = _Hwp @ np.array([_pt[0], _pt[1], 1.0])
    _du = abs(_u1 - _q[0] / _q[2]) + abs(_v1 - _q[1] / _q[2])
    assert _du < 0.1, f'单应对账失败 {_pt}: 偏 {_du:.2f}px（旋转约定又翻了？）'


# ---------- 输出骨架 ----------
for split in ('train', 'val'):
    os.makedirs(f'{args.out}/images/{split}', exist_ok=True)
    os.makedirs(f'{args.out}/labels/{split}', exist_ok=True)
os.makedirs(f'{args.out}/preview', exist_ok=True)

f = h5py.File(args.hdf5, 'r')
val_set = {s.decode() for s in f['mask']['20_percent'][()]}
demos = sorted(f['data'].keys(), key=lambda k: int(k.split('_')[1]))
if args.limit:
    demos = demos[:args.limit]

meta_f = open(f'{args.out}/meta.jsonl', 'w')
n_img, n_neg, n_bad = 0, 0, 0
sizes = []
for di, demo in enumerate(demos):
    g = f['data'][demo]
    states = np.array(g['states'])
    split = 'val' if demo in val_set else 'train'
    env.reset()                                          # 每集一次 reset，随后逐帧 set_state
    for t in FRAMES:
        if t >= states.shape[0]:
            continue
        env.sim.set_state_from_flattened(states[t])
        env.sim.forward()
        img = env.sim.render(camera_name=CAM, height=H, width=W)[::-1]      # RGB，flipud（E5 坑位#5）
        seg = np.asarray(env.sim.render(camera_name=CAM, height=H, width=W,
                                        segmentation=True))[::-1]            # 同行序翻转
        m = np.isin(seg[..., 1].astype(int), GEOMS)
        gt_w = env.sim.data.body_xpos[_bid].copy()
        gu, gv = world_to_pixel(gt_w)
        stem = f'{demo}_t{t:02d}'
        # ---- 标注：mask 外接矩形 ----
        if m.any():
            ys, xs = np.nonzero(m)
            x1, x2, y1, y2 = xs.min(), xs.max(), ys.min(), ys.max()
            bw, bh = int(x2 - x1), int(y2 - y1)
            sizes.append((bw, bh))
            if not (15 <= bw <= 80 and 15 <= bh <= 80):
                n_bad += 1
                print(f'[!] {stem} bbox 越界 sanity: w={bw} h={bh}（期望 15-80px）')
            cx, cy = (x1 + x2) / 2 / W, (y1 + y2) / 2 / H
            open(f'{args.out}/labels/{split}/{stem}.txt', 'w').write(
                f'0 {cx:.6f} {cy:.6f} {bw / W:.6f} {bh / H:.6f}\n')
        else:
            x1 = y1 = x2 = y2 = -1                        # 空标签=负样本
            open(f'{args.out}/labels/{split}/{stem}.txt', 'w').write('')
            n_neg += 1
        cv2.imwrite(f'{args.out}/images/{split}/{stem}.jpg',
                    cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92])
        # ---- 质心 vs GT 投影中心交叉核对（防 K/行序静默病） ----
        cen_d = (np.hypot((x1 + x2) / 2 - gu, (y1 + y2) / 2 - gv)
                 if m.any() else float('nan'))
        meta_f.write(json.dumps(dict(
            img=f'images/{split}/{stem}.jpg', split=split, t=t,
            bbox=[int(x1), int(y1), int(x2), int(y2)],
            gt_px=[round(gu, 2), round(gv, 2)], gt_world=[round(float(v), 4) for v in gt_w],
            center_err_px=None if np.isnan(cen_d) else round(float(cen_d), 2),
            H=H, W=W)) + '\n')
        n_img += 1
        # 前 8 张存叠加预览（人审）
        if n_img <= 8:
            vis = cv2.cvtColor(img.copy(), cv2.COLOR_RGB2BGR)
            if m.any():
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.circle(vis, (int(gu), int(gv)), 4, (255, 0, 0), -1)
            cv2.imwrite(f'{args.out}/preview/{stem}.jpg', vis)
    if (di + 1) % 20 == 0:
        print(f'  [{di + 1}/{len(demos)} 集] 已渲染 {n_img} 帧（负样本 {n_neg}）')

meta_f.close()
f.close()
sizes = np.array(sizes) if sizes else np.zeros((0, 2))
if len(sizes):
    print(f'\n==== 渲染完成：{n_img} 帧（train/val 按集划分，负样本 {n_neg}）====')
    print(f'bbox 尺寸 px: w 中位 {np.median(sizes[:, 0]):.0f} [{sizes[:, 0].min()}-{sizes[:, 0].max()}], '
          f'h 中位 {np.median(sizes[:, 1]):.0f} [{sizes[:, 1].min()}-{sizes[:, 1].max()}]（期望 ~24-33）')
    print(f'sanity 越界帧数: {n_bad}')
    errs = [json.loads(l)['center_err_px'] for l in open(f'{args.out}/meta.jsonl')
            if json.loads(l)['center_err_px'] is not None]
    print(f'标注中心-GT投影 距离: 中位 {np.median(errs):.1f}px p95 {np.percentile(errs, 95):.1f}px（<5px=标注可信）')
# 单类 yaml
open(f'{args.out}/lift_cube.yaml', 'w').write(
    f'path: {args.out}\ntrain: images/train\nval: images/val\nnc: 1\nnames: [cube]\n')
print(f'yaml → {args.out}/lift_cube.yaml')
