#!/bin/bash
# Jetson ROS2 跨平台通信配置
# 注意: 系统使用默认的 Fast DDS，两端 DDS 实现必须一致

# 设置环境变量
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
# DDS 使用系统默认的 Fast DDS（ROS2 Humble 默认）
# 如 PC 端安装了 CycloneDDS，需两端统一，否则无法通信
unset RMW_IMPLEMENTATION   # 确保使用默认 Fast DDS

# 显示网络信息
echo "=== Jetson ROS2 配置 ==="
echo "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "ROS_LOCALHOST_ONLY: $ROS_LOCALHOST_ONLY"
echo "DDS 中间件: Fast DDS (系统默认)"
echo "网络接口:"
ip addr show | grep "inet " | grep -v "127.0.0.1"
echo ""
echo "✅ Jetson 配置完成"
echo "现在可以启动节点: LLAMACPP=1 ros2 run robot_agent llm_agent"