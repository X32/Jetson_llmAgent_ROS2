#!/usr/bin/env python3
"""E1: Qwen2.5-VL grounding 输出解析器——从最严到最松的兜底链 + 尺度探测
用法: python3 parse_grounding.py "模型原始输出" [送检图宽 送检图高]
  注意：宽高要传**送检图**（模型实际看到的那张，如 --resize 后的 768x576）的尺寸；
  输出 pixel= 相对送检图。要标注更高清原图，再按 原图/送检图 比例线性放大。
统一约定：parse() 内部一律归一化到 0-1000 空间（尺度探测负责甄别），下游换算只有一套公式。"""
import re
import sys


def normalize_fullwidth(s):
    """全角→半角（中文模型爱输出全角括号/逗号）"""
    out = []
    for ch in s:
        c = ord(ch)
        if c == 0x3000:
            out.append(' ')
        elif 0xFF01 <= c <= 0xFF5E:
            out.append(chr(c - 0xFEE0))
        else:
            out.append(ch)
    return ''.join(out)


NUM = r'([\d.]+)'
PAIR = r'\(\s*' + NUM + r'\s*[,，]\s*' + NUM + r'\s*\)'

# 兜底链：命中即停，级别从最严到最松（与 Day11 文本模式 FC 的多级解析同思路）
PATTERNS = [
    # A: 标准标签 <box>(x1,y1),(x2,y2)</box>（闭合标签缺失/截断也命中，label 另取）
    ('A', re.compile(
        r'<box>\s*' + PAIR + r'\s*[,，]\s*' + PAIR + r'\s*(?:</box>|$)', re.I)),
    # A2: llama.cpp 特殊 token 未剥落变体
    ('A2', re.compile(
        r'<\|box_start\|>\s*' + PAIR + r'\s*[,，]\s*' + PAIR
        + r'\s*<\|box_end\|>')),
    # A3: 单括号四连数 <box>(x1,y1,x2,y2)——E1 Step1 红杯实测新变体 V8：
    #    3B 把两组坐标挤进一个括号，且缺右括号和 </box>
    ('A3', re.compile(
        r'<box>\s*\(?\s*' + NUM + r'\s*[,，]\s*' + NUM + r'\s*[,，]\s*'
        + NUM + r'\s*[,，]\s*' + NUM + r'\s*\)?', re.I)),
    # B: JSON 变体 {"bbox": [x1,y1,x2,y2]}
    ('B', re.compile(
        r'"(?:bbox|box)"\s*:\s*\[\s*' + NUM + r'\s*,\s*' + NUM
        + r'\s*,\s*' + NUM + r'\s*,\s*' + NUM + r'\s*\]')),
    # C: 裸坐标对（散文化兜底）
    ('C', re.compile(PAIR + r'\s*[,，]\s*' + PAIR)),
    # C2: 裸四连数（无括号无标签的最后兜底，V8 的彻底散文化形态）
    ('C2', re.compile(
        r'(?<![\d.])' + NUM + r'\s*[,，]\s*' + NUM + r'\s*[,，]\s*'
        + NUM + r'\s*[,，]\s*' + NUM + r'(?![\d.])')),
]
REF_RE = re.compile(r'<ref>(.*?)</ref>', re.I)
REF_TOKEN_RE = re.compile(r'<\|object_ref_start\|>(.*?)<\|object_ref_end\|>')
# 格式规整度分级（模型不给真置信度，用规整度做代理，见手册 2.3）
# A3=0.8：<box> 标签在但括号结构变形；C2=0.3：只剩裸数字，可信度最低
CONF = {'A': 1.0, 'A2': 0.9, 'A3': 0.8, 'B': 0.6, 'C': 0.4, 'C2': 0.3}


def to_norm(vals, w=None, h=None):
    """四元组 → 0-1000 归一化空间。尺度探测三档（先实证后假设，见手册 2.2 修正）：
    ① max ≤ 1.5 → 0-1 浮点漂移，×1000 拉回
    ② 传了送检图尺寸且 x≤宽、y≤高 → 按 V9 实测解释：Qwen2.5-VL 输出的是送检图
       绝对像素（0-1000 是 Qwen2-VL 旧约定；红杯实测像素假设 85-90% 命中 vs 归一化 35%）
    ③ 其余 → 按官方 0-1000 处理。两可时按②（2.5 官方约定），原文永远留日志、调试图复核。"""
    mx = max(vals)
    if mx <= 1.5:
        return [v * 1000.0 for v in vals]
    x1, y1, x2, y2 = vals
    if w and h and x1 <= w and x2 <= w and y1 <= h and y2 <= h:
        return [x1 / w * 1000.0, y1 / h * 1000.0, x2 / w * 1000.0, y2 / h * 1000.0]
    return list(vals)


def parse(text, w=None, h=None):
    """→ [(grade, label, x1,y1,x2,y2 …均统一到 0-1000 空间)]；失败返回 []
    w/h 传**送检图**尺寸（模型实际看到的图），供尺度探测用"""
    t = normalize_fullwidth(text)
    # 所有 ref 按出现顺序收集，与 bbox 按位置配对（双目标场景：红球+蓝碗各归各）
    refs = [m.group(1).strip() for m in REF_RE.finditer(t)]
    refs += [m.group(1).strip() for m in REF_TOKEN_RE.finditer(t)]
    for grade, pat in PATTERNS:
        found = []
        for i, g in enumerate(pat.finditer(t)):
            vals = to_norm([float(v) for v in g.groups()], w, h)
            # 数量对得上→按序配对；对不上→回填首个 ref（节点层再用请求词兜底）
            label = refs[i] if i < len(refs) else (refs[0] if refs else None)
            found.append((grade, label, *vals))
        if found:
            return found                      # 命中一级就不再降级
    return []


if __name__ == '__main__':
    results = parse(sys.argv[1],
                    *(int(v) for v in sys.argv[2:4])) if len(sys.argv) > 3 \
        else parse(sys.argv[1])
    if not results:
        print('解析失败：无坐标模式命中，请人工看原文')
        sys.exit(1)
    for grade, label, x1, y1, x2, y2 in results:
        line = f'[{grade}] label={label!r} norm=({x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f})'
        if len(sys.argv) > 3:
            w, h = int(sys.argv[2]), int(sys.argv[3])
            line += (f' → pixel=({round(x1/1000*w)},{round(y1/1000*h)},'
                     f'{round(x2/1000*w)},{round(y2/1000*h)}) @ {w}x{h}')
        print(line)
