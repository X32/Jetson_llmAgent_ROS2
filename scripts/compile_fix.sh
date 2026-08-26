#!/bin/bash

# 摄像头节点编译修复脚本

echo "=== ROS2摄像头节点编译修复 ==="
echo

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}1. 检查ROS2环境...${NC}"

if [ -z "$AMENT_PREFIX_PATH" ]; then
    echo -e "${YELLOW}ROS2环境未设置，正在加载...${NC}"
    source /opt/ros/humble/setup.bash
fi

echo -e "${GREEN}✓ ROS2环境已准备${NC}"
echo

echo -e "${BLUE}2. 检查example_interfaces包...${NC}"

if ! dpkg -l | grep -q "ros-humble-example-interfaces"; then
    echo -e "${YELLOW}example_interfaces包未安装${NC}"
    echo "请运行: sudo apt install ros-humble-example-interfaces"
    echo "或运行: sudo ./fix_dependencies.sh"
    echo
    echo "尝试自动安装（需要sudo权限）..."

    if sudo apt install -y ros-humble-example-interfaces; then
        echo -e "${GREEN}✓ example_interfaces安装成功${NC}"
    else
        echo -e "${RED}✗ 自动安装失败，请手动安装${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ example_interfaces已安装${NC}"
fi

echo

echo -e "${BLUE}3. 清理旧的编译文件...${NC}"
cd /mnt/apfs/workplace/ROS2
rm -rf build install logs
echo -e "${GREEN}✓ 清理完成${NC}"
echo

echo -e "${BLUE}4. 开始编译...${NC}"
source /opt/ros/humble/setup.bash
colcon build --packages-select my_package

if [ $? -eq 0 ]; then
    echo
    echo -e "${GREEN}=== 编译成功！===${NC}"
    echo
    echo -e "${YELLOW}现在可以运行摄像头节点了:${NC}"
    echo "source install/setup.bash"
    echo "ros2 run my_package simple_camera_publisher"

else
    echo
    echo -e "${RED}=== 编译失败 ===${NC}"
    echo "请检查上面的错误信息"
    exit 1
fi