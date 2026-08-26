#!/bin/bash

# ROS2 摄像头节点测试脚本

echo "=== ROS2 摄像头传感器节点测试 ==="
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
        echo -e "${YELLOW}ROS2环境未设置，正在加载...${NC}"
        source /opt/ros/humble/setup.bash
    fi

    if [ -d "/mnt/apfs/workplace/ROS2/install" ]; then
        source /mnt/apfs/workplace/ROS2/install/setup.bash
        echo -e "${GREEN}✓ ROS2环境已准备${NC}"
    else
        echo -e "${RED}✗ install目录不存在，请先编译项目${NC}"
        return 1
    fi

    echo
    return 0
}

# 检查摄像头设备
check_camera() {
    echo -e "${BLUE}检查摄像头设备...${NC}"

    if [ -e "/dev/video0" ]; then
        echo -e "${GREEN}✓ 找到摄像头设备 /dev/video0${NC}"
        ls -la /dev/video* | head -5
    else
        echo -e "${RED}✗ 未找到摄像头设备${NC}"
        echo "请检查摄像头连接和权限"
        return 1
    fi

    echo
    return 0
}

# 检查编译状态
check_build() {
    echo -e "${BLUE}检查编译状态...${NC}"

    if [ -f "/mnt/apfs/workplace/ROS2/install/my_package/lib/my_package/camera_publisher" ]; then
        echo -e "${GREEN}✓ 摄像头节点已编译${NC}"
    else
        echo -e "${RED}✗ 摄像头节点未编译${NC}"
        echo "请运行: cd /mnt/apfs/workplace/ROS2 && colcon build --packages-select my_package"
        return 1
    fi

    echo
    return 0
}

# 测试基本功能
test_basic() {
    echo -e "${BLUE}=== 测试基本摄像头功能 ===${NC}"

    echo "启动摄像头发布者（10秒测试）..."
    timeout 10 ros2 run my_package camera_publisher &
    PUB_PID=$!
    sleep 3

    echo "检查话题..."
    if ros2 topic list | grep -q "camera/image_raw"; then
        echo -e "${GREEN}✓ 摄像头话题已创建${NC}"

        echo "获取话题信息..."
        ros2 topic info /camera/image_raw

        echo "测试话题频率（3秒）..."
        timeout 3 ros2 topic hz /camera/image_raw || true
    else
        echo -e "${RED}✗ 摄像头话题未创建${NC}"
    fi

    # 清理
    kill $PUB_PID 2>/dev/null
    echo
}

# 快速演示（后台运行）
quick_demo() {
    echo -e "${BLUE}=== 快速摄像头演示 ===${NC}"
    echo "启动摄像头发布者和订阅者..."

    # 启动发布者
    ros2 run my_package camera_publisher &
    PUB_PID=$!
    echo -e "${GREEN}✓ 摄像头发布者已启动 (PID: $PUB_PID)${NC}"

    sleep 2

    # 启动订阅者
    ros2 run my_package camera_subscriber &
    SUB_PID=$!
    echo -e "${GREEN}✓ 摄像头订阅者已启动 (PID: $SUB_PID)${NC}"

    echo
    echo -e "${YELLOW}摄像头节点正在运行中...${NC}"
    echo -e "${YELLOW}按 Ctrl+C 停止${NC}"
    echo

    # 等待用户中断
    wait
}

# 监控模式
monitor_mode() {
    echo -e "${BLUE}=== 摄像头监控模式 ===${NC}"

    # 启动发布者
    echo "启动摄像头发布者..."
    ros2 run my_package camera_publisher &
    PUB_PID=$!
    sleep 2

    echo -e "${GREEN}摄像头已启动，正在监控...${NC}"
    echo -e "${YELLOW}监控命令 (在新终端中运行):${NC}"
    echo "  ros2 topic hz /camera/image_raw     # 查看帧率"
    echo "  ros2 topic echo /camera/image_raw   # 查看消息"
    echo "  ros2 node info /camera_publisher   # 节点信息"
    echo
    echo "按 Ctrl+C 停止监控"

    wait
}

# 性能测试
performance_test() {
    echo -e "${BLUE}=== 摄像头性能测试 ===${NC}"

    echo "测试不同分辨率和帧率..."

    # 测试默认配置
    echo "1. 默认配置 (640x480 @ 30Hz)"
    timeout 8 ros2 run my_package camera_publisher &
    PUB_PID=$!
    sleep 3
    timeout 5 ros2 topic hz /camera/image_raw || true
    kill $PUB_PID 2>/dev/null
    sleep 2

    # 测试低分辨率
    echo "2. 低分辨率 (320x240 @ 30Hz)"
    timeout 8 ros2 run my_package camera_publisher --ros-args -p image_width:=320 -p image_height:=240 &
    PUB_PID=$!
    sleep 3
    timeout 5 ros2 topic hz /camera/image_raw || true
    kill $PUB_PID 2>/dev/null
    sleep 2

    # 测试低帧率
    echo "3. 低帧率 (640x480 @ 15Hz)"
    timeout 8 ros2 run my_package camera_publisher --ros-args -p publish_frequency:=15.0 &
    PUB_PID=$!
    sleep 3
    timeout 5 ros2 topic hz /camera/image_raw || true
    kill $PUB_PID 2>/dev/null

    echo
}

