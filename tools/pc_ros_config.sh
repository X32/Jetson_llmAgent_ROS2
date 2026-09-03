#!/bin/bash
# PC ROS2 跨平台通信配置
source /opt/ros/humble/setup.bash
source install/setup.bash
# 设置环境变量
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
# DDS 使用系统默认的 Fast DDS（与 Jetson 端保持一致，两端必须相同）
unset RMW_IMPLEMENTATION   # 确保使用默认 Fast DDS

# 自动获取本机 IP
PC_IP=$(ip route get 1 2>/dev/null | awk '{print $3;exit}')

# 如果无法获取，提示用户手动输入
if [ -z "$PC_IP" ] || [ "$PC_IP" = "FAILED" ]; then
    echo "无法自动获取 IP 地址，请手动输入:"
    read -p "请输入本机 IP 地址: " PC_IP
fi

export ROS_IP=$PC_IP

# 显示网络信息
echo "=== PC ROS2 配置 ==="
echo "ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "ROS_LOCALHOST_ONLY: $ROS_LOCALHOST_ONLY"
echo "DDS 中间件: Fast DDS (系统默认，与 Jetson 一致)"
echo "ROS_IP: $ROS_IP"
echo "网络接口:"
ip addr show | grep "inet " | grep -v "127.0.0.1"
echo ""
echo "✅ PC 配置完成"
echo "现在可以发送消息: ros2 topic pub --once /voice_text std_msgs/msg/String \"data: '测试指令'\""