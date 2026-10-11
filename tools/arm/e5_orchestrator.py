#!/usr/bin/env python3
"""E5 编排节点（手册 DOC/arm/experiment_E5.md §5.2）：意图 → grounding → 派发 → 对账

/voice_text → 关键词意图（LIFT/停止/未识别）→ /e5/command(snapshot) → 等 /e5/frame
→ 调 /grounding 服务（60s 兜底）→ /e5/goal → 等 /e5/result → 延迟对账(/latency_diag)
失败自动重试（--auto-retry N，仅对"执行失败"重试；门控拒绝/无检测不重试——
重试也改变不了感知结果，如实上报）。

线程模型与 e5_act_node 同款：回调只改状态/入队，主循环 poll future + watchdog，
零 executor 线程坑。系统 python3 运行（source install 后）：
  python3 tools/arm/e5_orchestrator.py --auto-retry 3
"""
import argparse
import json
import re
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from my_package.srv import Grounding

LIFT_WORDS = ('抓', '拿', '举', '夹', '提', '拾', '捡')   # 捡：10 指令协议实测踩漏的词
STOP_WORDS = ('停', 'stop', 'STOP')
OBJECT_ALIASES = {'方块': '红色方块', '正方体': '红色方块', '木块': '红色方块',
                  '杯子': '红色杯子', '球': '红色球', '碗': '蓝色碗'}


def extract_target(text):
    """指令 → grounding 目标词。别名映射优先；否则取"把X<动词>"之间的名词（交给 VLM 判有无）"""
    for k, v in OBJECT_ALIASES.items():
        if k in text:
            return v
    m = re.search(r'把(.{1,8}?)[' + ''.join(LIFT_WORDS) + r']', text)
    return m.group(1).strip() if m else None


