#!/bin/bash

# 修复编译依赖脚本

echo "=== 安装ROS2编译所需的依赖 ==="
echo

# 检查是否有sudo权限
if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本"
    echo "命令: sudo $0"
    exit 1
fi

echo "更新包列表..."
apt update

echo "安装ROS2 example_interfaces包..."
apt install -y ros-humble-example_interfaces

echo "安装OpenCV相关依赖..."
apt install -y \
    libopencv-dev \
    python3-opencv \
    libboost-all-dev

echo "安装摄像头相关依赖..."
apt install -y \
    ros-humble-cv-bridge \
    ros-humble-vision-opencv \
    ros-humble-image-transport

echo
echo "=== 依赖安装完成 ==="
echo "现在可以运行编译命令了:"
echo "cd /mnt/apfs/workplace/ROS2"
echo "source /opt/ros/humble/setup.bash"
echo "colcon build --packages-select my_package"