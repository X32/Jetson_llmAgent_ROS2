#!/bin/bash

# ROS2 摄像头节点依赖安装脚本

echo "=== 安装ROS2摄像头节点依赖 ==="
echo

# 检查是否有sudo权限
if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本"
    echo "命令: sudo $0"
    exit 1
fi

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 更新包列表
echo -e "${BLUE}更新包列表...${NC}"
apt update

# 安装ROS2摄像头相关包
echo -e "${BLUE}安装ROS2摄像头相关包...${NC}"
apt install -y \
    ros-humble-cv-bridge \
    ros-humble-vision-opencv \
    ros-humble-image-transport \
    ros-humble-camera-calibration-parsers \
    ros-humble-camera-info-manager \
    ros-humble-image-view \
    ros-humble-compressed-image-transport

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ ROS2摄像头包安装成功${NC}"
else
    echo -e "${YELLOW}✗ ROS2摄像头包安装失败${NC}"
    exit 1
fi

# 安装OpenCV开发库
echo -e "${BLUE}安装OpenCV开发库...${NC}"
apt install -y \
    libopencv-dev \
    python3-opencv \
    python3-numpy

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ OpenCV安装成功${NC}"
else
    echo -e "${YELLOW}✗ OpenCV安装失败${NC}"
    exit 1
fi

# 安装USB摄像头工具
echo -e "${BLUE}安装USB摄像头工具...${NC}"
apt install -y \
    v4l-utils \
    guvcview \
    ffmpeg

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 摄像头工具安装成功${NC}"
else
    echo -e "${YELLOW}✗ 摄像头工具安装失败${NC}"
    exit 1
fi

# 设置用户权限
echo -e "${BLUE}设置摄像头设备权限...${NC}"
if id "ubuntu" &>/dev/null; then
    usermod -a -G video ubuntu
    echo -e "${GREEN}✓ 用户 ubuntu 已添加到 video 组${NC}"
elif id "$SUDO_USER" &>/dev/null; then
    usermod -a -G video $SUDO_USER
    echo -e "${GREEN}✓ 用户 $SUDO_USER 已添加到 video 组${NC}"
else
    echo -e "${YELLOW}⚠ 无法自动添加用户到video组${NC}"
    echo "请手动运行: sudo usermod -a -G video YOUR_USERNAME"
fi

echo
echo -e "${GREEN}=== 依赖安装完成！===${NC}"
echo
echo -e "${YELLOW}下一步操作:${NC}"
echo "1. 重新登录系统以使用户组生效"
echo "2. 检查摄像头设备: ls -la /dev/video*"
echo "3. 测试摄像头: v4l2-ctl --list-devices"
echo "4. 编译摄像头节点:"
echo "   cd /mnt/apfs/workplace/ROS2"
echo "   source /opt/ros/humble/setup.bash"
echo "   colcon build --packages-select my_package"
echo "5. 运行测试: ./camera_test.sh"
echo
echo -e "${YELLOW}注意: 如果OpenCV版本有问题，可能需要指定特定版本${NC}"