class Orchestrator(Node):
    def __init__(self, max_retry):
        super().__init__('e5_orchestrator')
        self.max_retry = max_retry
        self.pub_cmd = self.create_publisher(String, 'e5/command', 10)
        self.pub_goal = self.create_publisher(String, 'e5/goal', 10)
        self.diag = self.create_publisher(String, 'latency_diag', 20)
        self.create_subscription(String, 'voice_text', self.on_voice, 10)
        self.create_subscription(String, 'e5/frame', self.on_frame, 10)
        self.create_subscription(String, 'e5/result', self.on_result, 10)
        self.cli = self.create_client(Grounding, 'grounding')
        self.state = 'IDLE'                     # IDLE/AWAIT_FRAME/AWAIT_VLM/AWAIT_RESULT
        self.instr_seq = 0
        self.get_logger().info(f'编排就绪（重试上限 {max_retry}）。指令示例："把桌上的方块抓起来"')

    def diag_pub(self, stage, **kw):
        self.diag.publish(String(data=json.dumps(
            {'node': 'e5_orch', 'stage': stage, **kw}, ensure_ascii=False)))

    def send_cmd(self, **kw):
        self.pub_cmd.publish(String(data=json.dumps(kw, ensure_ascii=False)))

    # ---- 指令入口 ----
    def on_voice(self, msg):
        text = msg.data.strip()
        if self.state != 'IDLE':
            self.get_logger().warn(f'忙（{self.state}），丢弃指令: {text}')
            return
        t0 = time.perf_counter()
        if any(w in text for w in STOP_WORDS):
            self.send_cmd(type='abort')
            self.get_logger().info(f'[停止] {text}')
            return
        if not any(w in text for w in LIFT_WORDS):
            self.diag_pub('intent', text=text, status='no_task', intent_ms=0)
            self.get_logger().info(f'[未识别为指令] {text!r}（需含 {LIFT_WORDS} 之一）')
            return
        target = extract_target(text)
        if not target:
            self.diag_pub('intent', text=text, status='no_target', intent_ms=0)
            self.get_logger().info(f'[未识别目标] {text!r}')
            return
        self.instr_seq += 1
        self.start_try(text, target, try_=1)

    def start_try(self, text, target, try_):
        self.text, self.target, self.try_ = text, target, try_
        self.task_id = f'e5_{self.instr_seq:03d}' + (f'_r{try_}' if try_ > 1 else '')
        self.t_voice = time.perf_counter()
        self.diag_pub('intent', task_id=self.task_id, text=self.text, task='LIFT',
                      target=self.target, status='ok', intent_ms=0.0, try_=try_)
        self.send_cmd(type='snapshot', task_id=self.task_id, instruction=self.text,
                      target=self.target, try_=try_)
        self.state, self.deadline = 'AWAIT_FRAME', time.perf_counter() + 15.0
        self.get_logger().info(f'[{self.task_id}] 指令: {text}（第 {try_} 次尝试）')

    # ---- 快照到达 → 调 grounding ----
    def on_frame(self, msg):
        f = json.loads(msg.data)
        if self.state != 'AWAIT_FRAME' or f['task_id'] != self.task_id:
            return
        self.t_frame = time.perf_counter()
        self.frame_send = int(f.get('send', 1000))
        req = Grounding.Request()
        req.target, req.image_path = self.target, f['image_path']
        self.vlm_req, self.vlm_att, self.vlm_ms_sum = req, 0, 0.0
        self.vlm_fut = self.cli.call_async(req)
        self.state, self.deadline = 'AWAIT_VLM', time.perf_counter() + 75.0

    # ---- 结果与重试 ----
    def on_result(self, msg):
        r = json.loads(msg.data)
        if self.state != 'AWAIT_RESULT' or r['task_id'] != self.task_id:
            return
        total_ms = (time.perf_counter() - self.t_voice) * 1e3
        self.diag_pub('e2e', task_id=self.task_id, total_ms=round(total_ms), status=r['status'],
                      success=bool(r.get('success')), try_=self.try_)
        self.get_logger().info(
            f"[{self.task_id}] {r['status']} success={r.get('success')} "
            f"steps={r.get('steps', '-')} 端到端 {total_ms / 1000:.2f}s")
        retryable = (r['status'] == 'done' and not r.get('success'))   # 策略失败才值得再试
        if retryable and self.try_ <= self.max_retry:
            self.send_cmd(type='abort')          # 复位 act 节点（可能仍在收尾）
            time.sleep(0.2)
            self.start_try(self.text, self.target, try_=self.try_ + 1)
        else:
            self.diag_pub('instr_done', instr_seq=self.instr_seq, tries=self.try_,
                          success=bool(r.get('success')), status=r['status'])
            self.state = 'IDLE'

    # ---- 主循环：poll future + watchdog ----
    def step_once(self):
        if self.state == 'AWAIT_VLM' and self.vlm_fut.done():
            resp = self.vlm_fut.result()
            self.t_goal = time.perf_counter()
            vlm_ms = float(resp.latency_ms)
            self.vlm_ms_sum += vlm_ms
            if resp.error or not resp.objects:
                status = resp.error[:80] if resp.error else 'no_det'
                self.diag_pub('grounding', task_id=self.task_id, status='fail',
                              vlm_ms=round(self.vlm_ms_sum), detail=status)
                self.get_logger().warn(f'[{self.task_id}] grounding 失败: {status}')
                total_ms = (time.perf_counter() - self.t_voice) * 1e3
                self.diag_pub('e2e', task_id=self.task_id, status='vlm_fail', success=False,
                              try_=self.try_, total_ms=round(total_ms))
                self.diag_pub('instr_done', instr_seq=self.instr_seq, tries=self.try_,
                              success=False, status='vlm_fail')
                self.finalize_vlm_fail()
                return
            o = resp.objects[0]
            if ((o.x2 - o.x1) * (o.y2 - o.y1) > 0.25 * self.frame_send ** 2
                    and self.vlm_att < 1):             # 整图级大框 → 重查一次（Step1 run3/4 实测模式）
                self.vlm_att += 1
                self.get_logger().warn(f'[{self.task_id}] 大框({o.x2-o.x1:.0f}×{o.y2-o.y1:.0f})，重查')
                self.vlm_fut = self.cli.call_async(self.vlm_req)
                return
            bbox = [o.x1, o.y1, o.x2, o.y2]
            self.pub_goal.publish(String(data=json.dumps(
                {'task_id': self.task_id, 'bbox': bbox, 'grade': o.grade,
                 'confidence': o.confidence, 'vlm_ms': vlm_ms})))
            orch_ms = (self.t_goal - self.t_frame) * 1e3 - self.vlm_ms_sum
            self.diag_pub('grounding', task_id=self.task_id, status='ok',
                          vlm_ms=round(self.vlm_ms_sum), orch_ms=round(orch_ms, 1),
                          grade=o.grade + ('+retry' if self.vlm_att else ''),
                          bbox=[round(b) for b in bbox])
            self.state, self.deadline = 'AWAIT_RESULT', time.perf_counter() + 120.0
        if self.state != 'IDLE' and time.perf_counter() > self.deadline:
            why = {'AWAIT_FRAME': 'act 节点无响应', 'AWAIT_VLM': 'grounding 超时',
                   'AWAIT_RESULT': '执行超时'}[self.state]
            self.get_logger().error(f'[{self.task_id}] {why}')
            self.diag_pub('e2e', task_id=self.task_id, status='timeout', success=False,
                          try_=self.try_, total_ms=round((time.perf_counter() - self.t_voice) * 1e3))
            self.finalize_vlm_fail()
            self.diag_pub('instr_done', instr_seq=self.instr_seq, tries=self.try_,
                          success=False, status='timeout')
            self.state = 'IDLE'

    def finalize_vlm_fail(self):
        self.send_cmd(type='abort')              # 让 WAIT_GOAL 中的 act 节点复位
        self.state = 'IDLE'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--auto-retry', type=int, default=3)
    args = p.parse_args()
    rclpy.init()
    node = Orchestrator(args.auto_retry)
    if not node.cli.wait_for_service(timeout_sec=10.0):
        node.get_logger().error('/grounding 服务 10s 未出现——先起 T1（ros2 run vision_agent grounding）')
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.05)
            node.step_once()
    except (KeyboardInterrupt, SystemExit):
        pass
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == '__main__':
    main()
