#!/usr/bin/env python3
"""E5 延迟采集器（手册 DOC/arm/experiment_E5.md §6.1，Day8 零侵入模式移植）

只订阅 /latency_diag（JSON-in-String），按 task_id 聚合各段：
  S1 意图(intent_ms)  S2 快照(render_ms)  S3 VLM(vlm_ms+orch_ms)  S4 坐标(coord_ms)
  S5 首步(to_first_step_ms)  S6 执行(exec_ms)  Σ 端到端(e2e.total_ms)
收到 e2e 即定稿一行并实时打印；Ctrl+C 出 results/e5_latency.csv + markdown 对账表。
残差 = total − ΣS1..S6（阈值 100ms，超限标 ⚠）。

用法：source install/setup.bash && python3 tools/arm/e5_latency_recorder.py
"""
import csv
import json
import os
import signal
import sys

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

CSV_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', 'results', 'e5_latency.csv'))
COLS = ['task_id', 'text', 'status', 'success', 's1_intent', 's2_snapshot', 's3_vlm',
        'orch_ms', 's4_coord', 's5_first_step', 's6_exec', 'sum', 'total', 'residual',
        'xy_err_cm', 'gate', 'steps', 'chunk_p50', 'grade']


class Recorder(Node):
    def __init__(self):
        super().__init__('e5_latency_recorder')
        self.rows, self.instr = {}, []
        self.create_subscription(String, 'latency_diag', self.on_diag, 50)
        print('E5 延迟采集器就绪：跑指令即出行；Ctrl+C 出 CSV + 对账表\n')

    def on_diag(self, msg):
        d = json.loads(msg.data)
        stage = d.get('stage')
        if stage == 'instr_done':
            self.instr.append(d)
            print(f"  [指令#{d['instr_seq']}] tries={d['tries']} → {d['status']}"
                  f" success={d['success']}")
            return
        tid = d.get('task_id')
        if not tid:
            return
        r = self.rows.setdefault(tid, {'task_id': tid})
        if stage == 'intent':
            r.update(text=d.get('text', ''), s1_intent=d.get('intent_ms'))
        elif stage == 'snapshot':
            r['s2_snapshot'] = d.get('render_ms')
        elif stage == 'grounding':
            r.update(s3_vlm=d.get('vlm_ms'), orch_ms=d.get('orch_ms'), grade=d.get('grade'))
        elif stage == 'coord':
            r.update(s4_coord=d.get('coord_ms'), xy_err_cm=d.get('xy_err_cm'), gate=d.get('gate'))
        elif stage == 'first_step':
            r['s5_first_step'] = d.get('to_first_step_ms')
        elif stage == 'exec_start':
            r['first_chunk_ms'] = d.get('first_chunk_ms')   # 参考列（S5 已含）
        elif stage == 'exec_done':
            r.update(s6_exec=d.get('exec_ms'), steps=d.get('steps'),
                     chunk_p50=d.get('chunk_p50'), success=d.get('success'))
        elif stage == 'e2e':
            r.update(total=d.get('total_ms'), status=d.get('status'),
                     success=d.get('success'), try_=d.get('try_'))
            self.finalize(r)

    def finalize(self, r):
        segs = ['s1_intent', 's2_snapshot', 's3_vlm', 's4_coord', 's5_first_step', 's6_exec']
        ssum = sum(r[k] for k in segs if isinstance(r.get(k), (int, float)))
        r['sum'] = round(ssum)
        if isinstance(r.get('total'), (int, float)):
            r['residual'] = r['total'] - ssum
            mark = ' ⚠残差>100ms' if r['residual'] > 100 else ''
            print(f"  [{r['task_id']}] {r.get('status')}/{'✅' if r.get('success') else '❌'}"
                  f" 决策 {r.get('s1_intent', 0) + r.get('s2_snapshot', 0) + r.get('s3_vlm', 0) + r.get('s4_coord', 0):.0f}ms"
                  f" + 首步 {r.get('s5_first_step', 0):.0f}ms + 执行 {r.get('s6_exec', 0)}ms"
                  f" = Σ{ssum:.0f}ms vs 总 {r['total']}ms（残差 {r['residual']}ms）{mark}")

    def dump(self):
        rows = list(self.rows.values())
        with open(CSV_PATH, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=COLS + ['try_', 'first_chunk_ms'], extrasaction='ignore')
            w.writeheader()
            for r in rows:
                w.writerow(r)
        done = [r for r in rows if isinstance(r.get('total'), (int, float))]
        print(f'\n==== E5 延迟对账（{len(done)} 条完整 / 共 {len(rows)} 行）====')
        if done:
            def m(k):
                v = [r[k] for r in done if isinstance(r.get(k), (int, float))]
                return sum(v) / len(v) if v else float('nan')
            print(f"| {'段':<8} | 均值 ms |")
            print(f'|---|---|')
            for k, lab in [('s1_intent', 'S1 意图'), ('s2_snapshot', 'S2 快照'),
                           ('s3_vlm', 'S3 VLM'), ('s4_coord', 'S4 坐标'),
                           ('s5_first_step', 'S5 首步'), ('s6_exec', 'S6 执行'),
                           ('sum', 'Σ 分项'), ('total', '端到端'), ('residual', '残差')]:
                print(f'| {lab} | {m(k):.1f} |')
            bad = [r['task_id'] for r in done if r.get('residual', 0) > 100]
            print(f"\n残差超限(>100ms): {bad if bad else '无 ✅'}")
            err = [r['xy_err_cm'] for r in rows if isinstance(r.get('xy_err_cm'), (int, float))]
            if err:
                print(f"坐标链 xy 误差: 均值 {sum(err)/len(err):.2f}cm / 最大 {max(err):.2f}cm（N={len(err)}）")
        print(f'CSV → {CSV_PATH}')


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))   # timeout/TaskStop 也走优雅出表
    rclpy.init()
    node = Recorder()
    try:
        while rclpy.ok():
            rclpy.spin_once(node, timeout_sec=0.2)
    except (KeyboardInterrupt, SystemExit):
        pass
    node.dump()
    node.destroy_node()
    if rclpy.ok():                                # SIGINT 时 rclpy 自带 handler 已关过
        rclpy.shutdown()


if __name__ == '__main__':
    main()
