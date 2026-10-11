"""【E2-R4·P0-2】失败模式离线分类：扫 e2_eval_debug.py 落盘的 e2_debug_ep*.npz，出 F1-F6 频次表。

用法:
  python3 e2_debug_classify.py --dir /mnt/apfs/workplace/act/ckpt_lift_ph_v2 [--probe]

分类树（对失败集按优先级判定；成功集仅作对照组统计）:
  F3 打飞/推走 : 首次合爪指令前方块 xy 位移 > 5cm（无合爪则看全程）——接近段过冲
  F1 未接近    : min(eef-cube xy 距) > 3cm —— 视觉/接近段问题，重查询救不了
  F1' 未下压   : eef_z_min > 0.85（演示真抓降到 ~0.825-0.83）—— 没下探到抓取高度
  F2 抓空      : 有合爪翻转 + 方块基本没动 + z 从未接近线 —— 精定位问题
  F4 举不够    : 方块 z 抬升 > 2mm 但从未过线（过线即成功，故"抓起掉落"为空集）——重查询最可能救
  F5 超时无进展: 全程方块几乎没动、夹爪也没合 —— 政策性瘫住
  F6 其他

阈值来源：cube 初态 z≈0.831（±3cm xy 均匀采样），成功线 0.84（lift.py:417）。
"""
import argparse
import glob
import os

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('--dir', default='/mnt/apfs/workplace/act/ckpt_lift_ph_v2')
ap.add_argument('--probe', action='store_true', help='逐集打印特征明细')
args = ap.parse_args()

Z_LINE = 0.844          # 成功判定实际阈值（table+0.04，判成功即 break → 失败集 z_max 必低于此）
D_XY_FAR = 0.03         # F1: 3cm 未接近
EEF_Z_HIGH = 0.85       # F1': 未下压线（演示 min(eef_z) ~0.825）
XY_PUSH = 0.05          # F3: 5cm 推走
Z_RISE_PARTIAL = 0.002  # F4: 抬升 2mm 算"抓到了"

rows = []
for f in sorted(glob.glob(os.path.join(args.dir, 'e2_debug_ep*.npz'))):
    d = np.load(f)
    eef, grip, cube, act = d['eef'], d['grip'], d['cube'], d['act']
    ok, done_t = bool(d['ok']), int(d['done_t'])
    cube0 = cube[0]
    d_xy = np.linalg.norm(eef[:, :2] - cube[:, :2], axis=1)
    flips = np.nonzero(act[:, 6] != act[0, 6])[0]
    t_flip = int(flips[0]) if len(flips) else -1
    disp = np.linalg.norm(cube[:, :2] - cube0[:2], axis=1)
    xy_disp = float(disp.max())
    xy_disp_pre = float(disp[:t_flip].max()) if t_flip > 0 else xy_disp
    z_max = float(cube[:, 2].max())
    z_rise = z_max - float(cube0[2])
    # 夹爪两指符号对称（reset 实测 [+0.0208,-0.0208]），均值恒~0 无信息——用指距（开≈0.042，合≈0）
    gsep = np.abs(grip[:, 0] - grip[:, 1])
    grip_travel = float(gsep[0] - gsep.min())           # 从初始开度收拢了多少
    rows.append(dict(ep=os.path.basename(f), ok=ok, done_t=done_t, t_flip=t_flip,
                     min_d_xy=float(d_xy.min()), eef_z_min=float(eef[:, 2].min()),
                     z_max=z_max, z_rise=z_rise, xy_disp=xy_disp,
                     xy_disp_pre=xy_disp_pre, grip_travel=grip_travel))


def classify(r):
    if r['ok']:
        return 'OK'
    if r['xy_disp_pre'] > XY_PUSH:
        return 'F3 打飞/推走'
    if r['min_d_xy'] > D_XY_FAR:
        return 'F1 未接近'
    if r['eef_z_min'] > EEF_Z_HIGH:
        return "F1' 未下压"
    if r['z_rise'] > Z_RISE_PARTIAL:
        return 'F4 举不够'
    if r['t_flip'] >= 0:
        return 'F2 抓空'
    return 'F5 超时无进展'


for r in rows:
    r['cls'] = classify(r)

fails = [r for r in rows if not r['ok']]
succs = [r for r in rows if r['ok']]
print(f'共 {len(rows)} 集（成功 {len(succs)} / 失败 {len(fails)}）\n')
print('=== 失败分类频次 ===')
order = ['F1 未接近', "F1' 未下压", 'F2 抓空', 'F3 打飞/推走', 'F4 举不够', 'F5 超时无进展', 'F6 其他']
for c in order + [x for x in {r['cls'] for r in fails} if x not in order]:
    n = sum(1 for r in fails if r['cls'] == c)
    if n:
        print(f'  {c:<12} {n:>3}  ({n/max(len(fails),1):.0%})')

print('\n=== 成功集对照组（特征中位数 [p25, p75]）===')
if succs:
    for k in ('done_t', 'min_d_xy', 'eef_z_min', 'z_rise', 'grip_travel'):
        v = np.array([r[k] for r in succs])
        print(f'  {k:<12} med={np.median(v):.3f}  [{np.percentile(v,25):.3f}, {np.percentile(v,75):.3f}]')

if args.probe:
    print('\n=== 逐集明细 ===')
    for r in rows:
        print(f'  {r["ep"]:<18} {r["cls"]:<12} t_flip={r["t_flip"]:>3} min_d_xy={r["min_d_xy"]:.3f} '
              f'eef_z_min={r["eef_z_min"]:.3f} z_max={r["z_max"]:.3f} z_rise={r["z_rise"]:.3f} '
              f'xy_disp={r["xy_disp"]:.3f} grip={r["grip_travel"]:.5f}')
