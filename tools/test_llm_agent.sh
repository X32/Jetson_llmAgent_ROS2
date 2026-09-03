#!/bin/bash
# 完整的 llm_agent_node 测试脚本

echo "=== LLM Agent 节点测试套件 ==="

# 激活环境
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
source install/setup.bash

echo ""
echo "请选择测试模式:"
echo "1) 基础功能测试（不需要其他节点）"
echo "2) 完整功能测试（需要 state_query_node）"
echo "3) 性能压力测试"
echo "4) 交互式测试"
echo ""
read -p "选择 (1-4): " choice

case $choice in
    1)
        echo "=== 基础功能测试 ==="
        echo "测试移动指令..."
        ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"
        sleep 2

        echo "测试旋转指令..."
        ros2 topic pub --once /voice_text std_msgs/msg/String "data: '左转九十度'"
        sleep 2

        echo "测试停止指令..."
        ros2 topic pub --once /voice_text std_msgs/msg/String "data: '停止'"
        ;;

    2)
        echo "=== 完整功能测试 ==="
        echo "请确保 state_query_node 正在运行！"

        echo "测试传感器查询..."
        ros2 topic pub --once /voice_text std_msgs/msg/String "data: '前方有障碍物吗'"
        sleep 2

        echo "测试里程查询..."
        ros2 topic pub --once /voice_text std_msgs/msg/String "data: '走了多远'"
        ;;

    3)
        echo "=== 性能压力测试 ==="
        echo "发送10个连续指令..."

        for i in {1..10}; do
            echo "发送指令 $i/10"
            ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走0.5米'"
            sleep 0.5
        done
        ;;

    4)
        echo "=== 交互式测试 ==="
        echo "输入指令 (按 Ctrl+C 退出):"

        while true; do
            read -p "指令: " cmd
            if [ -n "$cmd" ]; then
                ros2 topic pub --once /voice_text std_msgs/msg/String "data: '$cmd'"
            fi
        done
        ;;

    *)
        echo "无效选择"
        exit 1
        ;;
esac

echo ""
echo "=== 测试完成 ==="
echo "监听 /robot_command 查看结果:"
echo "ros2 topic echo /robot_command"
