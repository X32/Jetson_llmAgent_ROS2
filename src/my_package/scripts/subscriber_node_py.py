#!/usr/bin/env python3
"""
ROS2 Python订阅者节点
订阅 publisher_node 发布的 "topic" 话题（std_msgs/String）并打印消息内容
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class MinimalSubscriber(Node):
    def __init__(self):
        super().__init__('minimal_subscriber_py')

        # 创建订阅者，话题名"topic"，消息类型String，队列长度10
        self.subscription = self.create_subscription(
            String,
            'topic',
            self.topic_callback,
            10
        )

        self.get_logger().info('Python订阅者节点已启动，等待消息...')

    def topic_callback(self, msg):
        """接收到消息时的回调函数，打印消息内容"""
        self.get_logger().info(f'收到消息: "{msg.data}"')


def main(args=None):
    rclpy.init(args=args)

    node = MinimalSubscriber()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('收到中断信号，正在关闭节点...')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
