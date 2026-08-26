#!/bin/bash

# 快速测试Python节点修复

echo "=== Python节点修复验证 ==="
echo

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}检查Python脚本语法...${NC}"

# 加载ROS2环境
source /opt/ros/humble/setup.bash
cd /mnt/apfs/workplace/ROS2
source install/setup.bash

# 检查Python脚本语法
python3 -m py_compile install/my_package/lib/my_package/camera_subscriber_py.py

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Python脚本语法正确${NC}"
else
    echo -e "${YELLOW}✗ Python脚本有语法错误${NC}"
    exit 1
fi

echo
echo -e "${BLUE}检查修复的关键部分...${NC}"

# 检查修复的代码行
if grep -q "if self.frame_count > 0 and self.last_fps > 0:" install/my_package/lib/my_package/camera_subscriber_py.py; then
    echo -e "${GREEN}✓ 发布者状态检查已修复${NC}"
else
    echo -e "${YELLOW}⚠ 修复可能未应用${NC}"
fi

echo
echo -e "${GREEN}=== 修复验证完成 ===${NC}"
echo
echo "现在可以运行Python摄像头节点了："
echo "  ros2 run my_package camera_subscriber_py.py"
echo
echo "注意：确保摄像头发布者正在运行"
echo "如果摄像头被占用，先停止其他摄像头程序"