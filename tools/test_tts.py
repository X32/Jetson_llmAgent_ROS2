#!/usr/bin/env python3
"""TTS 裸测：合成一句话并播放，打印 RTF/语速
用法：python3 tools/test_tts.py ["文本"] [speed] [模型目录名]
  speed: 1.0=原始语速；melo 实测偏快需 ~0.5，matcha 正常语速用 1.0
  模型:  matcha（默认，标准普通话）| melo（中英混说，实测语速快/音量低）

实测坑（sherpa-onnx 1.13.6，PC）：
  1. melo 输出不像普通话+语速~10字/秒+峰值仅±0.08 → 换 matcha + 统一峰值归一化
  2. 1.13.x Python API 不支持 melo_tts={...} 关键字，必须嵌套 Config 构造
"""
import sys
import time

import numpy as np
import sherpa_onnx
import sounddevice as sd

text = sys.argv[1] if len(sys.argv) > 1 else '你好，前方零点八七米处有障碍物，请注意避让。'
speed = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
model_name = sys.argv[3] if len(sys.argv) > 3 else 'matcha'
model_dir = f'models/tts/{model_name}'

if model_name == 'matcha':
    # matcha 两段式：声学模型（mel谱）+ vocoder（波形）
    # rule_fsts 关键：number.fst 把阿拉伯数字转成中文读法（"2米"→"两米"），
    # 不加则数字被直接丢弃（实测 Ignore OOV '2'）
    tts_config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            matcha=sherpa_onnx.OfflineTtsMatchaModelConfig(
                acoustic_model=f'{model_dir}/model-steps-3.onnx',
                vocoder=f'{model_dir}/hifigan_v2.onnx',
                lexicon=f'{model_dir}/lexicon.txt',
                tokens=f'{model_dir}/tokens.txt',
                dict_dir=f'{model_dir}/dict',
            ),
            num_threads=2,
        ),
        rule_fsts=f'{model_dir}/number.fst,{model_dir}/phone.fst',
    )
else:  # melo（vits 通道）
    tts_config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=f'{model_dir}/model.onnx',
                lexicon=f'{model_dir}/lexicon.txt',
                tokens=f'{model_dir}/tokens.txt',
                data_dir=f'{model_dir}/dict',
            ),
            num_threads=2,
        ),
    )

tts = sherpa_onnx.OfflineTts(tts_config)

t0 = time.perf_counter()
audio = tts.generate(text, speed=speed)
gen_s = time.perf_counter() - t0

samples = np.asarray(audio.samples, dtype=np.float32)
# 峰值归一化到 ±0.85（melo 幅度异常低必须归一化；matcha 幅度正常也不吃亏）
peak = np.abs(samples).max()
if peak > 1e-4:
    samples = samples / peak * 0.85

play_s = len(samples) / audio.sample_rate
n_chars = len([c for c in text if c.isalnum() or '一' <= c <= '鿿'])
print(f'[{model_name}] {gen_s:.2f}s 生成 → {play_s:.2f}s 音频 | RTF={gen_s/play_s:.3f} | '
      f'语速 {n_chars/play_s:.1f} 字/秒（正常4-6） | 采样率 {audio.sample_rate}')

sd.play(samples, samplerate=audio.sample_rate)
sd.wait()
