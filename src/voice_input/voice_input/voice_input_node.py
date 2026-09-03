#!/usr/bin/env python3
"""
Day8 节点：voice_input（耳朵）
麦克风 → silero VAD 自动切段 → SenseVoice 离线识别 → 发布 /voice_text (String)
模式：
  vad（默认） —— 连续听音，说完自动断句识别（演示用）
  manual      —— 回车开始录 N 秒（调试/演示兜底：环境噪声把 VAD 搞疯时用）
延迟打点：[ASR] 音频x.xs 识别=xxx ms
下游（llm_agent）零改动——今天只是换了"谁往 /voice_text 里发消息"。
"""
import json
import os
import re
import time
import threading

import numpy as np
import sounddevice as sd
import sherpa_onnx

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

SAMPLE_RATE = 16000   # SenseVoice 要求的采样率
VAD_BLOCK = 512       # silero VAD 要求的窗长（16kHz 下用 512）


class VoiceInputNode(Node):
    def __init__(self):
        super().__init__('voice_input')

        # ===== 参数：模型路径参数化（200MB+ 模型不进包不进 git，路径由外部传入）=====
        self.declare_parameter(
            'model_dir', '/home/zy/Desktop/workplace/Jetson_llmAgent_ROS2/models/asr/sense-voice')
        self.declare_parameter(
            'vad_model', '/home/zy/Desktop/workplace/Jetson_llmAgent_ROS2/models/asr/silero_vad.onnx')
        self.declare_parameter('mode', 'vad')            # vad / manual
        self.declare_parameter('manual_duration', 4.0)   # manual 模式录音秒数
        self.declare_parameter('cooldown', 1.0)          # 发布后冷却(s)，防尾音被切成第二段
        # 麦克风设备：Jetson 的 USB 麦硬件只支持 48kHz，直连开 16kHz 流会失败，
        # 必须走 pulse（PulseAudio 自动重采样到 16kHz）；PC 用系统默认即可
        self.declare_parameter(
            'device', 'pulse' if os.uname().machine == 'aarch64' else '')

        model_dir = self.get_parameter('model_dir').value
        vad_model = self.get_parameter('vad_model').value
        self.mode = self.get_parameter('mode').value
        self.manual_duration = self.get_parameter('manual_duration').value
        self.cooldown = self.get_parameter('cooldown').value
        device = self.get_parameter('device').value
        # 'pulse'/'' → None = 用系统默认选择；数字字符串 → PortAudio 索引
        self.device = int(device) if str(device).isdigit() else (device or None)

        # ===== ASR 引擎：SenseVoice int8（CPU 实时）=====
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=os.path.join(model_dir, 'model.int8.onnx'),
            tokens=os.path.join(model_dir, 'tokens.txt'),
            use_itn=True,
        )

        # ===== VAD：silero（2MB，CPU 实时判断"哪段是人声"）=====
        # sherpa-onnx 1.13.x API：VoiceActivityDetector 直接用 VadModelConfig 创建
        silero_vad_config = sherpa_onnx.SileroVadModelConfig(
            model=vad_model,
            threshold=0.5,
            min_silence_duration=0.5,   # 静默 0.5s → 认为说完了，切出一段
            min_speech_duration=0.25,   # 短于 0.25s 的声音当噪声丢弃
            max_speech_duration=8.0,    # 单段最长 8s（指令都是短句）
            window_size=VAD_BLOCK,
        )
        vad_config = sherpa_onnx.VadModelConfig(
            silero_vad=silero_vad_config,
            sample_rate=SAMPLE_RATE,
        )
        self.vad = sherpa_onnx.VoiceActivityDetector(vad_config)
        self.in_speech = False      # 仅用于日志提示"开始说话了"
        self.last_publish = 0.0

        self.text_pub = self.create_publisher(String, 'voice_text', 10)
        # Step8 延迟采集：诊断通道（JSON-in-String，dev-only 不建 msg）
        self.diag_pub = self.create_publisher(String, 'latency_diag', 10)

        # Day10 回声门控：播报期间丢弃 VAD 段落，防止机器人"听到自己说话"
        # （不自问自答的前提；MUTE_TAIL 兜房间混响）
        self.tts_mute_until = 0.0
        self.create_subscription(Bool, 'tts_state', self.on_tts_state, 10)

        # 麦克风采集是阻塞循环，放独立线程（主线程留给 rclpy.spin）
        threading.Thread(target=self.mic_loop, daemon=True).start()
        self.get_logger().info(f'voice_input 就绪（{self.mode} 模式），等待说话 ...')

    def on_tts_state(self, msg: Bool):
        """tts_node 播报状态回调：true=开始播报（一直静音），false=结束（留0.3s尾巴）"""
        if msg.data:
            self.tts_mute_until = float('inf')
        else:
            self.tts_mute_until = time.time() + 0.3

    # ================= 核心：识别 + 发布 =================
    def recognize_and_publish(self, samples: np.ndarray, t_pop: float = 0.0):
        audio_s = len(samples) / SAMPLE_RATE

        t0 = time.perf_counter()
        stream = self.recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        self.recognizer.decode_stream(stream)
        dt_ms = (time.perf_counter() - t0) * 1000

        # SenseVoice 偶尔吐 <|zh|><|NEUTRAL|> 之类控制标签，清洗掉（防御性一行）
        text = re.sub(r'<\|[^|]*\|>', '', stream.result.text).strip()
        if not text:
            return

        self.get_logger().info(
            f'[ASR] 音频{audio_s:.1f}s 识别={dt_ms:.0f}ms → "{text}"')
        msg = String()
        msg.data = text
        self.text_pub.publish(msg)
        self.last_publish = time.time()

        # 延迟诊断：t_pop=段落切出时刻，说完时刻≈t_pop−0.5s（VAD 等待），采集器据此算端到端
        diag = {'stage': 'asr', 'text': text, 'audio_s': round(audio_s, 2),
                'asr_ms': round(dt_ms), 'seg_emitted_at': t_pop or time.time()}
        d = String()
        d.data = json.dumps(diag, ensure_ascii=False)
        self.diag_pub.publish(d)

    # ================= 模式1：VAD 连续听音 =================
    def mic_loop(self):
        if self.mode == 'manual':
            return self.manual_loop()

        with sd.InputStream(device=self.device, channels=1, dtype='float32',
                            samplerate=SAMPLE_RATE, blocksize=VAD_BLOCK) as stream:
            self.get_logger().info('麦克风已开（VAD 自动断句），请说短指令，如"左转九十度"')
            while rclpy.ok():
                data, _ = stream.read(VAD_BLOCK)
                self.vad.accept_waveform(data[:, 0])

                if self.vad.is_speech_detected() and not self.in_speech:
                    self.in_speech = True
                    self.get_logger().info('检测到语音 ...')

                if not self.vad.empty():
                    segment = np.asarray(self.vad.front.samples, dtype='float32')
                    t_pop = time.time()      # 段落切出时刻（= 说完 + 0.5s VAD 等待）
                    self.vad.pop()
                    self.in_speech = False
                    # 冷却期内丢弃（同一句话的尾音可能被 VAD 切成第二段）
                    if time.time() - self.last_publish < self.cooldown:
                        continue
                    # 播报门控：机器人正在说话（或刚说完0.3s内）时丢弃本段——
                    # 这段音频是扬声器回声，不是用户指令
                    if time.time() < self.tts_mute_until:
                        self.get_logger().info('播报中，丢弃本段音频（回声门控）')
                        continue
                    self.recognize_and_publish(segment, t_pop)

    # ================= 模式2：回车录音（调试兜底）=================
    def manual_loop(self):
        while rclpy.ok():
            try:
                input(f'\n按回车开始录音（{self.manual_duration:.0f} 秒，请说短指令）...')
            except EOFError:
                return
            self.get_logger().info('录音中 ...')
            audio = sd.rec(int(self.manual_duration * SAMPLE_RATE),
                           samplerate=SAMPLE_RATE, channels=1, dtype='float32',
                           device=self.device)
            sd.wait()
            # manual 模式 t_pop=录音结束时刻（无 VAD 等待，采集器行内口径为"录完→车动"）
            self.recognize_and_publish(audio[:, 0], t_pop=time.time())


def main():
    rclpy.init()
    node = VoiceInputNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
