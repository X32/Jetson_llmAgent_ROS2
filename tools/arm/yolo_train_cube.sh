#!/bin/bash
# 【E9-B】YOLO 方块检测训练（2026-10-09 实跑参数的存档版——当天用内联命令跑的，此件为复现脚本）
# 前置：① 数据已生成（tools/arm/yolo_render_frames.py）② venv /mnt/apfs/workplace/venvs/yolo（torch 2.1.0+cu121）
# 用法：bash yolo_train_cube.sh [冒烟=2轮|全量=150轮]，默认全量
# 当日实测：2 轮冒烟即 P=1.0 R=1.0 mAP50=0.995；150 轮 58 分钟 mAP50-95=0.993（1080 Ti）
set -e
EPOCHS=${1:-150}
NAME=${2:-v1}
cd /mnt/nvme01/workplace/yolo

/mnt/apfs/workplace/venvs/yolo/bin/python - <<EOF
from ultralytics import YOLO
m = YOLO('yolo26n.pt')
m.train(
    data='/mnt/nvme01/workplace/yolo/datasets/lift_cube/lift_cube.yaml',
    epochs=${EPOCHS},          # 冒烟传 2，全量 150
    patience=40,               # 连续 40 轮无进步提前收工
    imgsz=640, batch=16, seed=0,
    hsv_h=0.0,                 # 锁死色相扰动——方块靠"红色"识别，不能练到变色（本场景特有）
    device=0,
    project='/mnt/nvme01/workplace/yolo/runs/lift_cube', name='${NAME}', exist_ok=True)
p = m.export(format='onnx', opset=12)             # 导出 onnx（推理服务用）
print('EXPORTED:', p)
EOF

echo "==== 验收（t0-val 专尺：检出/世界系误差）===="
/mnt/apfs/workplace/venvs/yolo/bin/python /mnt/apfs/workplace/ROS2/tools/arm/yolo_val_world.py \
    --onnx /mnt/nvme01/workplace/yolo/runs/lift_cube/${NAME}/weights/best.onnx --t0-only
echo "验收线: 检出 ≥39/40、误差均值 ≤1cm、p95 ≤2cm（E9-A 定价: σ*=1cm）"
