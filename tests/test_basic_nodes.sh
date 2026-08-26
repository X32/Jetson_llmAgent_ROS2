#!/bin/bash

# ROS2基础节点测试脚本

echo "=== ROS2基础节点测试 ==="
echo

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查ROS2环境
if [ -z "$AMENT_PREFIX_PATH" ]; then
    echo -e "${YELLOW}加载ROS2环境...${NC}"
    source /opt/ros/humble/setup.bash
fi

cd /mnt/apfs/workplace/ROS2
source install/setup.bash

echo -e "${GREEN}✓ ROS2环境已准备${NC}"
echo

# 测试菜单
echo -e "${BLUE}选择要测试的功能:${NC}"
echo "1. 话题通信测试 (publisher + subscriber)"
echo "2. 服务通信测试 (server + client)"
echo "3. 综合节点测试 (comprehensive)"
echo "4. 全部测试"
echo "5. 查看节点状态"
echo "0. 退出"
echo

read -p "请选择 (0-5): " choice

case $choice in
    1)
        echo -e "${BLUE}=== 话题通信测试 ===${NC}"
        echo "启动发布者节点（5秒）..."
        timeout 5 ros2 run my_package publisher_node &
        sleep 2

        echo "检查话题..."
        if ros2 topic list | grep -q topic; then
            echo -e "${GREEN}✓ 话题 /topic 已创建${NC}"

            echo "测试订阅者（3秒）..."
            timeout 3 ros2 run my_package subscriber_node &
            sleep 4
        else
            echo -e "${YELLOW}✗ 话题未创建${NC}"
        fi
        ;;

    2)
        echo -e "${BLUE}=== 服务通信测试 ===${NC}"
        echo "启动服务端（8秒）..."
        timeout 8 ros2 run my_package service_server &
        sleep 2

        echo "检查服务..."
        if ros2 service list | grep -q add_two_ints; then
            echo -e "${GREEN}✓ 服务 /add_two_ints 已创建${NC}"

            echo "启动客户端..."
            timeout 6 ros2 run my_package service_client &
            sleep 7
        else
            echo -e "${YELLOW}✗ 服务未创建${NC}"
        fi
        ;;

    3)
        echo -e "${BLUE}=== 综合节点测试 ===${NC}"
        echo "启动综合节点（5秒）..."
        timeout 5 ros2 run my_package comprehensive_node &
        sleep 6

        echo "检查话题..."
        ros2 topic list
        ;;

    4)
        echo -e "${BLUE}=== 全部测试 ===${NC}"

        echo "1. 话题通信测试..."
        timeout 3 ros2 run my_package publisher_node &
        sleep 2
        ros2 topic list | grep topic && echo -e "${GREEN}✓ 话题正常${NC}" || echo -e "${YELLOW}✗ 话题失败${NC}"

        echo "2. 服务通信测试..."
        timeout 5 ros2 run my_package service_server &
        sleep 2
        ros2 service list | grep add_two_ints && echo -e "${GREEN}✓ 服务正常${NC}" || echo -e "${YELLOW}✗ 服务失败${NC}"

        echo "3. 综合节点测试..."
        timeout 3 ros2 run my_package comprehensive_node &
        sleep 4
        ;;

    5)
        echo -e "${BLUE}=== 节点状态 ===${NC}"
        echo "可执行文件:"
        ls -lh install/my_package/lib/my_package/

        echo
        echo "话题列表:"
        timeout 2 ros2 run my_package publisher_node &
        sleep 2
        ros2 topic list
        ;;

    0)
        echo "退出测试"
        exit 0
        ;;

    *)
        echo "无效选择"
        exit 1
        ;;
esac

echo
echo -e "${GREEN}=== 测试完成 ===${NC}"
echo
echo "手动运行命令:"
echo "source /opt/ros/humble/setup.bash"
echo "source /mnt/apfs/workplace/ROS2/install/setup.bash"
echo "ros2 run my_package <node_name>"