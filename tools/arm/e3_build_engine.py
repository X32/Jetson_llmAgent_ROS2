"""E3 Step2: ONNX → TensorRT 双引擎构建（FP32 / FP16）

TRT 8.6.1 来源：NGC 容器 nvcr.io/nvidia/tensorrt:23.12-py3 提取
（pip 元包渠道死——构建时访问 pypi.nvidia.com 不通；tarball 要账号，容器是唯一免登录官方渠道）

运行环境（重要，两行都要）:
  unset PYTHONPATH
  export LD_LIBRARY_PATH=/mnt/apfs/workplace/trt-862/lib:/mnt/apfs/workplace/venvs/act/lib/python3.10/site-packages/torch/lib

产物: /mnt/apfs/workplace/act/e3/act_fp32.engine + act_fp16.engine + build_log_*.txt
记录: build 耗时、engine 大小、UNSUPPORTED_NODE 清单（预期空——ACT 纯标准算子）
"""
import os
import sys
import time

import tensorrt as trt

ONNX = '/mnt/apfs/workplace/act/e3/act_lift_ph.onnx'
OUT = '/mnt/apfs/workplace/act/e3'

logger = trt.Logger(trt.Logger.WARNING)
trt.init_libnvinfer_plugins(logger, '')

for fp16 in (False, True):
    tag = 'fp16' if fp16 else 'fp32'
    t0 = time.time()
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)
    if not parser.parse_from_file(ONNX):
        for i in range(parser.num_errors):
            print(f'  [parser] {parser.get_error(i)}')
        sys.exit(1)
    cfg = builder.create_builder_config()
    cfg.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 4 << 30)   # 4GB 工作区
    if fp16:
        cfg.set_flag(trt.BuilderFlag.FP16)   # TRT 自带逐层精度回退（Pascal FP16 弱，回退属预期）
    engine = builder.build_serialized_network(network, cfg)
    if engine is None:
        print(f'❌ {tag} build 失败'); sys.exit(1)
    path = os.path.join(OUT, f'act_{tag}.engine')
    with open(path, 'wb') as f:
        f.write(engine)
    dt = time.time() - t0
    print(f'✅ {tag}: {os.path.getsize(path)/1e6:.1f}MB, build {dt:.0f}s（序列化 blob 已落盘）')
print('完成：FP32/FP16 双引擎（坑位#5 未触发 = 无不支持算子，plugin 走回退练习）')
