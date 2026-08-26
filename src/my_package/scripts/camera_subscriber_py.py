#!/usr/bin/env python3
"""
ROS2 Python摄像头订阅者节点
接收 /camera/image_raw 话题并显示图像
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import time

class CameraSubscriberPy(Node):
    def __init__(self):
        super().__init__('camera_subscriber_py')

        # 创建CV Bridge对象，用于ROS图像和OpenCV图像之间的转换
        self.bridge = CvBridge()

        # 统计信息
        self.frame_count = 0
        self.start_time = time.time()
        self.last_fps = 0.0
        self.last_print_time = time.time()

        # 创建图像订阅者
        self.subscription = self.create_subscription(
            Image,
            '/camera/image_raw',
            self.image_callback,
            10  # QoS profile depth
        )

        self.get_logger().info('Python摄像头订阅者节点已启动')
        self.get_logger().info('订阅话题: /camera/image_raw')

        # 创建定时器用于统计信息
        self.timer = self.create_timer(5.0, self.print_stats)

    def image_callback(self, msg):
        """接收到图像消息时的回调函数"""
        try:
            # 将ROS图像消息转换为OpenCV格式
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            # 处理图像（添加FPS信息）
            self.process_image(cv_image)

            # 显示图像
            cv2.imshow('ROS2 Python Camera Subscriber', cv_image)
            cv2.waitKey(1)  # 必须调用waitKey来更新窗口

            # 更新统计信息
            self.frame_count += 1
            current_time = time.time()

            # 每30帧更新一次FPS
            if self.frame_count % 30 == 0:
                elapsed = current_time - self.last_print_time
                if elapsed > 0:
                    self.last_fps = 30 / elapsed
                self.last_print_time = current_time
                self.get_logger().info(f'接收帧 #{self.frame_count} (FPS: {self.last_fps:.1f})')

        except Exception as e:
            self.get_logger().error(f'处理图像时出错: {str(e)}')

    def process_image(self, image):
        """处理图像，添加FPS信息等"""
        # 计算当前FPS
        if self.frame_count > 0:
            elapsed = time.time() - self.start_time
            current_fps = self.frame_count / elapsed if elapsed > 0 else 0
        else:
            current_fps = self.last_fps

        # 添加FPS信息到图像上
        fps_text = f'FPS: {int(current_fps)}'
        frame_text = f'Frame: {self.frame_count}'

        # 在图像上绘制文本
        cv2.putText(image, fps_text, (15, 35),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(image, frame_text, (15, image.shape[0] - 15),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        # 添加"Python"标识
        cv2.putText(image, 'Python ROS2', (15, 70),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    def print_stats(self):
        """打印统计信息"""
        elapsed = time.time() - self.start_time
        avg_fps = self.frame_count / elapsed if elapsed > 0 else 0

        self.get_logger().info(f'=== 统计信息 ===')
        self.get_logger().info(f'总帧数: {self.frame_count}')
        self.get_logger().info(f'当前FPS: {self.last_fps:.1f}')
        self.get_logger().info(f'平均FPS: {avg_fps:.1f}')
        self.get_logger().info(f'运行时间: {elapsed:.1f}秒')

        # 检查发布者状态（Python版本的替代方法）
        if self.frame_count > 0 and self.last_fps > 0:
            self.get_logger().info('发布者状态: 活跃')
        else:
            self.get_logger().warn('发布者状态: 可能在等待数据')

    def __del__(self):
        """析构函数，清理资源"""
        cv2.destroyAllWindows()

def main(args=None):
    rclpy.init(args=args)

    node = CameraSubscriberPy()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('收到中断信号，正在关闭节点...')
    finally:
        node.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()