#!/usr/bin/env python3
"""E1 Step3: 模型 bbox vs 颜色分割真值 的客观 IoU 判定（坑位#10：VLM 自查不可信，用像素算）
用法: python3 e1_iou_eval.py testN.png x1 y1 x2 y2 目标名
  坐标为原图像素（送检图坐标先按 原图/送检图 比例放大再传入）。
真值来源: 颜色分割，可视化存档 test1_gt.jpg / test2_gt.jpg。
判定: IoU≥0.5 ✓ / 0.3~0.5 △ / <0.3 ✗；同图多目标取 IoU 最大者判归属——
  若最大者不是被问目标 → 属性绑定失败（问红球框住乐高）。"""
import sys

GT = {  # 颜色分割真值，原图 2304x1728 像素坐标系
    ('test2.png', '红球'): (549, 909, 954, 1363),
    ('test2.png', '蓝碗'): (1034, 404, 1769, 1175),
    ('test1.png', '红球'): (308, 697, 591, 978),
    ('test1.png', '乐高'): (859, 667, 1217, 1049),
    ('test1.png', '橘子'): (1458, 540, 2018, 1086),
}


def inter_area(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)


def iou(a, b):
    inter = inter_area(a, b)
    union = ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / union if union else 0.0


def main():
    img = sys.argv[1]
    box = tuple(int(v) for v in sys.argv[2:6])
    asked = sys.argv[6]
    cands = {n: g for (f, n), g in GT.items() if f == img}
    if not cands:
        print(f'没有 {img} 的真值'); sys.exit(2)

    rows = sorted(((iou(box, g), n) for n, g in cands.items()), reverse=True)
    best_iou, best_name = rows[0]
    gt = cands[asked]
    cov = inter_area(box, gt) / ((gt[2] - gt[0]) * (gt[3] - gt[1]))

    for v, n in rows:
        print(f'  IoU vs {n}: {v:.2f}')
    print(f'  真值覆盖率(框住 asked 的比例): {cov:.0%}')

    if best_name != asked:
        print(f'✗ 属性绑定失败: 问的是「{asked}」，框住的却是「{best_name}」')
        sys.exit(1)
    if best_iou >= 0.5:
        print(f'✓ 命中「{asked}」 IoU={best_iou:.2f}')
    elif best_iou >= 0.3:
        print(f'△ 边缘命中「{asked}」 IoU={best_iou:.2f}')
    else:
        print(f'✗ 未命中「{asked}」 IoU={best_iou:.2f}')
        sys.exit(1)


if __name__ == '__main__':
    main()
