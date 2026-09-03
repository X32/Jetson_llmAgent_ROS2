#!/usr/bin/env python3
"""
单独测试 llm_agent_node.py 的脚本
测试 LLM Agent 节点的输入输出
"""
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from my_package.msg import RobotCommand
import json
import time

class LLMAgentTester(Node):
    def __init__(self):
        super().__init__('llm_agent_tester')

        # 订阅 /robot_command 来监听输出
        self.cmd_sub = self.create_subscription(
            RobotCommand,
            'robot_command',
            self.on_robot_command,
            10
        )

        # 订阅 /agent_answer 来监听传感器查询答案
        self.answer_sub = self.create_subscription(
            String,
            'agent_answer',
            self.on_agent_answer,
            10
        )

        # 发布测试指令
        self.voice_pub = self.create_publisher(
            String,
            'voice_text',
            10
        )

        self.test_count = 0
        self.received_count = 0
        self.get_logger().info('LLM Agent 测试节点启动')

    def on_robot_command(self, msg):
        """接收到机器人指令"""
        self.received_count += 1
        self.get_logger().info(
            f'✅ 收到机器人指令 #{self.received_count}: '
            f'action={msg.action} distance={msg.distance} angle={msg.angle}'
        )

    def on_agent_answer(self, msg):
        """接收到传感器查询答案"""
        self.get_logger().info(f'✅ 收到查询答案: {msg.data}')

    def send_test_command(self, text):
        """发送测试指令"""
        self.test_count += 1
        self.get_logger().info(f'📤 发送测试指令 #{self.test_count}: {text}')

        msg = String()
        msg.data = text
        self.voice_pub.publish(msg)

def main():
    rclpy.init()
    tester = LLMAgentTester()

    # 测试指令列表
    test_commands = [
        "向前走半米",
        "左转九十度",
        "停止",
        "前方有障碍物吗",  # 需要运行 state_query_node
        "走了多远",        # 需要运行 state_query_node
    ]

    print("=== LLM Agent 节点测试 ===")
    print("请确保:")
    print("1. llama.cpp 服务器正在运行 (http://localhost:8000)")
    print("2. 如需测试传感器查询，请先运行: ros2 run state_query state_query_node")
    print("")

    try:
        # 发送测试指令
        for i, command in enumerate(test_commands, 1):
            print(f"\n--- 测试 {i}/{len(test_commands)}: {command} ---")
            tester.send_test_command(command)

            # 等待响应
            rclpy.spin_once(tester, timeout_sec=3.0)
            time.sleep(0.5)

        print(f"\n=== 测试完成 ===")
        print(f"发送: {tester.test_count} 条指令")
        print(f"接收: {tester.received_count} 条机器人指令")

    except KeyboardInterrupt:
        print("\n测试被中断")

    finally:
        tester.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
