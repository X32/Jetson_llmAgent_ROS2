#!/bin/bash
# 快速测试 llm_agent 节点

echo "=== LLM Agent 快速测试 ==="

# 激活环境
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
source install/setup.bash

# 检查节点状态
echo "1. 检查节点状态:"
NODES=$(ros2 node list)
if echo "$NODES" | grep -q "llm_agent"; then
    echo "   ✅ llm_agent 节点正在运行"
else
    echo "   ❌ llm_agent 节点未运行"
    echo ""
    echo "   请先启动节点:"
    echo "   LLAMACPP=1 ros2 run robot_agent llm_agent"
    exit 1
fi

# 检查话题订阅
echo ""
echo "2. 检查 /voice_text 话题:"
SUB_INFO=$(ros2 topic info /voice_text 2>/dev/null)
if echo "$SUB_INFO" | grep -q "Subscription count:"; then
    echo "   ✅ /voice_text 话题存在"
else
    echo "   ❌ /voice_text 话题不存在"
    exit 1
fi

# 发送测试消息
echo ""
echo "3. 发送测试消息:"
echo "   消息: '向前走半米'"

ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"

echo ""
echo "=== 测试完成 ==="
