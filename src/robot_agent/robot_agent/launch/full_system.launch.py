"""
Day12 一键启动：智能 + 语音全链路（仿真世界另起 robot_bringup）
= llm_agent + robot_controller + state_query + voice_input + tts_node

用法：
  # 标准演示（仿真终端之外只需这一条）
  ros2 launch robot_agent full_system.launch.py

  # 纯文字调试（不起麦克风/ASR，用 ros2 topic pub 发 /voice_text）
  ros2 launch robot_agent full_system.launch.py enable_voice:=false

  # 关闭 TTS 播报（无声调试，回声门控随之不生效）
  ros2 launch robot_agent full_system.launch.py enable_tts:=false

  # llama.cpp 后端（Jetson 部署形态；PC 默认 Ollama 不用开）
  ros2 launch robot_agent full_system.launch.py backend:=llamacpp

  # 模型路径不在 ~/models 时覆盖默认值
  ros2 launch robot_agent full_system.launch.py asr_model_dir:=/data/models/asr/sense-voice

设计说明：
  - 模型路径全部 launch 参数注入，节点代码零硬编码（实验8/10 的参数化模式延续）
  - LLAMACPP 是环境变量开关（llm_agent_node.py 读 os.environ），
    backend 参数在 launch 里转成 additional_env 传给节点进程
  - 全部 output='screen'：日志直出终端，排错不抓瞎
  - Ctrl+C 退出安全：controller 的 SIGINT 零速兜底（实验7）保证关 launch 车即停
"""
import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

# 模型默认根目录：换机器只需覆盖对应 launch 参数
DEFAULT_MODELS_ROOT = os.path.expanduser('~/models')


def generate_launch_description():
    # ---- launch 参数（全部可在命令行覆盖）----
    enable_voice = LaunchConfiguration('enable_voice')   # 麦克风 + ASR
    enable_tts = LaunchConfiguration('enable_tts')       # 扬声器播报
    backend = LaunchConfiguration('backend')             # ollama / llamacpp

    asr_model_dir = LaunchConfiguration('asr_model_dir')     # SenseVoice 目录
    vad_model = LaunchConfiguration('vad_model')             # silero VAD onnx
    tts_model_dir = LaunchConfiguration('tts_model_dir')     # matcha 目录
    tts_speed = LaunchConfiguration('tts_speed')             # 播报语速

    return LaunchDescription([
        # ---- 参数声明（默认值 = 实测可用的路径）----
        DeclareLaunchArgument(
            'enable_voice', default_value='true',
            description='是否启动麦克风+ASR（false=纯文字调试模式）'),
        DeclareLaunchArgument(
            'enable_tts', default_value='true',
            description='是否启动TTS播报（false=无声调试）'),
        DeclareLaunchArgument(
            'backend', default_value='ollama',
            description='LLM后端：ollama（PC默认）/ llamacpp（Jetson形态）'),
        DeclareLaunchArgument(
            'asr_model_dir',
            default_value=os.path.join(DEFAULT_MODELS_ROOT, 'asr', 'sense-voice'),
            description='SenseVoice 模型目录（含 model.int8.onnx / tokens.txt）'),
        DeclareLaunchArgument(
            'vad_model',
            default_value=os.path.join(DEFAULT_MODELS_ROOT, 'asr', 'silero_vad.onnx'),
            description='silero VAD 模型路径'),
        DeclareLaunchArgument(
            'tts_model_dir',
            default_value=os.path.join(DEFAULT_MODELS_ROOT, 'tts', 'matcha'),
            description='matcha TTS 模型目录（含声学模型/vocoder/词典）'),
        DeclareLaunchArgument(
            'tts_speed', default_value='1.0',
            description='TTS 播报语速'),

        # ================= 大脑 + 肌肉（常驻，不受开关影响）=================
        Node(
            package='robot_agent',
            executable='llm_agent',
            name='llm_agent',
            output='screen',
            # backend 参数转环境变量：llm_agent_node.py 读 os.environ['LLAMACPP']
            # 注：非 '1' 的任何值都走 Ollama 分支，与节点现有判断一致
            additional_env={'LLAMACPP': LaunchConfiguration('backend')},
            parameters=[{
                # llm_config 路径由节点内部从 share 目录解析（跟包安装）
                'use_sim_time': False,
            }],
        ),
        Node(
            package='robot_agent',
            executable='robot_controller',
            name='robot_controller',
            output='screen',
            parameters=[{'use_sim_time': False}],
        ),
        Node(
            package='state_query',
            executable='state_query_node',
            name='state_query',
            output='screen',
            parameters=[{'use_sim_time': False}],
        ),

        # ================= 耳朵：麦克风 + VAD + ASR =================
        Node(
            package='voice_input',
            executable='voice_input_node',
            name='voice_input',
            output='screen',
            condition=IfCondition(enable_voice),
            parameters=[{
                'model_dir': asr_model_dir,
                'vad_model': vad_model,
                'mode': 'vad',   # 连续听音自动断句（manual 调试用 ros2 run 单起）
                'use_sim_time': False,
            }],
        ),

        # ================= 嘴巴：matcha TTS（含 /tts_state 回声门控）=================
        Node(
            package='voice_output',
            executable='tts_node',
            name='tts_node',
            output='screen',
            condition=IfCondition(enable_tts),
            parameters=[{
                'model_dir': tts_model_dir,
                'speed': tts_speed,
                'use_sim_time': False,
            }],
        ),
    ])
