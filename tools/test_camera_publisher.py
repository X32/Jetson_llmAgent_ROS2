#!/usr/bin/env python3
"""
简单的模拟摄像头发布者 - 用于测试Python订阅者节点
"""

import rclpy
from sensor_msgs.msg import Image
import time
import numpy as np

class TestCameraPublisher:
    def __init__(self):
        self.node = rclpy.create_node('test_camera_publisher')
        self.publisher = self.node.create_publisher(Image, '/camera/image_raw', 10)
        self.timer = self.node.create_timer(0.1, self.publish_image)  # 10 Hz
        self.count = 0

        self.node.get_logger().info('测试摄像头发布者已启动')
        self.node.get_logger().info('发布模拟图像数据到: /camera/image_raw')

    def publish_image(self):
        """发布模拟图像数据"""
        msg = Image()
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.header.frame_id = 'camera_frame'
        msg.height = 480
        msg.width = 640
        msg.encoding = 'bgr8'
        msg.step = 640 * 3

        # 创建模拟彩色条纹图像
        img_data = np.zeros((480, 640, 3), dtype=np.uint8)
        for i in range(640):
            color = int((i / 640) * 255)
            img_data[:, i] = [color, 128, 255-color]

        msg.data = img_data.tobytes()
        self.publisher.publish(msg)

        self.count += 1
        if self.count % 10 == 0:
            self.node.get_logger().info(f'已发送 {self.count} 帧模拟图像数据')

def main():
    rclpy.init()
    test_pub = TestCameraPublisher()

    print("模拟摄像头发布者正在运行...")
    print("Python订阅者节点应该能接收并显示彩色条纹图像")
    print("按 Ctrl+C 停止")

    try:
        rclpy.spin(test_pub.node)
    except KeyboardInterrupt:
        print("\n模拟发布者已停止")
    finally:
        test_pub.node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()