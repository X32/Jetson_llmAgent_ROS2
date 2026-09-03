#!/bin/bash
# ROS2 环境诊断和修复脚本

echo "=== ROS2 环境诊断 ==="
echo ""

# 1. 检查 ROS2 安装
echo "1. 检查 ROS2 安装..."
if [ -f "/opt/ros/humble/setup.bash" ]; then
    echo "   ✅ ROS2 Humble 已安装"
else
    echo "   ❌ ROS2 Humble 未安装"
    exit 1
fi

# 2. 检查 RMW 实现
echo ""
echo "2. 检查已安装的 RMW 实现..."
rmw_count=0

if [ -f "/opt/ros/humble/lib/librmw_cyclonedds_cpp.so" ]; then
    echo "   ✅ CycloneDDS (rmw_cyclonedds_cpp)"
    rmw_count=$((rmw_count + 1))
else
    echo "   ⚠️  CycloneDDS 未安装"
fi

if [ -f "/opt/ros/humble/lib/librmw_fastrtps_cpp.so" ]; then
    echo "   ✅ Fast-RTPS (rmw_fastrtps_cpp)"
    rmw_count=$((rmw_count + 1))
else
    echo "   ❌ Fast-RTPS 未安装"
fi

echo "   已安装 RMW 实现数量: $rmw_count"

# 3. 检查当前 RMW 设置
echo ""
echo "3. 当前 RMW 配置..."
if [ -n "$RMW_IMPLEMENTATION" ]; then
    echo "   RMW_IMPLEMENTATION: $RMW_IMPLEMENTATION"

    if [ "$RMW_IMPLEMENTATION" = "rmw_cyclonedds_cpp" ] && [ ! -f "/opt/ros/humble/lib/librmw_cyclonedds_cpp.so" ]; then
        echo "   ❌ 配置要求 CycloneDDS 但未安装！"
        fix_needed=true
    elif [ "$RMW_IMPLEMENTATION" = "rmw_fastrtps_cpp" ] && [ ! -f "/opt/ros/humble/lib/librmw_fastrtps_cpp.so" ]; then
        echo "   ❌ 配置要求 Fast-RTPS 但未安装！"
        fix_needed=true
    else
        echo "   ✅ RMW 配置有效"
    fi
else
    echo "   ⚠️  RMW_IMPLEMENTATION 未设置（将使用默认）"
fi

# 4. 修复建议
echo ""
echo "=== 修复建议 ==="

if [ "$rmw_count" -eq 0 ]; then
    echo "❌ 没有找到任何 RMW 实现！"
    echo ""
    echo "修复步骤:"
    echo "  sudo apt update"
    echo "  sudo apt install -y ros-humble-rmw-fastrtps-cpp"
    echo ""
    echo "或安装 CycloneDDS（推荐）:"
    echo "  sudo apt install -y ros-humble-rmw-cyclonedds-cpp"
elif [ ! -f "/opt/ros/humble/lib/librmw_cyclonedds_cpp.so" ]; then
    echo "⚠️  CycloneDDS 未安装（性能更好，推荐安装）"
    echo ""
    echo "安装命令:"
    echo "  sudo apt update"
    echo "  sudo apt install -y ros-humble-rmw-cyclonedds-cpp"
    echo ""
    echo "或使用 Fast-RTPS（已安装）:"
    echo "  export RMW_IMPLEMENTATION=rmw_fastrtps_cpp"
else
    echo "✅ RMW 环境完整"
fi

# 5. 测试
echo ""
echo "=== 测试 ROS2 ==="
source /opt/ros/humble/setup.bash 2>/dev/null

if ros2 node list 2>/dev/null; then
    echo "✅ ROS2 节点列表正常"
else
    echo "❌ ROS2 节点列表失败"
    echo "请检查是否有运行的节点，或启动测试节点:"
    echo "  ros2 run demo_nodes_cpp talker"
fi

echo ""
echo "=== 诊断完成 ==="
