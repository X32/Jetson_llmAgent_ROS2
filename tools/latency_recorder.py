#!/usr/bin/env python3
"""
Day8 Step8 延迟采集器：自动拼"说完→车动"延迟表（experiment_8.md Step8 同款列）

数据来源（零侵入，只订阅不改节点）：
  /latency_diag (String, JSON)
    - voice_input 发 {stage:'asr', text, audio_s, asr_ms, seg_emitted_at}
    - llm_agent   发 {stage:'llm', text, status, action, fc_ms, msg_ms, done_at}
  /cmd_vel (Twist)
    - controller 静止期发零速心跳、动作期非零 → "零→非零"跳变 = 车动时刻

配对与计算：
  asr ↔ llm 按"相同文本（时间窗内）"配对
  说完时刻 = seg_emitted_at − 0.5（VAD min_silence_duration 固定等待）
  端到端   = 首帧非零 /cmd_vel 时刻 − 说完时刻
  stop 指令无"非零跳变"（controller 立即发零速）→ 端到端≈llm 完成，标注 <50ms
  rejected / no_tool / error 行标注状态，不算端到端

用法：
  source install/setup.bash && python3 tools/latency_recorder.py
  （说话测试 → 每完成一行实时打印 → Ctrl+C 出 CSV + Markdown 表）
  注意：上一条动作执行完再说下一条（/cmd_vel 跳变检测假设静止起步）
"""
import csv
import json
import os
import time
from collections import defaultdict

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from std_msgs.msg import String

VAD_WAIT = 0.5          # voice_input 的 min_silence_duration（说完→段落切出的固定等待）
MATCH_WINDOW = 15.0     # asr↔llm 配对时间窗
CMD_VEL_WINDOW = 8.0    # llm 完成后等多久的车动（FC 冷启动慢也够）
MOVE_THRESHOLD = 0.01   # |linear.x| 或 |angular.z| 超过此值算"车动"
CSV_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'results', 'day8_latency.csv'))

STATUS_NOTE = {'rejected': '拒绝', 'no_tool': '未识别为指令',
               'invalid_param': '参数非法', 'error': 'LLM错误'}


class LatencyRecorder(Node):
    def __init__(self):
        super().__init__('latency_recorder')
        self.asr_queue = []     # 待配对的 asr 事件
        self.pending = []       # 已配对、等车动的行（FIFO；指令连发时不丢行）
        self.rows = []          # 已完成的行
        self.idx = 0
        self.was_moving = False # 上一帧 /cmd_vel 是否非零
        self.create_subscription(String, 'latency_diag', self.on_diag, 20)
        self.create_subscription(Twist, 'cmd_vel', self.on_cmd_vel, 50)
        # 超时检查用定时器：不依赖 /cmd_vel 有发布者（controller 没起也能定稿）
        self.create_timer(1.0, self.check_timeouts)
        print('延迟采集器就绪：一条指令执行完再说下一条；Ctrl+C 出表\n')

    # ================= 诊断事件 =================
    def on_diag(self, msg: String):
        try:
            d = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        if d.get('stage') == 'asr':
            self.asr_queue.append(d)
            print(f"  [asr] \"{d['text']}\" 音频{d['audio_s']}s ASR={d['asr_ms']}ms")
        elif d.get('stage') == 'llm':
            self.on_llm(d)

    def on_llm(self, d):
        asr = self.match_asr(d.get('text', ''))
        speech_end = (asr['seg_emitted_at'] - VAD_WAIT) if asr else None
        row = {
            'idx': 0, 'text': d.get('text', ''),
            'asr_text': asr['text'] if asr else '(无ASR事件)',
            'audio_s': asr['audio_s'] if asr else '',
            'asr_ms': asr['asr_ms'] if asr else '',
            'fc_ms': d.get('fc_ms', 0), 'msg_ms': d.get('msg_ms', 0.0),
            'action': d.get('action', ''), 'status': d.get('status', ''),
            'speech_end': speech_end, 'llm_done': d.get('done_at', time.time()),
            'e2e': None,
        }
        if row['status'] != 'success':
            self.finish_row(row)          # 拒绝/失败行直接定稿，不算端到端
            return
        if row['action'] == 'stop':
            row['e2e'] = (row['llm_done'] - speech_end) if speech_end else None
            self.finish_row(row)          # stop 无跳变可测，端到端≈llm 完成（控制<50ms）
            return
        self.pending.append(row)          # 等待车动（on_cmd_vel 填端到端）

    def match_asr(self, text):
        """优先同文本，其次时间窗内最近的（llm 事件文本 = /voice_text = ASR 文本）"""
        for i in range(len(self.asr_queue) - 1, -1, -1):
            if self.asr_queue[i].get('text') == text:
                return self.asr_queue.pop(i)
        now = time.time()
        for i in range(len(self.asr_queue) - 1, -1, -1):
            if now - self.asr_queue[i].get('seg_emitted_at', 0) <= MATCH_WINDOW:
                return self.asr_queue.pop(i)
        return None

    # ================= 车动检测 =================
    def on_cmd_vel(self, msg: Twist):
        now = time.time()
        moving = (abs(msg.linear.x) > MOVE_THRESHOLD
                  or abs(msg.angular.z) > MOVE_THRESHOLD)
        if self.pending and moving and not self.was_moving:
            row = self.pending.pop(0)     # FIFO：跳变归最早已配对未完成行
            row['e2e'] = (now - row['speech_end']) if row['speech_end'] else None
            self.finish_row(row)
        self.was_moving = moving

    def check_timeouts(self):
        """超时兜底（定时器驱动，controller 缺席也能定稿）"""
        now = time.time()
        for row in [r for r in self.pending if now - r['llm_done'] > CMD_VEL_WINDOW]:
            self.pending.remove(row)
            self.finish_row(row)

    # ================= 行定稿 =================
    def finish_row(self, row):
        self.idx += 1
        row['idx'] = self.idx
        self.rows.append(row)
        e2e = f"{row['e2e']:.2f}" if row['e2e'] is not None else '—'
        note = STATUS_NOTE.get(row['status'], '')
        asr_ms = row['asr_ms'] if row['asr_ms'] != '' else '—'
        print(f"  ✓ 第{row['idx']}行 {row['text']}: "
              f"ASR={asr_ms}ms FC={row['fc_ms']}ms 端到端={e2e}s {note}")


