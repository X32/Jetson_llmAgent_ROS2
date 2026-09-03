#!/bin/bash
# ROS2 环境配置脚本 - 确保 DOMAIN_ID 一致

echo "=== 配置 ROS2 环境 ==="

# 激活 Python 环境
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env

# Source ROS2
source install/setup.bash

# 设置统一的 ROS_DOMAIN_ID
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0

echo "✅ ROS2 环境配置完成"
echo "   ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "   ROS_LOCALHOST_ONLY: $ROS_LOCALHOST_ONLY"
echo ""
echo "现在可以运行 ROS2 命令了！"
echo "  - ros2 node list"
echo "  - ros2 topic list"
echo "  - ros2 topic pub /voice_text ..."
