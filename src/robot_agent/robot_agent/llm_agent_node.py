#!/usr/bin/env python3
"""
Day7 节点1：llm_agent（大脑）
订阅 /voice_text (String) → LLMAgent.chat() → FC 结果填进 RobotCommand.msg → 发布 /robot_command
延迟打点：[延迟] FC=xxx ms 填msg+发布=x.x ms
"""
import json
import os
import time
from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from my_package.msg import RobotCommand

from robot_agent.llm_core import LLMAgent


class LLMAgentNode(Node):
    def __init__(self):
        super().__init__('llm_agent')

        # 大脑核心（Day6 移植），配置从安装目录读（跟包走，不依赖工作目录）
        config_path = os.path.join(
            get_package_share_directory('robot_agent'), 'config', 'llm_config.json')
        self.agent = LLMAgent(config_path=config_path)

        self.sub = self.create_subscription(String, 'voice_text', self.on_voice, 10)
        self.cmd_pub = self.create_publisher(RobotCommand, 'robot_command', 10)
        # Step8 延迟采集：诊断通道（JSON-in-String，dev-only 不建 msg）
        self.diag_pub = self.create_publisher(String, 'latency_diag', 10)

        self.get_logger().info(
            f'llm_agent 就绪（模型 {self.agent.model}），等待 /voice_text ...')

    def on_voice(self, msg: String):
        t0 = time.perf_counter()
        text = msg.data.strip()
        if not text:
            return
        self.get_logger().info(f'收到指令: {text}')

        # 大脑处理（拒绝检查在 core 里、LLM 调用前拦截，零 token 消耗）
        result = self.agent.chat(text)

        if result['status'] != 'success':
            # rejected / no_tool / invalid_param / error：
            # 不发布任何指令 → controller 收不到新命令，零速心跳兜底，车保持静止
            self.get_logger().warn(
                f"不发布指令（{result['status']}）: {result.get('message', '')[:80]}")
            self.publish_diag(text, result, 1000*(time.perf_counter()-t0), 0.0)
            return

        t1 = time.perf_counter()

        # ===== JSON → msg：全链路唯一的转换边界 =====
        cmd = RobotCommand()
        cmd.action = result['action']
        cmd.distance = float(result['parameters'].get('distance', 0.0))
        cmd.angle = float(result['parameters'].get('angle', 0.0))
        cmd.sensor_type = str(result['parameters'].get('type', ''))
        self.cmd_pub.publish(cmd)

        t2 = time.perf_counter()
        self.get_logger().info(
            f'已发布 /robot_command: action={cmd.action} distance={cmd.distance} '
            f'angle={cmd.angle} sensor_type={cmd.sensor_type} | '
            f'[延迟] FC={1000*(t1-t0):.0f}ms 填msg+发布={1000*(t2-t1):.1f}ms')
        self.publish_diag(text, result, 1000*(t1-t0), 1000*(t2-t1))

    def publish_diag(self, text, result, fc_ms, msg_ms):
        """Step8 延迟采集：诊断事件。rejected 在 LLM 调用前拦截，fc_ms≈0 是真实数据"""
        diag = {'stage': 'llm', 'text': text, 'status': result['status'],
                'action': result.get('action', ''), 'fc_ms': round(fc_ms),
                'msg_ms': round(msg_ms, 1), 'done_at': time.time()}
        d = String()
        d.data = json.dumps(diag, ensure_ascii=False)
        self.diag_pub.publish(d)


def main():
    rclpy.init()
    node = LLMAgentNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
