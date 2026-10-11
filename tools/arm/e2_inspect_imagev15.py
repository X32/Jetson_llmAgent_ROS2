"""E2 中间产物检查器：解析 robomimic 格式的补拍大文件 image_v15.hdf5（200 条 demo 挤一个文件）

与 e2_inspect_episode.py 的分工：
  - e2_inspect_episode.py 吃 ACT 格式单条 episode（observations/images/...，record_sim_episodes.py / e2_adapter.py 的产物）
  - 本脚本吃 robomimic 格式多 demo 文件（data/demo_N/obs/...，即 dataset_states_to_obs.py 补拍脚本的直接产物）

用法：
  unset PYTHONPATH
  /mnt/apfs/workplace/venvs/act/bin/python tools/arm/e2_inspect_imagev15.py \
      --file /mnt/apfs/workplace/act/data/lift_ph/image_v15.hdf5 [--demo 0] [--frames 0,29,58]

输出：
  1) 全局概览：demo 总数、步数分布、root/data attrs（含 env_args）
  2) 选中 demo 的结构树（每个数据集 形状/dtype/范围；next_obs 与 obs 同构，只数不清点）
  3) 相机样帧 PNG → <outdir>/（默认 <hdf5所在目录>/inspect_image_v15/）
"""
import argparse
import os

import cv2
import h5py
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--file', default='/mnt/apfs/workplace/act/data/lift_ph/image_v15.hdf5')
ap.add_argument('--demo', type=int, default=0, help='细看的 demo 编号（默认 0）')
ap.add_argument('--frames', default=None, help='导出帧号，逗号分隔（默认 0,中点,末帧）')
ap.add_argument('--outdir', default=None, help='样帧输出目录（默认 <hdf5所在目录>/inspect_image_v15）')
args = ap.parse_args()

with h5py.File(args.file, 'r') as root:
    print(f'=== {args.file} ({os.path.getsize(args.file)/1e6:.1f} MB) ===')
    for k, v in root.attrs.items():
        print(f'attrs[{k}] = {v}')

    if 'data' not in root:
        raise SystemExit('✗ 没有 data 组 —— 这不是 robomimic 格式？')
    g = root['data']
    for k, v in g.attrs.items():  # robomimic 惯例：env_args / total 就挂在这
        s = str(v)
        print(f'data.attrs[{k}] = {s[:220]}{"…" if len(s) > 220 else ""}')

    demos = sorted(g.keys(), key=lambda s: int(s.split('_')[1]))
    print(f'\n共 {len(demos)} 条 demo')

    # ---------- 全局步数分布（只读 shape，不碰数据，秒回） ----------
    def demo_len(dg):
        if 'actions' in dg:
            return dg['actions'].shape[0]
        obs = dg['obs']
        return obs[sorted(obs.keys())[0]].shape[0]

    lens = [demo_len(g[d]) for d in demos]
    print(f'步数: min={min(lens)} max={max(lens)} mean={sum(lens)/len(lens):.1f}  总转移={sum(lens)}')

    # ---------- 选中 demo 的结构树 ----------
    dname = f'demo_{args.demo}'
    dg = g[dname]
    print(f'\n--- {dname} (attrs: ' + ', '.join(f'{k}={v}' for k, v in dg.attrs.items()) + ') ---')
    data = {}

    def walk(name, obj):
        if isinstance(obj, h5py.Dataset):
            d = obj[()]  # 单条 demo 的图像也就 ~1.2MB/相机，无压力
            data[name] = d
            if d.dtype == np.uint8:
                rng = f'min={d.min()} max={d.max()}'
            else:
                rng = f'min={d.min():+.4f} max={d.max():+.4f} mean={d.mean():+.4f}'
            print(f'  {name:<48} {str(d.shape):<22} {d.dtype}  {rng}')

    dg.visititems(walk)

    # ---------- 导出相机样帧（跳过 next_obs——与 obs 逐帧错位重复，图一样） ----------
    outdir = args.outdir or os.path.join(os.path.dirname(args.file), 'inspect_image_v15')
    os.makedirs(outdir, exist_ok=True)

    # 注意：dg.visititems 给出的键名是相对 demo 组的（obs/...），不带 demo_N/ 前缀
    img_keys = [k for k in data if k.startswith('obs/') and k.endswith('_image')]
    for ik in img_keys:
        imgs = data[ik]
        T = imgs.shape[0]
        cam = ik.rsplit('/', 1)[-1].replace('_image', '')
        frames = [int(x) for x in args.frames.split(',')] if args.frames else sorted({0, T // 2, T - 1})
        for t in frames:
            t = min(t, T - 1)
            rgb = imgs[t]
            png = os.path.join(outdir, f'demo{args.demo}_{cam}_t{t:03d}.png')
            cv2.imwrite(png, rgb[:, :, ::-1])  # RGB→BGR 再写盘
            print(f'  🖼  {png}  ({rgb.shape[1]}x{rgb.shape[0]}x{rgb.shape[2]})')

    # ---------- eef 轨迹图（有 robot0_eef_pos 才画） ----------
    eef_key = 'obs/robot0_eef_pos'
    if eef_key in data:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            eef = data[eef_key]
            fig, axs = plt.subplots(3, 1, figsize=(8, 5), sharex=True)
            for i, ax_name in enumerate('xyz'):
                axs[i].plot(eef[:, i])
                axs[i].set_ylabel(f'eef_{ax_name} (m)', fontsize=7)
                axs[i].tick_params(labelsize=6)
            fig.suptitle(f'{dname} end-effector position', fontsize=10)
            fig.tight_layout()
            plot_path = os.path.join(outdir, f'demo{args.demo}_eef_pos.png')
            fig.savefig(plot_path, dpi=110)
            plt.close(fig)
            print(f'  📈 {plot_path}')
        except Exception as e:
            print(f'  (跳过 eef 轨迹图: {e})')

    print(f'✅ 解析完成，样帧在 {outdir}/')
