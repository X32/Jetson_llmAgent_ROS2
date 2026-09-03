#!/bin/bash
# ROS2 网络诊断脚本

echo "=== ROS2 网络诊断 ==="
echo ""

echo "1. 检查 ROS_DOMAIN_ID:"
echo "   当前 ROS_DOMAIN_ID: $ROS_DOMAIN_ID"
echo "   建议设置为: export ROS_DOMAIN_ID=0"
echo ""

echo "2. 检查网络接口:"
ip addr show | grep -E "inet [0-9]" | grep -v 127.0.0.1
echo ""

echo "3. 检查 ROS2 节点:"
ros2 node list
echo ""

echo "4. 检查 ROS2 话题:"
ros2 topic list
echo ""

echo "5. 检查防火墙状态:"
sudo ufw status || echo "防火墙状态检查失败"
echo ""

echo "6. 测试多播通信:"
ping -c 2 224.0.0.1 || echo "多播测试失败"
echo ""

echo "=== 诊断完成 ==="
echo ""
echo "建议解决方案:"
echo "1. 确保 PC 和 Jetson 使用相同的 ROS_DOMAIN_ID"
echo "2. 检查网络连接: ping <jetson_ip>"
echo "3. 临时关闭防火墙: sudo ufw disable"
echo "4. 设置环境变量:"
echo "   export ROS_DOMAIN_ID=0"
echo "   export ROS_LOCALHOST_ONLY=0"