def report(rows):
    """打印 Step8 同款 Markdown 表 + 重复指令聚合统计"""
    print('\n## Step8 延迟数据表（可直接粘贴 experiment_8.md）\n')
    print('| # | 口说指令 | ASR 输出 | 音频(s) | ASR(ms) | FC(ms) | 端到端(s) 说完→车动 | 备注 |')
    print('| --- | --- | --- | --- | --- | --- | --- | --- |')
    for r in rows:
        e2e = f"{r['e2e']:.2f}" if r['e2e'] is not None else '—'
        note = STATUS_NOTE.get(r['status'], '')
        if r['action'] == 'stop':
            note = '立即停(控制<50ms)'
        asr_ms = r['asr_ms'] if r['asr_ms'] != '' else '—'
        audio = r['audio_s'] if r['audio_s'] != '' else '—'
        print(f"| {r['idx']} | {r['text']} | {r['asr_text']} | {audio} "
              f"| {asr_ms} | {r['fc_ms']} | {e2e} | {note} |")

    groups = defaultdict(list)
    for r in rows:
        if r['e2e'] is not None:
            groups[r['text']].append(r['e2e'])
    stats = {t: v for t, v in groups.items() if len(v) >= 2}
    if stats:
        print('\n重复指令聚合（端到端）：')
        for t, v in stats.items():
            m = sum(v) / len(v)
            std = (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5
            print(f'  {t} ×{len(v)}: 均值 {m:.2f}s ± {std:.2f}')


def save_csv(rows):
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    fields = ['idx', 'text', 'asr_text', 'audio_s', 'asr_ms', 'fc_ms', 'msg_ms',
              'action', 'status', 'e2e']
    with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as f:  # utf-8-sig: Excel 中文不乱码
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({**r, 'e2e': f"{r['e2e']:.3f}" if r['e2e'] is not None else ''})
    print(f'\nCSV 已写入 {CSV_PATH}')


def main():
    rclpy.init()
    node = LatencyRecorder()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        if node.pending:
            waiting = '、'.join(r['text'] for r in node.pending)
            print(f'\n⚠ 有行未等到车动（{waiting}），未计入')
        report(node.rows)
        if node.rows:
            save_csv(node.rows)
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
