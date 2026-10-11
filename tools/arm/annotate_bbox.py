#!/usr/bin/env python3
"""E1: 把解析出的像素 bbox 画回原图，肉眼核对（验收证据截图就用它）
用法: python3 annotate_bbox.py 原图.jpg x1 y1 x2 y2 [label]"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

# 坑位#8：老版 PIL 点阵字体遇中文直接 UnicodeEncodeError 崩溃（不止是显示方块）
# 优先加载系统 CJK 字体，找不到再用默认字体并把 label 降级成 ASCII
CJK_FONTS = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/truetype/arphic/uming.ttc',
]


def load_font(size=20):
    for p in CJK_FONTS:
        if os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size), None
            except Exception:
                pass
    return ImageFont.load_default(), 'ascii'


img = Image.open(sys.argv[1]).convert('RGB')
x1, y1, x2, y2 = (int(v) for v in sys.argv[2:6])
label = ' '.join(sys.argv[6:]) or 'target'
font, fallback = load_font()
if fallback == 'ascii':
    label = label.encode('ascii', 'replace').decode()
d = ImageDraw.Draw(img)
d.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=3)
d.text((x1, max(0, y1 - 24)), label, fill=(255, 0, 0), font=font)
out = sys.argv[1].rsplit('.', 1)[0] + '_bbox.jpg'
img.save(out)
print(f'已保存: {out}  图幅 {img.size[0]}x{img.size[1]}  字体: {"CJK" if fallback is None else "ASCII降级"}')
