#!/bin/bash

# 🚀 ROS2摄像头AI识别系统 - 一键启动脚本

echo "=== 🤖🔍 ROS2摄像头AI识别系统 - 快速启动 ==="
echo

cd /mnt/apfs/workplace/ROS2

# 加载ROS2环境
source /opt/ros/humble/setup.bash
source install/setup.bash

echo "🔧 检查依赖..."
python3 -c "import cv2, numpy, rclpy, onnxruntime, torch, pandas, PIL" 2>/dev/null || {
    echo "❌ 依赖缺失，正在安装..."
    pip3 install "pandas<2.0,>=1.3.0" "opencv-python-headless==4.7.0.68" --user
}

echo "✅ 依赖检查完成"
echo

echo "📋 选择启动模式："
echo "1) 完整系统 (摄像头 + AI识别)"
echo "2) 仅摄像头发布者"
echo "3) 仅AI识别节点"
echo

read -p "请选择 (1-3): " choice

case $choice in
    1)
        echo "🚀 启动完整系统..."
        echo "📷 终端1 - 摄像头发布者:"
        echo "  ros2 run my_package camera_publisher"
        echo
        echo "🤖 终端2 - AI识别节点:"
        echo "  ros2 run my_package camera_recognition_subscriber.py"
        echo
        echo "💡 建议: 开启两个终端分别运行上述命令"
        ;;

    2)
        echo "📷 启动摄像头发布者..."
        ros2 run my_package camera_publisher --ros-args -p image_width:=640 -p image_height:=480
        ;;

    3)
        echo "🤖 启动AI识别节点..."
        ros2 run my_package camera_recognition_subscriber.py
        ;;

    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac