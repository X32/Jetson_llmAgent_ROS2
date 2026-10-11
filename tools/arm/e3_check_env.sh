#!/usr/bin/env bash
# E3 工具链完整性自检（报告 §5.5）：TRT 部署链每个部件一页体检表
# 核对对象 = 报告 §5.3 的全部提取件 + venv 钉死包 + E3 产物 + 固定运行环境
# 用法:  bash /mnt/apfs/workplace/ROS2/tools/arm/e3_check_env.sh [--smoke]
#   --smoke  额外做一次 TRT 引擎反序列化冒烟（重检，数秒）
# 退出码 = 失败项数（0 = 工具链完整）
set -u
PY=/mnt/apfs/workplace/venvs/act/bin/python
TRT_LIB=/mnt/apfs/workplace/trt-862/lib
E3DIR=/mnt/apfs/workplace/act/e3
CKPT=/mnt/apfs/workplace/act/ckpt_lift_ph_v2

unset PYTHONPATH                                    # E2 惯例：防 ROS2 泄漏（坑位#8）
TORCH_LIB=$($PY -c "import os,torch;print(os.path.join(os.path.dirname(torch.__file__),'lib'))" 2>/dev/null)
export LD_LIBRARY_PATH="$TRT_LIB:${TORCH_LIB:-/nonexistent}"   # §5.3 固定运行环境，脚本自带

PASS=0; FAIL=0
ok()  { echo "✅ $1"; PASS=$((PASS+1)); }
bad() { echo "❌ $1"; FAIL=$((FAIL+1)); }

echo "==== E3 TRT 工具链体检 ===="

# ① GPU 与驱动
GPU_LINE=$(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null | head -1)
[ -n "$GPU_LINE" ] && ok "GPU/驱动: $GPU_LINE" || bad "GPU/驱动: nvidia-smi 不可用"

# ② venv 解释器
[ -x "$PY" ] && ok "venv python: $PY ($($PY --version 2>&1 | cut -d' ' -f2))" \
              || bad "venv python 缺失: $PY（E2 §3.1 钉版环境）"

# ③ python 包（含版本钉死检查）
pycheck() {  # pycheck <描述> <断言代码>
  $PY -c "$2" >/dev/null 2>&1 && ok "$1" || bad "$1"
}
pycheck "numpy==1.26.4 钉死（坑位#2 两度复刻的高危项）" \
        "import numpy; assert numpy.__version__=='1.26.4'"
pycheck "torch + CUDA 可用（1080 Ti / cu121）" \
        "import torch; assert torch.cuda.is_available()"
pycheck "onnx + onnxruntime（L1 对齐件）" \
        "import onnx, onnxruntime"
pycheck "h5py（读 lift_ph_act 观测）" \
        "import h5py"
pycheck "tensorrt==8.6.1（NGC 容器提取件，进 venv）" \
        "import tensorrt; assert tensorrt.__version__=='8.6.1'"

# ④ TRT 库文件（容器提取落 /mnt/apfs，坑位#3 缺啥补啥清单）
# 注：TRT 8.6 已把 myelin 编译进 libnvinfer.so 主库，容器内无独立 libmyelin.so——
#     runbook 第4步 cp 命令里的 libmyelin* 通配是 8.0 时代写法，匹配为空、无害
#     （2026-09-25 实证：ldd libnvinfer 零缺库 + 引擎反序列化冒烟通过）
for so in libnvinfer libnvparsers libnvonnxparser; do
  ls "$TRT_LIB"/${so}*.so* >/dev/null 2>&1 && ok "TRT 库: ${so}*.so 在位" \
                                              || bad "TRT 库缺: $TRT_LIB/${so}*.so*"
done
[ -d "${TORCH_LIB:-}" ] && ok "torch/lib 在位（cudnn/cublas 复用，不另拷）: $TORCH_LIB" \
                          || bad "torch/lib 未定位（cudnn 复用链断）"

# ⑤ E3 产物（引擎/ONNX/元数据 + 反标准化统计量）
for f in act_lift_ph.onnx act_fp32.engine act_fp16.engine export_meta.json; do
  [ -s "$E3DIR/$f" ] && ok "产物: $f ($(du -h "$E3DIR/$f" | cut -f1))" \
                     || bad "产物缺: $E3DIR/$f"
done
[ -s "$CKPT/dataset_stats.pkl" ] && ok "dataset_stats.pkl（反标准化必需，坑位#5 同类）" \
                                   || bad "缺 $CKPT/dataset_stats.pkl"

# ⑥（可选）引擎反序列化冒烟——体检金字塔的最底一层实证
if [ "${1:-}" = "--smoke" ]; then
  $PY - <<'PYEOF' && ok "引擎反序列化冒烟: act_fp32.engine 可加载" \
                   || bad "引擎反序列化失败（查 LD_LIBRARY_PATH / 库完整性）"
import tensorrt as trt
with open('/mnt/apfs/workplace/act/e3/act_fp32.engine', 'rb') as f, \
     trt.Logger(trt.Logger.ERROR) as lg, trt.Runtime(lg) as rt:
    assert rt.deserialize_cuda_engine(f.read()) is not None
PYEOF
fi

echo "---- 体检结果: $PASS 通过 / $FAIL 失败 ----"
[ $FAIL -eq 0 ] && echo "✅ E3 工具链完整" \
               || echo "❌ 有缺失项——按报告 §5.3 容器提取 / §三第1步重钉 numpy 修复"
exit $FAIL
