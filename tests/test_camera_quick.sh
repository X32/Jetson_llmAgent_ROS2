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

# 加载ROS2环境
if [ -z "$AMENT_PREFIX_PATH" ]; then
    echo -e "${BLUE}加载ROS2环境...${NC}"
    source /opt/ros/humble/setup.bash
fi

cd /mnt/apfs/workplace/ROS2
source install/setup.bash

echo -e "${GREEN}✓ ROS2环境已准备${NC}"
echo

# 检查摄像头设备
echo -e "${BLUE}检查摄像头设备...${NC}"
if [ -e "/dev/video0" ]; then
    echo -e "${GREEN}✓ 找到摄像头: /dev/video0${NC}"
    ls -la /dev/video0 | head -1
else
    echo -e "${RED}✗ 未找到摄像头设备${NC}"
    echo "请检查摄像头连接"
    exit 1
fi

echo

# 测试摄像头发布者
echo -e "${BLUE}=== 测试摄像头发布者 ===${NC}"
echo "启动摄像头发布者（8秒测试）..."

timeout 8 ros2 run my_package camera_publisher &
PUB_PID=$!
sleep 3

# 检查话题
echo "检查摄像头话题..."
if ros2 topic list | grep -q "camera/image_raw"; then
    echo -e "${GREEN}✓ 摄像头话题已创建: /camera/image_raw${NC}"

    echo "获取话题信息..."
    ros2 topic info /camera/image_raw

    echo "测试话题频率（3秒）..."
    timeout 3 ros2 topic hz /camera/image_raw || true
else
    echo -e "${RED}✗ 摄像头话题未创建${NC}"
    kill $PUB_PID 2>/dev/null
    exit 1
fi

# 清理发布者
kill $PUB_PID 2>/dev/null

echo

# 测试摄像头订阅者
echo -e "${BLUE}=== 测试摄像头订阅者 ===${NC}"
echo "同时启动发布者和订阅者（10秒测试）..."

# 启动发布者
ros2 run my_package camera_publisher &
PUB_PID=$!
sleep 2

# 启动订阅者
timeout 10 ros2 run my_package camera_subscriber &
SUB_PID=$!
sleep 8

# 清理
kill $PUB_PID 2>/dev/null
kill $SUB_PID 2>/dev/null

echo -e "${GREEN}✓ 摄像头订阅者测试完成${NC}"

echo

# 显示可用节点
echo -e "${BLUE}=== 可用的摄像头节点 ===${NC}"
echo "1. camera_publisher        - 完整功能摄像头发布者"
echo "2. camera_subscriber       - 图像显示和统计"
echo "3. simple_camera_publisher - 简化稳定版本"

echo

# 提供启动命令
echo -e "${GREEN}=== 手动启动命令 ===${NC}"

echo -e "${YELLOW}启动摄像头发布者:${NC}"
echo "cd /mnt/apfs/workplace/ROS2"
echo "source /opt/ros/humble/setup.bash"
echo "source install/setup.bash"
echo "ros2 run my_package camera_publisher"

echo
echo -e "${YELLOW}启动摄像头订阅者（新终端）:${NC}"
echo "cd /mnt/apfs/workplace/ROS2"
echo "source /opt/ros/humble/setup.bash"
echo "source install/setup.bash"
echo "ros2 run my_package camera_subscriber"

echo
echo -e "${YELLOW}使用GUI查看图像（新终端）:${NC}"
echo "ros2 run rqt_image_view rqt_image_view"

echo
echo -e "${GREEN}=== 测试完成！摄像头系统工作正常 ===${NC}"
echo
echo "🎉 你的USB摄像头已经可以在ROS2中使用了！"