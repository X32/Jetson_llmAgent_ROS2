#!/bin/bash

# ROS2节点停止脚本

echo "=== ROS2节点停止工具 ==="
echo

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查ROS2环境
if [ -z "$AMENT_PREFIX_PATH" ]; then
    echo -e "${YELLOW}加载ROS2环境...${NC}"
    source /opt/ros/humble/setup.bash
fi

echo -e "${BLUE}当前运行的ROS2节点:${NC}"
ros2 node list

echo

# 菜单
echo -e "${BLUE}选择停止方式:${NC}"
echo "1. 停止所有摄像头节点"
echo "2. 停止所有基础节点"
echo "3. 停止所有ROS2节点"
echo "4. 停止特定节点（手动输入）"
echo "5. 查看topic状态"
echo "6. 清理ROS2守护进程"
echo "0. 退出"
echo

read -p "请选择 (0-6): " choice

case $choice in
    1)
        echo -e "${YELLOW}停止摄像头节点...${NC}"
        nodes=("camera_publisher" "camera_subscriber" "simple_camera_publisher")
        for node in "${nodes[@]}"; do
            if pgrep -x "$node" > /dev/null; then
                killall "$node" 2>/dev/null
                echo -e "${GREEN}✓ 已停止: $node${NC}"
            else
                echo -e "${YELLOW}⚠ 未运行: $node${NC}"
            fi
        done
        ;;

    2)
        echo -e "${YELLOW}停止基础节点...${NC}"
        nodes=("publisher_node" "subscriber_node" "comprehensive_node" "service_server" "service_client")
        for node in "${nodes[@]}"; do
            if pgrep -x "$node" > /dev/null; then
                killall "$node" 2>/dev/null
                echo -e "${GREEN}✓ 已停止: $node${NC}"
            else
                echo -e "${YELLOW}⚠ 未运行: $node${NC}"
            fi
        done
        ;;

    3)
        echo -e "${YELLOW}停止所有ROS2节点...${NC}"
        # 停止常见的ROS2可执行文件
        killall -9 camera_publisher 2>/dev/null
        killall -9 camera_subscriber 2>/dev/null
        killall -9 simple_camera_publisher 2>/dev/null
        killall -9 publisher_node 2>/dev/null
        killall -9 subscriber_node 2>/dev/null
        killall -9 comprehensive_node 2>/dev/null
        killall -9 service_server 2>/dev/null
        killall -9 service_client 2>/dev/null

        echo -e "${GREEN}✓ 所有节点已停止${NC}"
        ;;

    4)
        echo -e "${YELLOW}停止特定节点...${NC}"
        read -p "输入节点名称（如 camera_publisher）: " node_name

        if pgrep -x "$node_name" > /dev/null; then
            killall "$node_name" 2>/dev/null
            echo -e "${GREEN}✓ 已停止: $node_name${NC}"
        else
            echo -e "${RED}✗ 节点未运行: $node_name${NC}"
        fi
        ;;

    5)
        echo -e "${BLUE}当前topic状态:${NC}"
        ros2 topic list
        echo
        echo -e "${BLUE}活跃节点:${NC}"
        ros2 node list
        ;;

    6)
        echo -e "${YELLOW}清理ROS2守护进程...${NC}"
        ros2 daemon stop --rm
        echo -e "${GREEN}✓ 守护进程已清理${NC}"
        echo "重新启动: ros2 daemon start"
        ;;

    0)
        echo "退出"
        exit 0
        ;;

    *)
        echo -e "${RED}无效选择${NC}"
        exit 1
        ;;
esac

echo
echo -e "${BLUE}停止后状态:${NC}"
echo "活跃节点:"
ros2 node list || echo "无活跃节点"
echo
echo "活跃topic:"
ros2 topic list || echo "无活跃topic"

echo
echo -e "${GREEN}=== 停止完成 ===${NC}"