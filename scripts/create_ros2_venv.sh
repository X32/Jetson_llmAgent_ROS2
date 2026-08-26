#!/bin/bash

# ROS2 Python虚拟环境创建脚本

echo "=== 创建ROS2 Python虚拟环境 ==="
echo

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查python3-venv包
echo -e "${BLUE}检查python3-venv包...${NC}"
if ! dpkg -l | grep -q "python3-venv"; then
    echo -e "${YELLOW}⚠ python3-venv包未安装${NC}"
    echo "需要安装python3-venv包"
    echo

    # 检查是否有sudo权限
    if [ "$EUID" -eq 0 ]; then
        echo "使用sudo安装python3-venv..."
        apt update
        apt install -y python3-venv
    else
        echo -e "${RED}请手动安装python3-venv:${NC}"
        echo "sudo apt install python3-venv"
        echo "然后重新运行此脚本"
        exit 1
    fi
fi

# 虚拟环境名称
VENV_NAME="ros2_camera_env"

echo -e "${BLUE}创建虚拟环境: ${VENV_NAME}${NC}"
echo

# 创建虚拟环境
python3 -m venv "${VENV_NAME}"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 虚拟环境创建成功${NC}"
else
    echo -e "${YELLOW}✗ 虚拟环境创建失败${NC}"
    exit 1
fi

echo
echo -e "${BLUE}激活虚拟环境...${NC}"
source "${VENV_NAME}/bin/activate"

echo
echo -e "${BLUE}升级pip...${NC}"
pip install --upgrade pip

echo
echo -e "${BLUE}安装ROS2基础依赖...${NC}"
pip install rclpy sensor-msgs-cv

echo
echo -e "${BLUE}安装图像处理依赖...${NC}"
pip install opencv-python-headless

echo
echo -e "${BLUE}安装cv_bridge...${NC}"
pip install cv_bridge

echo
echo -e "${BLUE}安装图像识别依赖...${NC}"
pip install onnxruntime torch torchvision pandas pillow

echo
echo -e "${BLUE}安装开发工具...${NC}"
pip install ipython jupyter matplotlib

echo
echo -e "${GREEN}=== 虚拟环境配置完成 ===${NC}"

echo
echo -e "${YELLOW}如何使用虚拟环境:${NC}"
echo
echo "激活虚拟环境:"
echo "  source ${VENV_NAME}/bin/activate"
echo
echo "在虚拟环境中运行ROS2节点:"
echo "  source /opt/ros/humble/setup.bash"
echo "  ros2 run my_package camera_recognition_subscriber.py"
echo
echo "退出虚拟环境:"
echo "  deactivate"
echo
echo "删除虚拟环境:"
echo "  rm -rf ${VENV_NAME}"

echo
echo -e "${GREEN}🎉 虚拟环境已准备就绪！${NC}"