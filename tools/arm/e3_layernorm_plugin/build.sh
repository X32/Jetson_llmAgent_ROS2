#!/bin/bash
# E3 Step4: LayerNorm plugin 编译（在 NGC TRT 容器内跑——宿主机无 CUDA toolkit）
# 用法: bash build.sh
# 产物: libe2_layernorm_plugin.so（本目录，宿主机可 ctypes.CDLL 加载）
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
docker run --rm -v "$DIR":/src nvcr.io/nvidia/tensorrt:23.12-py3 bash -c "
  cd /src
  nvcc -shared -Xcompiler -fPIC -arch=sm_61 \
       -I/usr/include/x86_64-linux-gnu \
       -L/usr/lib/x86_64-linux-gnu -lnvinfer -lnvinfer_plugin \
       e3_layernorm_plugin.cu -o libe2_layernorm_plugin.so
  ls -lh libe2_layernorm_plugin.so"
