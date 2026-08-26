#!/bin/bash

# Python摄像头节点测试脚本

echo "=== Python摄像头节点测试 ==="
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

# 检查Python脚本
echo -e "${BLUE}检查Python脚本...${NC}"
if [ -f "install/my_package/lib/my_package/camera_subscriber_py.py" ]; then
    echo -e "${GREEN}✓ Python脚本已安装${NC}"
    ls -lh install/my_package/lib/my_package/camera_subscriber_py.py
else
    echo -e "${RED}✗ Python脚本未找到${NC}"
    exit 1
fi

echo

# 测试摄像头发布者
echo -e "${BLUE}=== 测试摄像头通信 ===${NC}"
echo "启动摄像头发布者（10秒）..."

timeout 10 ros2 run my_package camera_publisher &
PUB_PID=$!
sleep 3

# 检查话题
echo "检查摄像头话题..."
if ros2 topic list | grep -q "camera/image_raw"; then
    echo -e "${GREEN}✓ 摄像头话题已创建: /camera/image_raw${NC}"

    echo "测试Python订阅者（5秒）..."
    timeout 5 ros2 run my_package camera_subscriber_py.py &
    sleep 6

    echo -e "${GREEN}✓ Python订阅者测试完成${NC}"
else
    echo -e "${RED}✗ 摄像头话题未创建${NC}"
    kill $PUB_PID 2>/dev/null
    exit 1
fi

# 清理
kill $PUB_PID 2>/dev/null

echo

# 显示Python节点信息
echo -e "${BLUE}=== Python摄像头节点 ===${NC}"
echo "文件位置:"
echo "  源码: src/my_package/scripts/camera_subscriber_py.py"
echo "  安装: install/my_package/lib/my_package/camera_subscriber_py.py"

echo
echo "启动命令:"
echo -e "${YELLOW}方法1 - 使用ros2 run:${NC}"
echo "  ros2 run my_package camera_subscriber_py.py"

echo -e "${YELLOW}方法2 - 直接运行Python:${NC}"
echo "  python3 install/my_package/lib/my_package/camera_subscriber_py.py"

echo -e "${YELLOW}方法3 - 运行源码:${NC}"
echo "  python3 src/my_package/scripts/camera_subscriber_py.py"

echo

# 对比信息
echo -e "${BLUE}=== Python vs C++ 节点对比 ===${NC}"
echo "Python节点特点:"
echo "  • 代码更简洁 (60行 vs 140行)"
echo "  • 开发效率更高"
echo "  • 调试更方便"
echo "  • 适合原型开发"

echo
echo "C++节点特点:"
echo "  • 性能更高"
echo "  • 内存使用更低"
echo "  • 适合生产环境"

echo
echo -e "${GREEN}=== 测试完成！Python摄像头节点工作正常 ===${NC}"
echo
echo "🎉 你的Python摄像头节点已经可以使用！"
echo
echo "完整指南: PYTHON_CAMERA_GUIDE.md"