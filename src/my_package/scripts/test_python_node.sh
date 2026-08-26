#!/bin/bash

# 测试Python摄像头节点（使用模拟数据）

echo "=== Python摄像头节点测试 ==="
echo

# 加载ROS2环境
source /opt/ros/humble/setup.bash
cd /mnt/apfs/workplace/ROS2
source install/setup.bash

echo "使用模拟图像数据测试Python节点..."

# 创建一个简单的测试发布者，发布模拟图像数据
cat > /tmp/test_publisher.py << 'EOF'
#!/usr/bin/env python3
import rclpy
from sensor_msgs.msg import Image
import time
import numpy as np

class TestPublisher:
    def __init__(self):
        self.node = rclpy.create_node('test_camera_publisher')
        self.publisher = self.node.create_publisher(Image, '/camera/image_raw', 10)
        self.timer = self.node.create_timer(0.1, self.publish_image)
        self.count = 0

    def publish_image(self):
        msg = Image()
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_frame'
        msg.height = 480
        msg.width = 640
        msg.encoding = 'bgr8'
        msg.step = 640 * 3

        # 创建模拟图像数据（彩色条纹）
        img_data = np.zeros((480, 640, 3), dtype=np.uint8)
        for i in range(640):
            color = int((i / 640) * 255)
            img_data[:, i] = [color, 128, 255-color]

        msg.data = img_data.tobytes()
        self.publisher.publish(msg)

        self.count += 1
        if self.count % 10 == 0:
            print(f"已发送 {self.count} 帧模拟图像数据")

def main():
    rclpy.init()
    test_pub = TestPublisher()

    print("测试发布者已启动，发送模拟图像数据...")
    print("Python节点应该能接收并显示这些数据")

    try:
        rclpy.spin(test_pub.node)
    except KeyboardInterrupt:
        print("\n测试发布者已停止")
    finally:
        test_pub.node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
EOF

chmod +x /tmp/test_publisher.py

# 启动测试发布者
python3 /tmp/test_publisher.py &
TEST_PID=$!

sleep 2

# 测试Python订阅者
echo "启动Python订阅者（5秒测试）..."
timeout 5 ros2 run my_package camera_subscriber_py.py

# 清理
kill $TEST_PID 2>/dev/null
rm /tmp/test_publisher.py

echo
echo "Python节点测试完成"
echo "如果看到图像窗口显示彩色条纹，说明Python节点工作正常！"