#!/bin/bash

# ROS2 通信机制测试脚本
# 用于测试话题、服务、动作的所有示例

echo "=== ROS2 通信机制测试脚本 ==="
echo "确保你已经编译了 my_package"
echo

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查ROS2环境
check_ros2_env() {
    echo -e "${BLUE}检查ROS2环境...${NC}"

    if [ -z "$AMENT_PREFIX_PATH" ]; then
        echo -e "${RED}ROS2环境未设置，正在加载...${NC}"
        source /opt/ros/humble/setup.bash
    fi

    if [ ! -d "/mnt/apfs/workplace/ROS2/install" ]; then
        echo -e "${RED}错误: install目录不存在，请先编译项目${NC}"
        echo "运行: cd /mnt/apfs/workplace/ROS2 && colcon build --packages-select my_package"
        exit 1
    fi

    source /mnt/apfs/workplace/ROS2/install/setup.bash
    echo -e "${GREEN}✓ ROS2环境已准备${NC}"
    echo
}

# 测试话题通信
test_topics() {
    echo -e "${BLUE}=== 测试话题通信 ===${NC}"

    echo "启动发布者节点（后台运行）..."
    timeout 5 ros2 run my_package publisher_node &
    PUB_PID=$!
    sleep 2

    echo "启动订阅者节点（后台运行）..."
    timeout 5 ros2 run my_package subscriber_node &
    SUB_PID=$!
    sleep 3

    # 检查话题
    echo "检查话题状态..."
    ros2 topic list | grep topic && echo -e "${GREEN}✓ 话题创建成功${NC}" || echo -e "${RED}✗ 话题创建失败${NC}"

    # 清理
    kill $PUB_PID $SUB_PID 2>/dev/null
    echo
}

# 测试服务通信
test_services() {
    echo -e "${BLUE}=== 测试服务通信 ===${NC}"

    echo "启动服务端（后台运行）..."
    timeout 8 ros2 run my_package service_server &
    SRV_PID=$!
    sleep 2

    echo "启动客户端（后台运行）..."
    timeout 8 ros2 run my_package service_client &
    CLI_PID=$!
    sleep 6

    # 手动测试服务
    echo "手动测试服务调用..."
    ros2 service call /add_two_ints example_interfaces/srv/AddTwoInts "{a: 42, b: 58}" &
    sleep 2

    echo -e "${GREEN}✓ 服务测试完成${NC}"

    # 清理
    kill $SRV_PID $CLI_PID 2>/dev/null
    echo
}

# 测试综合节点
test_comprehensive() {
    echo -e "${BLUE}=== 测试综合节点 ===${NC}"
    echo "启动综合节点（同时使用话题和服务）..."
    timeout 6 ros2 run my_package comprehensive_node &
    COMP_PID=$!
    sleep 5

    echo -e "${GREEN}✓ 综合节点测试完成${NC}"

    # 清理
    kill $COMP_PID 2>/dev/null
    echo
}

# 显示可用命令
show_commands() {
    echo -e "${YELLOW}=== 有用的ROS2命令 ===${NC}"

    echo -e "${BLUE}话题相关:${NC}"
    echo "  ros2 topic list                    # 列出所有话题"
    echo "  ros2 topic echo <topic_name>        # 监听话题"
    echo "  ros2 topic info <topic_name>       # 查看话题信息"
    echo "  ros2 topic hz <topic_name>         # 查看发布频率"

    echo -e "${BLUE}服务相关:${NC}"
    echo "  ros2 service list                  # 列出所有服务"
    echo "  ros2 service type <service_name>  # 查看服务类型"
    echo "  ros2 service call <name> <type>    # 调用服务"

    echo -e "${BLUE}节点相关:${NC}"
    echo "  ros2 node list                     # 列出所有节点"
    echo "  ros2 node info <node_name>         # 查看节点信息"
    echo
}

# 交互式菜单
show_menu() {
    echo -e "${YELLOW}=== ROS2 通信机制测试菜单 ===${NC}"
    echo "1. 测试话题通信"
    echo "2. 测试服务通信"
    echo "3. 测试综合节点"
    echo "4. 运行所有测试"
    echo "5. 显示有用命令"
    echo "6. 启动话题演示（手动模式）"
    echo "7. 启动服务演示（手动模式）"
    echo "0. 退出"
    echo -n "请选择操作: "
}

# 手动模式 - 话题演示
manual_topic_demo() {
    echo -e "${BLUE}=== 话题演示 - 手动模式 ===${NC}"
    echo "你需要在两个不同的终端中运行以下命令："
    echo -e "${GREEN}终端1 (发布者):${NC}"
    echo "  source /opt/ros/humble/setup.bash"
    echo "  source /mnt/apfs/workplace/ROS2/install/setup.bash"
    echo "  ros2 run my_package publisher_node"
    echo
    echo -e "${GREEN}终端2 (订阅者):${NC}"
    echo "  source /opt/ros/humble/setup.bash"
    echo "  source /mnt/apfs/workplace/ROS2/install/setup.bash"
    echo "  ros2 run my_package subscriber_node"
    echo
    echo -e "${GREEN}终端3 (监控) - 可选:${NC}"
    echo "  ros2 topic echo /topic"
    echo "  ros2 topic hz /topic"
}

# 手动模式 - 服务演示
manual_service_demo() {
    echo -e "${BLUE}=== 服务演示 - 手动模式 ===${NC}"
    echo "你需要在两个不同的终端中运行以下命令："
    echo -e "${GREEN}终端1 (服务端):${NC}"
    echo "  source /opt/ros/humble/setup.bash"
    echo "  source /mnt/apfs/workplace/ROS2/install/setup.bash"
    echo "  ros2 run my_package service_server"
    echo
    echo -e "${GREEN}终端2 (客户端):${NC}"
    echo "  source /opt/ros/humble/setup.bash"
    echo "  source /mnt/apfs/workplace/ROS2/install/setup.bash"
    echo "  ros2 run my_package service_client"
    echo
    echo -e "${GREEN}终端3 (手动调用) - 可选:${NC}"
    echo "  ros2 service call /add_two_ints example_interfaces/srv/AddTwoInts \"{a: 100, b: 200}\""
}

# 主程序
main() {
    check_ros2_env

    if [ "$1" == "--manual" ]; then
        show_menu
        read choice
        case $choice in
            1) test_topics ;;
            2) test_services ;;
            3) test_comprehensive ;;
            4)
                test_topics
                test_services
                test_comprehensive
                ;;
            5) show_commands ;;
            6) manual_topic_demo ;;
            7) manual_service_demo ;;
            0) echo "退出"; exit 0 ;;
            *) echo "无效选择" ;;
        esac
    else
        # 自动运行所有测试
        test_topics
        test_services
        test_comprehensive
        show_commands

        echo -e "${GREEN}=== 所有测试完成！===${NC}"
        echo -e "${YELLOW}要手动运行示例，请执行: $0 --manual${NC}"
    fi
}

# 运行主程序
main "$@"