# 交互式菜单
show_menu() {
    echo -e "${YELLOW}=== ROS2 摄像头节点测试菜单 ===${NC}"
    echo "1. 检查系统状态"
    echo "2. 测试基本功能"
    echo "3. 快速演示（后台运行）"
    echo "4. 监控模式"
    echo "5. 性能测试"
    echo "6. 显示有用命令"
    echo "7. 停止所有摄像头节点"
    echo "8. 手动运行指南"
    echo "0. 退出"
    echo -n "请选择操作: "
}

# 停止所有摄像头节点
stop_all() {
    echo -e "${BLUE}停止所有摄像头节点...${NC}"
    killall -9 camera_publisher 2>/dev/null && echo -e "${GREEN}✓ 停止发布者${NC}"
    killall -9 camera_subscriber 2>/dev/null && echo -e "${GREEN}✓ 停止订阅者${NC}"
    echo
}

# 显示有用命令
show_commands() {
    echo -e "${BLUE}=== 有用的ROS2摄像头命令 ===${NC}"

    echo -e "${YELLOW}话题相关:${NC}"
    echo "  ros2 topic list                          # 列出所有话题"
    echo "  ros2 topic info /camera/image_raw        # 查看摄像头话题详情"
    echo "  ros2 topic hz /camera/image_raw          # 查看发布频率"
    echo "  ros2 topic bw /camera/image_raw          # 查看带宽使用"
    echo "  ros2 topic echo /camera/image_raw        # 监听图像消息"

    echo -e "${YELLOW}图像显示:${NC}"
    echo "  ros2 run rqt_image_view rqt_image_view   # 使用GUI查看图像"
    echo "  ros2 run image_view image_view --ros-args -r image:=/camera/image_raw"

    echo -e "${YELLOW}数据录制:${NC}"
    echo "  ros2 bag record /camera/image_raw        # 录制摄像头数据"
    echo "  ros2 bag play <bag_file>                 # 回放录制的数据"

    echo -e "${YELLOW}节点调试:${NC}"
    echo "  ros2 node list                           # 列出所有节点"
    echo "  ros2 node info /camera_publisher         # 查看发布者节点信息"

    echo -e "${YELLOW}参数配置:${NC}"
    echo "  ros2 param list                          # 列出所有参数"
    echo "  ros2 param get /camera_publisher camera_device  # 获取特定参数"
    echo
}

# 手动运行指南
manual_guide() {
    echo -e "${BLUE}=== 手动运行指南 ===${NC}"
    echo -e "${GREEN}终端1 - 摄像头发布者:${NC}"
    echo "  source /opt/ros/humble/setup.bash"
    echo "  source /mnt/apfs/workplace/ROS2/install/setup.bash"
    echo "  ros2 run my_package camera_publisher"
    echo
    echo -e "${GREEN}终端2 - 摄像头订阅者:${NC}"
    echo "  source /opt/ros/humble/setup.bash"
    echo "  source /mnt/apfs/workplace/ROS2/install/setup.bash"
    echo "  ros2 run my_package camera_subscriber"
    echo
    echo -e "${GREEN}终端3 - 监控工具（可选）:${NC}"
    echo "  # 查看帧率"
    echo "  ros2 topic hz /camera/image_raw"
    echo "  # 显示图像"
    echo "  ros2 run rqt_image_view rqt_image_view"
    echo
}

# 系统状态检查
system_check() {
    echo -e "${BLUE}=== 系统状态检查 ===${NC}"

    check_ros2_env || return 1
    check_build || return 1
    check_camera || return 1

    echo -e "${GREEN}✓ 所有检查通过${NC}"
    echo
}

# 主程序
main() {
    if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
        echo "用法: $0 [选项]"
        echo "选项:"
        echo "  --check     检查系统状态"
        echo "  --test      运行基本测试"
        echo "  --demo      快速演示"
        echo "  --monitor   监控模式"
        echo "  --perf      性能测试"
        echo "  --stop      停止所有节点"
        echo "  --manual    显示手动运行指南"
        echo "  无参数      交互式菜单"
        exit 0
    fi

    case "$1" in
        --check)
            system_check
            ;;
        --test)
            check_ros2_env && check_build && test_basic
            ;;
        --demo)
            check_ros2_env && check_build && quick_demo
            ;;
        --monitor)
            check_ros2_env && check_build && monitor_mode
            ;;
        --perf)
            check_ros2_env && check_build && performance_test
            ;;
        --stop)
            stop_all
            ;;
        --manual)
            manual_guide
            ;;
        "")
            # 交互式菜单
            while true; do
                show_menu
                read choice
                case $choice in
                    1) system_check ;;
                    2) check_ros2_env && check_build && test_basic ;;
                    3) check_ros2_env && check_build && quick_demo ;;
                    4) check_ros2_env && check_build && monitor_mode ;;
                    5) check_ros2_env && check_build && performance_test ;;
                    6) show_commands ;;
                    7) stop_all ;;
                    8) manual_guide ;;
                    0) echo "退出"; exit 0 ;;
                    *) echo "无效选择" ;;
                esac
            done
            ;;
        *)
            echo "未知选项: $1"
            echo "运行 $0 --help 查看帮助"
            exit 1
            ;;
    esac
}

# 运行主程序
main "$@"