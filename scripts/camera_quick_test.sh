#!/bin/bash

# 摄像头快速测试脚本

echo "=== USB摄像头快速测试 ==="
echo

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查摄像头设备
echo -e "${BLUE}1. 检查摄像头设备...${NC}"
if [ -e "/dev/video0" ]; then
    echo -e "${GREEN}✓ 找到摄像头设备 /dev/video0${NC}"
    ls -la /dev/video* | head -3
else
    echo -e "${RED}✗ 未找到摄像头设备${NC}"
    exit 1
fi

echo

# 检查摄像头信息
echo -e "${BLUE}2. 查询摄像头详细信息...${NC}"
v4l2-ctl --device=/dev/video0 --all | head -20

echo

# 测试摄像头图像采集
echo -e "${BLUE}3. 测试摄像头图像采集（5秒）...${NC}"
echo "使用ffplay测试摄像头..."

# 检查是否安装了ffmpeg
if command -v ffplay &> /dev/null; then
    timeout 5 ffplay -fflags nobuffer -flags low_delay -framedrop /dev/video0 -v quiet &
    FFPLAY_PID=$!
    sleep 5
    kill $FFPLAY_PID 2>/dev/null
    echo -e "${GREEN}✓ 摄像头图像采集测试完成${NC}"
else
    echo -e "${YELLOW}⚠ ffplay未安装，跳过图像测试${NC}"
    echo "安装命令: sudo apt install ffmpeg"
fi

echo

# 检查用户权限
echo -e "${BLUE}4. 检查用户权限...${NC}"
if groups | grep -q video; then
    echo -e "${GREEN}✓ 用户在video组中${NC}"
else
    echo -e "${YELLOW}⚠ 用户不在video组中${NC}"
    echo "添加命令: sudo usermod -a -G video \$USER"
    echo "然后重新登录系统"
fi

echo

# 检查ROS2环境
echo -e "${BLUE}5. 检查ROS2环境...${NC}"
if [ -z "$AMENT_PREFIX_PATH" ]; then
    echo -e "${YELLOW}⚠ ROS2环境未设置${NC}"
    echo "运行: source /opt/ros/humble/setup.bash"
else
    echo -e "${GREEN}✓ ROS2环境已设置${NC}"
fi

echo

# 检查编译状态
echo -e "${BLUE}6. 检查摄像头节点编译状态...${NC}"
if [ -f "/mnt/apfs/workplace/ROS2/install/my_package/lib/my_package/camera_publisher" ]; then
    echo -e "${GREEN}✓ 摄像头发布者已编译${NC}"
    if [ -f "/mnt/apfs/workplace/ROS2/install/my_package/lib/my_package/camera_subscriber" ]; then
        echo -e "${GREEN}✓ 摄像头订阅者已编译${NC}"
    else
        echo -e "${YELLOW}⚠ 摄像头订阅者未编译${NC}"
    fi
else
    echo -e "${YELLOW}⚠ 摄像头节点未编译${NC}"
    echo "编译命令:"
    echo "cd /mnt/apfs/workplace/ROS2"
    echo "source /opt/ros/humble/setup.bash"
    echo "colcon build --packages-select my_package"
fi

echo

# 提供快速启动命令
echo -e "${BLUE}=== 快速启动命令 ===${NC}"
echo -e "${GREEN}启动摄像头发布者:${NC}"
echo "cd /mnt/apfs/workplace/ROS2"
echo "source /opt/ros/humble/setup.bash"
echo "source install/setup.bash"
echo "ros2 run my_package camera_publisher"

echo
echo -e "${GREEN}启动摄像头订阅者（新终端）:${NC}"
echo "cd /mnt/apfs/workplace/ROS2"
echo "source /opt/ros/humble/setup.bash"
echo "source install/setup.bash"
echo "ros2 run my_package camera_subscriber"

echo
echo -e "${GREEN}监控摄像头话题（新终端）:${NC}"
echo "ros2 topic hz /camera/image_raw"
echo "ros2 run rqt_image_view rqt_image_view"

echo
echo -e "${BLUE}=== 测试完成 ===${NC}"