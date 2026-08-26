#!/usr/bin/env python3
"""
Day7 节点2：robot_controller（肌肉）
订阅 /robot_command → 换算成 /cmd_vel → 20Hz 持续发布（动作期发指令、静止期发零速心跳）
安全兜底三条：① 动作完成发零速 ② 静止期持续零速（看门狗）③ stop 最高优先级
"""
import math
import signal
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from my_package.msg import RobotCommand


class RobotController(Node):
    def __init__(self):
        super().__init__('robot_controller')

        # 参数化（可用 --ros-args -p linear_speed:=0.3 覆盖）
        self.declare_parameter('linear_speed', 0.2)    # m/s
        self.declare_parameter('angular_speed', 0.5)   # rad/s
        self.declare_parameter('publish_rate', 20.0)   # Hz
        self.linear_speed = self.get_parameter('linear_speed').value
        self.angular_speed = self.get_parameter('angular_speed').value
        rate = self.get_parameter('publish_rate').value

        self.sub = self.create_subscription(RobotCommand, 'robot_command', self.on_cmd, 10)
        self.cmd_pub = self.create_publisher(Twist, 'cmd_vel', 10)

        # 执行状态：当前速度 + 动作截止时刻（ROS 时钟，纳秒）
        self.twist = Twist()      # 当前目标速度（静止=全零）
        self.active = False       # 是否有动作在执行
        self.end_time_ns = 0      # 动作截止时刻（纳秒）

        # 安全兜底②：20Hz 心跳——节点活着，就永远有 /cmd_vel 输出
        self.timer = self.create_timer(1.0 / rate, self.loop)
        self.get_logger().info(
            f'robot_controller 就绪（v={self.linear_speed}m/s w={self.angular_speed}rad/s '
            f'{rate:.0f}Hz），等待 /robot_command ...')

    # ================= 指令处理 =================
    def on_cmd(self, msg: RobotCommand):
        action = msg.action

        # 安全③：stop 最高优先级，立即清空当前动作
        if action == 'stop':
            self.twist = Twist()
            self.active = False
            self.cmd_pub.publish(self.twist)   # 立即发零速，不等下一个心跳
            self.get_logger().warn('收到 stop，立即停车')
            return

        # Day9 才实装，今天只记录
        if action == 'query_sensor':
            self.get_logger().info(
                f'query_sensor({msg.sensor_type}) 将在 Day9 由 state_query 实装，当前忽略')
            return

        twist = Twist()
        if action == 'move_forward':
            if msg.distance <= 0:
                self.get_logger().warn(f'distance 非法: {msg.distance}，忽略')
                return
            twist.linear.x = self.linear_speed
            duration = msg.distance / self.linear_speed
        elif action == 'turn_left':
            if msg.angle <= 0:
                self.get_logger().warn(f'angle 非法: {msg.angle}，忽略')
                return
            twist.angular.z = self.angular_speed            # 左转 = +（右手系，z 朝上）
            duration = math.radians(msg.angle) / self.angular_speed
        elif action == 'turn_right':
            if msg.angle <= 0:
                self.get_logger().warn(f'angle 非法: {msg.angle}，忽略')
                return
            twist.angular.z = -self.angular_speed           # 右转 = -
            duration = math.radians(msg.angle) / self.angular_speed
        else:
            self.get_logger().warn(f'未知动作: {action}，忽略')
            return

        # 新动作直接取代当前动作（后到的指令优先）
        self.twist = twist
        self.active = True
        self.end_time_ns = self.get_clock().now().nanoseconds + int(duration * 1e9)
        self.get_logger().info(
            f'执行 {action}(distance={msg.distance}m angle={msg.angle}°) '
            f'→ v=({twist.linear.x:.2f}, {twist.angular.z:.2f}) 持续 {duration:.2f}s')

    # ================= 20Hz 心跳循环 =================
    def loop(self):
        now_ns = self.get_clock().now().nanoseconds
        # 安全①：动作到期 → 归零
        if self.active and now_ns >= self.end_time_ns:
            self.twist = Twist()
            self.active = False
            self.get_logger().info('动作完成，发零速')
        # 动作期发指令速度；静止期发零速（安全② 看门狗心跳）
        self.cmd_pub.publish(self.twist)


def main():
    rclpy.init()
    node = RobotController()

    # 夺回信号处理权：rclpy 默认处理器会先关 context，导致退出前零速发不出去
    # （Day7 安全钩子在 Ctrl+C / kill 下都可能失效）——恢复 KeyboardInterrupt 语义
    def _on_signal(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        # 退出前最后发一次零速：防止带着速度死掉、车在仿真里飞出去（此刻 context 仍有效）
        node.cmd_pub.publish(Twist())
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
