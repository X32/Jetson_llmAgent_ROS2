#!/usr/bin/env python3
"""
Day10 节点：tts_node（嘴）
订阅 /agent_answer → 离线 MeloTTS 合成 → 扬声器播放
设计要点：
  1. worker线程+队列：播放阻塞数秒，绝不能堵 executor 回调（原理见手册2.3）
  2. /tts_state 门控：播报期间 voice_input 静音，防自问自答回声循环
  3. 模型路径 ROS 参数注入，与 voice_input 同一模式
"""
import json
import queue
import threading
import time

import numpy as np

import rclpy
import sherpa_onnx
import sounddevice as sd
from rclpy.node import Node
from std_msgs.msg import Bool, String

MUTE_TAIL = 0.3   # 播放结束后再静音 0.3s（房间混响尾巴）


class TtsNode(Node):
    def __init__(self):
        super().__init__('tts_node')
        # 模型路径参数注入（绝对路径由命令行给）
        self.declare_parameter('model_dir', '')
        model_dir = self.get_parameter('model_dir').value
        self.declare_parameter('speed', 1.0)
        self.speed = self.get_parameter('speed').value

        # sherpa-onnx 离线 TTS（matcha 两段式，加载 ~2s，只做一次）
        # 构造与 tools/test_tts.py 同款；rule_fsts 必配（数字→中文读法）
        self.tts = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                matcha=sherpa_onnx.OfflineTtsMatchaModelConfig(
                    acoustic_model=f'{model_dir}/model-steps-3.onnx',
                    vocoder=f'{model_dir}/hifigan_v2.onnx',
                    lexicon=f'{model_dir}/lexicon.txt',
                    tokens=f'{model_dir}/tokens.txt',
                    dict_dir=f'{model_dir}/dict',
                ),
                num_threads=2,
            ),
            rule_fsts=f'{model_dir}/number.fst,{model_dir}/phone.fst',
        ))

        self.text_q = queue.Queue()
        self.state_pub = self.create_publisher(Bool, 'tts_state', 10)
        self.diag_pub = self.create_publisher(String, 'latency_diag', 10)
        self.create_subscription(String, 'agent_answer', self.on_answer, 10)

        threading.Thread(target=self.worker, daemon=True).start()
        self.get_logger().info(f'tts_node 就绪（matcha, speed={self.speed}），等待 /agent_answer ...')

    # ============ 回调只递纸条（微秒级返回） ============
    def on_answer(self, msg: String):
        if msg.data.strip():
            self.text_q.put(msg.data.strip())

    # ============ 重活全在 worker ============
    def worker(self):
        while rclpy.ok():
            text = self.text_q.get()
            # ① 播报门控开
            st = Bool(); st.data = True
            self.state_pub.publish(st)
            try:
                # ② 合成 + 峰值归一化（TTS 输出幅度不稳定，统一拉到 ±0.85）
                t0 = time.perf_counter()
                audio = self.tts.generate(text, speed=self.speed)
                gen_ms = (time.perf_counter() - t0) * 1000
                samples = np.asarray(audio.samples, dtype=np.float32)
                peak = np.abs(samples).max()
                if peak > 1e-4:
                    samples = samples / peak * 0.85
                # ③ 播放（阻塞到放完，worker 里允许）
                sd.play(samples, samplerate=audio.sample_rate)
                sd.wait()
                play_s = len(audio.samples) / audio.sample_rate
                self.get_logger().info(f'[播报] {text} | 生成{gen_ms:.0f}ms 音频{play_s:.1f}s')
                # ④ 诊断点（latency_recorder 自动忽略未知 stage，不影响 Day8 采集）
                diag = {'stage': 'tts', 'text': text,
                        'gen_ms': round(gen_ms), 'play_s': round(play_s, 2),
                        'done_at': time.time()}
                d = String(); d.data = json.dumps(diag, ensure_ascii=False)
                self.diag_pub.publish(d)
            except Exception as e:
                self.get_logger().error(f'播报失败: {e}')
            finally:
                # ⑤ 门控关 + 混响尾巴（睡在 worker 里，不占 executor）
                time.sleep(MUTE_TAIL)
                st.data = False
                self.state_pub.publish(st)


def main():
    rclpy.init()
    node = TtsNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        sd.stop()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
