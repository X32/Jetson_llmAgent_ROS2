#!/usr/bin/env python3
"""
Day9 节点：state_query（眼睛 + 里程记忆）
订阅 /scan /odom → 维护最新快照 → 服务 /query_sensor 返回"环境摘要"
设计要点：摘要在这里压缩完成（360个float → 3句话），LLM 永远不见原始数组
"""
import math
import time

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan

from my_package.srv import QuerySensor

STALE_SEC = 2.0   # 传感器数据超过 2 秒没更新视为过期


class StateQueryNode(Node):
    def __init__(self):
        super().__init__('state_query')

        # 扇区划分与障碍阈值（可 --ros-args -p 覆盖）
        self.declare_parameter('front_half_angle', 15.0)    # "前方"扇区半角(度)
        self.declare_parameter('side_half_angle', 30.0)     # 左/右扇区半角(度)
        self.declare_parameter('obstacle_threshold', 1.0)   # 障碍判定阈值(米)
        self.front_half = math.radians(self.get_parameter('front_half_angle').value)
        self.side_half = math.radians(self.get_parameter('side_half_angle').value)
        self.obs_th = self.get_parameter('obstacle_threshold').value

        # ===== 传感器快照 =====
        self.scan = None            # 最新一帧 LaserScan
        self.scan_time = 0.0
        self.traveled = 0.0         # 累计行驶里程（对相邻 odom 位置差累加）
        self.last_pos = None
        self.pos = None
        self.yaw_deg = None

        self.create_subscription(LaserScan, 'scan', self.on_scan, 10)
        self.create_subscription(Odometry, 'odom', self.on_odom, 10)
        self.create_service(QuerySensor, 'query_sensor', self.on_query)
        self.get_logger().info('state_query 就绪，等待 /query_sensor 请求 ...')

    # ================= 传感器快照维护 =================
    def on_scan(self, msg: LaserScan):
        self.scan = msg
        self.scan_time = time.time()

    def on_odom(self, msg: Odometry):
        p = msg.pose.pose.position
        if self.last_pos is not None:
            self.traveled += math.hypot(p.x - self.last_pos[0], p.y - self.last_pos[1])
        self.last_pos = (p.x, p.y)
        self.pos = (p.x, p.y)
        # 四元数 → 偏航角（deg，[-180,180)）
        q = msg.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y),
                         1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self.yaw_deg = math.degrees(yaw)

    # ================= 扇区最小距离 =================
    def sector_min(self, center_deg: float, half_rad: float):
        """center_deg 方位 ± half_rad 扇区内的最小有效距离；无有效数据返回 None
        有效 = 非 inf/NaN、大于 range_min、非 0（0 通常表示无回波）"""
        if self.scan is None:
            return None
        center = math.radians(center_deg)
        best = None
        s = self.scan
        for i, r in enumerate(s.ranges):
            ang = s.angle_min + i * s.angle_increment
            # 角度归一化到 [-pi, pi)
            ang = math.atan2(math.sin(ang), math.cos(ang))
            d = abs(ang - center)
            d = min(d, 2 * math.pi - d)          # 处理 ±180 附近环绕
            if d > half_rad:
                continue
            if math.isinf(r) or math.isnan(r) or r <= s.range_min or r == 0.0:
                continue
            if s.range_max > 0 and r >= s.range_max:
                continue                          # 到量程外 = 没看到东西
            best = r if best is None else min(best, r)
        return best

    # ================= 服务回调：生成环境摘要 =================
    def on_query(self, request: QuerySensor.Request, response: QuerySensor.Response):
        t = request.type
        stale = time.time() - self.scan_time > STALE_SEC
        lines = []

        if t in ('lidar', 'all'):
            front = self.sector_min(0.0, self.front_half)
            left = self.sector_min(90.0, self.side_half)
            right = self.sector_min(-90.0, self.side_half)
            response.front_min = front if front is not None else -1.0
            response.left_min = left if left is not None else -1.0
            response.right_min = right if right is not None else -1.0
            if front is None:
                # 关键措辞：明确"数据不可用"，防止 LLM 把"不知道"说成"没有障碍"
                # （实测踩坑：模型曾把本句回答成"前面没有检测到明显的障碍物"）
                lines.append('激光雷达数据不可用（无有效数据）——'
                             '请如实告知用户传感器暂时异常，无法判断障碍情况，禁止推测')
            else:
                obs = '有' if front < self.obs_th else '无'
                lines.append(
                    f'前方最近障碍{front:.2f}米（判定：{obs}障碍，阈值{self.obs_th}米）')
                if left is not None and right is not None:
                    lines.append(f'左侧最近{left:.2f}米，右侧最近{right:.2f}米')
            if stale:
                lines.append(f'（注意：雷达数据已{time.time()-self.scan_time:.0f}秒未更新）')

        if t in ('odom', 'all'):
            response.traveled = self.traveled
            if self.pos is not None:
                lines.append(
                    f'已累计行驶{self.traveled:.2f}米，当前位置x={self.pos[0]:.2f} '
                    f'y={self.pos[1]:.2f}，朝向{self.yaw_deg:.0f}度')

        response.summary = '；'.join(lines) if lines else '未知查询类型'
        self.get_logger().info(f'查询[{t}] → {response.summary}')
        return response


def main():
    rclpy.init()
    node = StateQueryNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
