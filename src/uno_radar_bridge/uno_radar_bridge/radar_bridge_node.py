#!/usr/bin/env python3
"""
uno_radar_bridge — Arduino Uno 超声波雷达串口桥接节点

读取 Uno(UltrasonicRadar.ino) 输出的串口数据：
    SCAN_START
    <角度>,<距离cm>     (距离为 -1 表示无回波)
    SCAN_END
聚合成 sensor_msgs/LaserScan 发布到 /scan（frame_id: laser）。
每个方向(去程/回程)扫完发布一次，约 11 秒一帧。
"""

import math
import threading

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

import serial
import serial.serialutil

N_ANGLES = 181  # 0°~180°，每度一点


class RadarBridgeNode(Node):

    def __init__(self):
        super().__init__('uno_radar_bridge')
        self.declare_parameter('port', '/dev/ttyACM0')
        self.declare_parameter('baud', 115200)
        self.declare_parameter('frame_id', 'laser')
        self.declare_parameter('range_min', 0.02)  # HC-SR04 最小 2cm
        self.declare_parameter('range_max', 4.0)   # 30ms 回波超时约 5m，留裕量

        port = self.get_parameter('port').value
        baud = self.get_parameter('baud').value

        self.publisher = self.create_publisher(LaserScan, 'scan', 10)
        self.sweep = {}          # angle -> distance(m)
        self.scan_start = self.now_sec()

        self.ser = self.open_serial(port, baud)

        # 串口读线程：readline 阻塞，不占 executor
        self.rx_thread = threading.Thread(target=self.rx_loop, daemon=True)
        self.rx_thread.start()
        self.get_logger().info(f'桥接启动: {port}@{baud} -> /scan')

    # ---------- 串口 ----------

    def open_serial(self, port, baud):
        try:
            return serial.Serial(port, baud, timeout=1.0)
        except serial.serialutil.SerialException as e:
            self.get_logger().error(
                f'无法打开 {port}: {e}。'
                '请确认已插板、且 Arduino IDE 串口监视器已关闭。')
            raise SystemExit(1)

    def rx_loop(self):
        """后台线程：持续读串口，按行解析。"""
        while rclpy.ok():
            try:
                raw = self.ser.readline().decode(errors='ignore').strip()
            except (serial.serialutil.SerialException, OSError) as e:
                self.get_logger().error(f'串口读取失败: {e}，5 秒后重连')
                self.reconnect()
                continue
            if not raw:
                continue
            self.handle_line(raw)

    def reconnect(self):
        import time
        while rclpy.ok():
            try:
                self.ser.close()
                self.ser = self.open_serial(
                    self.get_parameter('port').value,
                    self.get_parameter('baud').value)
                self.get_logger().info('串口已重连')
                return
            except SystemExit:
                pass
            except serial.serialutil.SerialException:
                time.sleep(5)  # 后台线程无 executor，用普通 sleep

    # ---------- 协议解析 ----------

    def handle_line(self, line):
        if line == 'SCAN_START':
            self.sweep = {}
            self.scan_start = self.now_sec()
            return
        if line == 'SCAN_END':
            self.publish_scan()
            return
        parts = line.split(',')
        if len(parts) != 2:
            return
        try:
            angle = int(parts[0])
            distance_cm = float(parts[1])
        except ValueError:
            return
        if not (0 <= angle < N_ANGLES):
            return
        if distance_cm <= 0:
            self.sweep[angle] = float('inf')  # 无回波 -> inf(RViz 不显示)
        else:
            self.sweep[angle] = distance_cm / 100.0  # cm -> m

    # ---------- 发布 ----------

    def publish_scan(self):
        if not self.sweep:
            return
        now = self.now_sec()
        sweep_duration = max(now - self.scan_start, 0.1)

        msg = LaserScan()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.get_parameter('frame_id').value
        msg.angle_min = 0.0
        msg.angle_max = math.pi                      # 180°
        msg.angle_increment = math.pi / (N_ANGLES - 1)
        msg.scan_time = sweep_duration
        msg.time_increment = sweep_duration / N_ANGLES
        msg.range_min = self.get_parameter('range_min').value
        msg.range_max = self.get_parameter('range_max').value

        ranges = [float('inf')] * N_ANGLES           # 缺失角度不瞎编
        for angle, dist in self.sweep.items():
            ranges[angle] = dist
        msg.ranges = ranges

        self.publisher.publish(msg)
        n_valid = sum(1 for r in ranges if math.isfinite(r))
        self.get_logger().info(
            f'发布 /scan: {n_valid}/{N_ANGLES} 点有效, '
            f'耗时 {sweep_duration:.1f}s')
        self.scan_start = now   # 防御：即使固件漏发 SCAN_START 也重置计时基准

    def now_sec(self):
        return self.get_clock().now().nanoseconds * 1e-9


def main(args=None):
    rclpy.init(args=args)
    node = RadarBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
