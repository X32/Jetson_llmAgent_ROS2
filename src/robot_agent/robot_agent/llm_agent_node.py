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
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from my_package.msg import RobotCommand
from my_package.srv import QuerySensor

# 支持切换到 llama.cpp 版本（通过环境变量 LLAMACPP=1 启用）
# 在导入时就决定使用哪个核心，避免加载不需要的模块
if os.environ.get('LLAMACPP') == '1':
    from robot_agent.llm_core_llamacpp import LLMAgent
    backend = "llama.cpp"
else:
    from robot_agent.llm_core import LLMAgent
    backend = "Ollama"


class LLMAgentNode(Node):
    def __init__(self):
        super().__init__('llm_agent')

        # 大脑核心，配置从安装目录读（跟包走，不依赖工作目录）
        # 根据 LLAMACPP 环境变量选择配置文件
        if os.environ.get('LLAMACPP') == '1':
            config_file = 'llm_config_llamacpp.json'
            backend = "llama.cpp"
        else:
            config_file = 'llm_config.json'
            backend = "Ollama"

        config_path = os.path.join(
            get_package_share_directory('robot_agent'), 'config', config_file)
        self.agent = LLMAgent(config_path=config_path)
          # Day9 死锁预防：订阅回调与服务客户端放同一个可重入回调组，
        # 配合 MultiThreadedExecutor，on_voice 里才能同步等服务结果（见 2.4 节）
        self.cb_group = ReentrantCallbackGroup()

        self.sub = self.create_subscription(String, 'voice_text', self.on_voice, 10, callback_group=self.cb_group)
        self.cmd_pub = self.create_publisher(RobotCommand, 'robot_command', 10)
        self.answer_pub = self.create_publisher(String, 'agent_answer', 10)   # Day9 新增
        # Step8 延迟采集：诊断通道（JSON-in-String，dev-only 不建 msg）
        self.diag_pub = self.create_publisher(String, 'latency_diag', 10, callback_group=self.cb_group)
        self.query_client = self.create_client(QuerySensor, 'query_sensor', callback_group=self.cb_group)        # Day9 新增

        self.get_logger().info(
            f'llm_agent 就绪（后端={backend}，模型={self.agent.model}），等待 /voice_text ...')
        
    def handle_query(self, result, t0):
        """Day9 工具执行体：调 /query_sensor 服务 → 结果回填 → 二次推理 → 发布回答"""
        sensor_type = result['parameters'].get('type', 'all')

        # 服务调用（~ms 级；2 秒超时兜底）
        t_s0 = time.perf_counter()
        summary = '传感器服务无响应'
        if self.query_client.wait_for_service(timeout_sec=1.0):
            req = QuerySensor.Request()
            req.type = sensor_type
            future = self.query_client.call_async(req)
            t_deadline = time.time() + 2.0
            while not future.done() and time.time() < t_deadline:
                time.sleep(0.02)
            if future.done() and future.result() is not None:
                summary = future.result().summary
        t_s1 = time.perf_counter()

        # 真实结果回填 → 二次推理 → 自然语言回答
        answer = self.agent.followup_tool_result('query_sensor', summary)
        t2 = time.perf_counter()

        self.get_logger().info(
            f'[问答] 传感器数据: {summary}')
        self.get_logger().info(
            f'[问答] 回答: {answer} | '
            f'[延迟] FC1={1000*(t_s0-t0):.0f}ms 服务={1000*(t_s1-t_s0):.0f}ms '
            f'FC2={1000*(t2-t_s1):.0f}ms')

        msg = String()
        msg.data = answer
        self.answer_pub.publish(msg)

        # 延迟采集：问答行 fc_ms = 两次推理总和（无车动，recorder 端到端列会超时留空，正常）
        diag = {'stage': 'llm', 'text': result['user_input'], 'status': 'success',
                'action': 'query_sensor', 'fc_ms': round(1000*(t2-t0)),
                'msg_ms': 0.0, 'done_at': time.time()}
        d = String()
        d.data = json.dumps(diag, ensure_ascii=False)
        self.diag_pub.publish(d)

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
            # 调试：no_tool 时打印模型原始输出，便于定位（正式版可关闭）
            if result.get('llm_response'):
                self.get_logger().warn(
                    f"[调试] 模型原始输出: {result['llm_response'][:200]}")
            self.publish_diag(text, result, 1000*(time.perf_counter()-t0), 0.0)
            return

        t1 = time.perf_counter()
         # ===== Day9 分流：查询类走工具执行体，不发 /robot_command =====
        if result['action'] == 'query_sensor':
            self.handle_query(result, t0)
            return

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
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
