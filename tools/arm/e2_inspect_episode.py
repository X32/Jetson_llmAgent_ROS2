"""E2 数据集检查器：解析一条 ACT 官方格式 episode hdf5 —— 打印结构树 + 导出样帧 PNG

用途（对应 record_sim_episodes.py / e2_adapter.py 的产物，两种格式都兼容）：
  unset PYTHONPATH
  /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e2_inspect_episode.py \
      --file /mnt/apfs/workplace/act/data/episode_49.hdf5          # 官方双臂集(18GB那种)
  /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e2_inspect_episode.py \
      --file /mnt/apfs/workplace/act/data/lift_ph_act/episode_0.hdf5  # Lift 自训集(2.6MB那种)

输出：
  1) 终端：hdf5 树（每个数据集的 形状/dtype/数值范围）+ root attrs + qpos 各维摘要
  2) 落盘：<outdir>/ 下每个相机各导 --frames 指定的帧为 PNG（默认首/中/末 3 帧）
          外加 qpos_action.png 曲线图（官方 14 维 = 左右臂各 7；Lift 9 维）

注意：hdf5 里图像是 RGB；cv2.imwrite 要 BGR，所以写盘前翻一次通道。
"""
import argparse
import os

import cv2
import h5py
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--file', required=True, help='episode hdf5 路径')
ap.add_argument('--outdir', default=None, help='样帧输出目录（默认 <hdf5所在目录>/inspect_<文件名>）')
ap.add_argument('--frames', default=None, help='导出帧号，逗号分隔（默认 0,中点,末帧）')
args = ap.parse_args()

# ---------- 1. 打开文件，递归打印整棵树 ----------
with h5py.File(args.file, 'r') as root:
    print(f'=== {args.file} ({os.path.getsize(args.file)/1e6:.1f} MB) ===')
    for k, v in root.attrs.items():
        print(f'attrs[{k}] = {v}')

    def walk(name, obj):
        if isinstance(obj, h5py.Dataset):
            d = obj[()]  # 读全量（一条 episode 最大的也就是 352MB，内存无压力）
            if d.dtype == np.uint8:  # 图像：报告范围就够，不报均值
                rng = f'min={d.min()} max={d.max()}'
            else:
                rng = f'min={d.min():+.4f} max={d.max():+.4f} mean={d.mean():+.4f}'
            print(f'  {name:<38} {str(d.shape):<22} {d.dtype}  {rng}')
            return d
        return None

    # 走一遍树：打印 + 顺手把数据留在内存（一条 episode 最多 352MB，无压力）
    data = {}

    def walk(name, obj):
        if isinstance(obj, h5py.Dataset):
            d = obj[()]
            data[name] = d
            if d.dtype == np.uint8:  # 图像：报范围就够
                rng = f'min={d.min()} max={d.max()}'
            else:
                rng = f'min={d.min():+.4f} max={d.max():+.4f} mean={d.mean():+.4f}'
            print(f'  {name:<38} {str(d.shape):<22} {d.dtype}  {rng}')

    root.visititems(walk)

    # ---------- 2. 导出样帧 PNG ----------
    outdir = args.outdir or os.path.join(os.path.dirname(args.file),
                                         'inspect_' + os.path.splitext(os.path.basename(args.file))[0])
    os.makedirs(outdir, exist_ok=True)

    cam_keys = [k for k in data if k.startswith('observations/images')]
    frames = ([int(x) for x in args.frames.split(',')] if args.frames
              else None)
    for ck in cam_keys:
        imgs = data[ck]
        T = imgs.shape[0]
        cam = ck.rsplit('/', 1)[-1]
        if frames is None:
            frames = sorted({0, T // 2, T - 1})
        for t in frames:
            t = min(t, T - 1)
            rgb = imgs[t]
            png = os.path.join(outdir, f'{cam}_t{t:03d}.png')
            cv2.imwrite(png, rgb[:, :, ::-1])  # RGB→BGR 再写盘
            print(f'  🖼  {png}  ({rgb.shape[1]}x{rgb.shape[0]}x{rgb.shape[2]})')

    # ---------- 3. qpos / action 曲线 ----------
    if 'observations/qpos' in data and 'action' in data:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            qpos, action = data['observations/qpos'], data['action']
            nd = qpos.shape[1]
            fig, axs = plt.subplots(nd, 1, figsize=(8, 1.5 * nd), sharex=True)
            for i in range(nd):
                axs[i].plot(qpos[:, i], label='qpos(state)')
                if i < action.shape[1]:
                    axs[i].plot(range(1, len(action) + 1), action[:, i], '--', label='action(cmd)')
                axs[i].set_ylabel(f'dim{i}', fontsize=7)
                axs[i].tick_params(labelsize=6)
            axs[0].legend(fontsize=7)
            fig.suptitle('qpos vs action (per dim)', fontsize=10)
            fig.tight_layout()
            plot_path = os.path.join(outdir, 'qpos_action.png')
            fig.savefig(plot_path, dpi=110)
            plt.close(fig)
            print(f'  📈 {plot_path}')
        except Exception as e:  # matplotlib 缺席不挡结构输出
            print(f'  (跳过曲线图: {e})')

    print(f'✅ 解析完成，样帧在 {outdir}/')
