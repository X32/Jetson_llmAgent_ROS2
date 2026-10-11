#!/usr/bin/env python3
"""E-YOLO-BOARD PC 桥：/grounding_yolo（Grounding.srv 传路径，旧契约）⇄ /yolo_board 话题对（传字节，板上 TRT）。

存在理由：e5v3 只认 Grounding.srv+文件路径；板上服务只吃字节。桥在中间读图转字节，
两头协议都原样——e5_grasp_v3_node 一个字节不用改，旧 yolo_grounding 停掉、本桥顶名即切换后端。
真机形态没有 PC，客户端直连 /yolo_board 话题对，本桥即退役。

运行（PC，需 ROS2 环境）:
  source install/setup.bash && python3 tools/arm/yolo_board_bridge_node.py
"""
import array
import json
import threading
import time

import numpy as np
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import UInt8MultiArray, String

from my_package.msg import DetectedObject
from my_package.srv import Grounding


class BridgeNode(Node):
    def __init__(self):
        super().__init__('yolo_board_bridge')
        self.cb = ReentrantCallbackGroup()
        self.srv = self.create_service(Grounding, 'grounding_yolo', self.on_grounding,
                                       callback_group=self.cb)
        self.pub_req = self.create_publisher(UInt8MultiArray, '/yolo_board/req', 10)
        self.create_subscription(String, '/yolo_board/resp', self.on_resp, 10,
                                 callback_group=self.cb)
        self.seq = 0
        self.inbox = {}
        self.rpc_timeout = 3.0
        self.get_logger().info('yolo_board_bridge 就绪：/grounding_yolo（Grounding 传路径）→ '
                               '/yolo_board 话题对（板上 TRT）；旧 yolo_grounding 勿同时在线（会抢答）')

    # ---- 板上话题对 RPC ----
    def on_resp(self, msg):
        try:
            d = json.loads(msg.data)
            ev = self.inbox.get(int(d.get('seq', -1)))
            if ev is not None:
                ev['data'] = d                         # 结果放进等待方手里的 holder 再放行
                ev['event'].set()
        except Exception as e:
            self.get_logger().error(f'on_resp 异常: {e!r}')

    def board_call(self, target: str, jpg: bytes):
        for attempt in (1, 2):                          # 超时重发 1 次（照 e5v3 规矩）
            self.seq = (self.seq + 1) & 0xFFFFFFFF
            seq = self.seq
            tb = target.encode('utf-8')
            payload = np.array([seq, len(tb)], '<u4').tobytes() + tb + jpg
            m = UInt8MultiArray()
            m.data = array.array('B', payload)
            holder = dict(event=threading.Event(), data=None)
            self.inbox[seq] = holder
            self.pub_req.publish(m)
            if holder['event'].wait(self.rpc_timeout):
                d = holder['data']
                self.inbox.pop(seq, None)
                if d.get('error'):
                    raise RuntimeError(f'板上服务报错: {d["error"]}')
                return d
            self.inbox.pop(seq, None)
            self.get_logger().warn(f'seq={seq} 第{attempt}次超时，重发')
        raise TimeoutError('板上 YOLO 服务 2 次超时')

    # ---- 旧契约服务端（原样兼容 e5v3）----
    def on_grounding(self, req, resp):
        t0 = time.perf_counter()
        try:
            if not req.image_path:
                resp.error = 'bridge: image_path 为空（取摄像头帧是旧节点功能，桥不支持）'
                return resp
            with open(req.image_path, 'rb') as fh:
                jpg = fh.read()
            d = self.board_call(req.target or '目标', jpg)
            resp.objects = [DetectedObject(label=o['label'], x1=float(o['x1']), y1=float(o['y1']),
                                           x2=float(o['x2']), y2=float(o['y2']),
                                           confidence=float(o['confidence']),
                                           grade=o.get('grade', 'TRT'))
                            for o in d['objects']]
            resp.latency_ms = (time.perf_counter() - t0) * 1e3   # 含读图+跨机来回，如实报
            resp.error = ''
        except Exception as e:
            resp.error = repr(e)
            self.get_logger().error(f'on_grounding: {e!r}')
        return resp


def main():
    rclpy.init()
    node = BridgeNode()
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(node)
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
