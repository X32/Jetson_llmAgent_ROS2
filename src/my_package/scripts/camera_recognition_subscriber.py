#!/usr/bin/env python3
"""
ROS2 Python摄像头识别订阅者节点
接收 /camera/image_raw 话题，进行图像识别并显示结果
"""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import numpy as np
import time
import os

# 导入图像识别相关模块
try:
    import onnxruntime
    import torch
    import torch.nn.functional as F
    from torchvision import transforms
    from PIL import Image as PILImage, ImageFont, ImageDraw
    import pandas as pd
    RECOGNITION_AVAILABLE = True
except ImportError as e:
    print(f"警告: 图像识别依赖未安装 - {e}")
    print("请安装: pip3 install onnxruntime torch torchvision pandas")
    RECOGNITION_AVAILABLE = False

class CameraRecognitionSubscriber(Node):
    def __init__(self, enable_recognition=True):
        super().__init__('camera_recognition_subscriber')

        # 创建CV Bridge对象
        self.bridge = CvBridge()

        # 统计信息
        self.frame_count = 0
        self.start_time = time.time()
        self.last_fps = 0.0
        self.last_print_time = time.time()

        # 识别系统
        self.enable_recognition = enable_recognition
        self.recognition_system = None

        if self.enable_recognition and RECOGNITION_AVAILABLE:
            self.init_recognition_system()
        elif self.enable_recognition:
            self.get_logger().warn('图像识别依赖未安装，将只显示原始图像')

        # 创建图像订阅者
        self.subscription = self.create_subscription(
            Image,
            '/camera/image_raw',
            self.image_callback,
            10
        )

        self.get_logger().info('Python摄像头识别订阅者节点已启动')
        self.get_logger().info('订阅话题: /camera/image_raw')
        if self.enable_recognition:
            self.get_logger().info('图像识别: 已启用')
        else:
            self.get_logger().info('图像识别: 已禁用')

        # 创建定时器用于统计信息
        self.timer = self.create_timer(5.0, self.print_stats)

    def init_recognition_system(self):
        """初始化图像识别系统"""
        try:
            # 查找模型和标签文件（支持多种路径）
            possible_paths = [
                # 相对于安装路径
                '../share/my_package/imgNet/',
                # 相对于工作目录
                'src/my_package/scripts/imgNet/',
                # 当前目录
                './',
            ]

            model_path = None
            labels_path = None
            font_path = None

            for base_path in possible_paths:
                test_model = os.path.join(base_path, 'resnet18_imagenet.onnx')
                test_labels = os.path.join(base_path, 'imagenet_class_index.csv')
                test_font = os.path.join(base_path, 'SimHei.ttf')

                if os.path.exists(test_model):
                    model_path = test_model
                    labels_path = test_labels
                    font_path = test_font
                    break

            if not model_path:
                raise FileNotFoundError("无法找到识别模型文件")

            self.get_logger().info(f'使用模型文件: {model_path}')
            self.get_logger().info(f'使用标签文件: {labels_path}')

            # 创建识别系统
            self.recognition_system = CameraRecognition(
                model_path=model_path,
                labels_path=labels_path,
                font_path=font_path
            )

            self.get_logger().info('图像识别系统初始化成功')

        except Exception as e:
            self.get_logger().error(f'图像识别系统初始化失败: {e}')
            self.enable_recognition = False

    def image_callback(self, msg):
        """接收到图像消息时的回调函数"""
        try:
            # 将ROS图像消息转换为OpenCV格式
            cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            # 进行图像识别（如果启用），并将识别结果绘制到图像上
            if self.enable_recognition and self.recognition_system:
                display_image = self.recognition_system.process_frame(cv_image, top_n=3)
                # 输出识别结果到终端（每30帧输出一次）
                if hasattr(self.recognition_system, 'last_predictions'):
                    predictions = self.recognition_system.last_predictions
                    if predictions and (self.frame_count % 30 == 0):
                        self.get_logger().info(f'🔍 识别结果: {" | ".join(predictions[:2])}')
            else:
                display_image = self.add_basic_info(cv_image)
                if self.frame_count == 0:
                    self.get_logger().info('📷 接收图像帧 (识别已禁用)')

            # 在窗口中显示带识别结果的图像
            cv2.imshow('ROS2 Camera Recognition', display_image)
            cv2.waitKey(1)

            # 更新统计信息
            self.frame_count += 1
            current_time = time.time()

            # 每30帧更新一次FPS
            if self.frame_count % 30 == 0:
                elapsed = current_time - self.last_print_time
                if elapsed > 0:
                    self.last_fps = 30 / elapsed
                self.last_print_time = current_time

        except Exception as e:
            self.get_logger().error(f'处理图像时出错: {str(e)}')

    def add_basic_info(self, image):
        """添加基本统计信息到图像上"""
        if self.frame_count > 0:
            elapsed = time.time() - self.start_time
            current_fps = self.frame_count / elapsed if elapsed > 0 else 0
        else:
            current_fps = self.last_fps

        # 添加FPS和帧数信息
        fps_text = f'FPS: {int(current_fps)}'
        frame_text = f'Frame: {self.frame_count}'
        mode_text = '模式: 显示' if not self.enable_recognition else '模式: 识别'

        cv2.putText(image, fps_text, (15, 35),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(image, frame_text, (15, 65),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.putText(image, mode_text, (15, 95),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        return image

    def print_stats(self):
        """打印统计信息"""
        elapsed = time.time() - self.start_time
        avg_fps = self.frame_count / elapsed if elapsed > 0 else 0

        self.get_logger().info(f'=== 统计信息 ===')
        self.get_logger().info(f'总帧数: {self.frame_count}')
        self.get_logger().info(f'当前FPS: {self.last_fps:.1f}')
        self.get_logger().info(f'平均FPS: {avg_fps:.1f}')
        self.get_logger().info(f'运行时间: {elapsed:.1f}秒')
        self.get_logger().info(f'识别模式: {"启用" if self.enable_recognition else "禁用"}')

        # 检查发布者状态
        if self.frame_count > 0 and self.last_fps > 0:
            self.get_logger().info('发布者状态: 活跃')
        else:
            self.get_logger().warn('发布者状态: 可能在等待数据')

    def __del__(self):
        """析构函数，清理资源"""
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

# 复用原始的CameraRecognition类
class CameraRecognition:
    """摄像头实时图像识别类"""

    def __init__(self, model_path='resnet18_imagenet.onnx',
                 labels_path='imagenet_class_index.csv',
                 font_path='SimHei.ttf'):
        """
        初始化识别系统

        参数:
            model_path: ONNX模型文件路径
            labels_path: ImageNet标签文件路径
            font_path: 中文字体文件路径
        """
        self.model_path = model_path
        self.labels_path = labels_path
        self.font_path = font_path

        # 下载中文字体（如果不存在）
        self._download_font_if_needed()

        # 加载中文字体
        self.font = ImageFont.truetype(self.font_path, 28)

        # 加载ONNX模型
        print(f"加载ONNX模型: {self.model_path}")
        self.ort_session = onnxruntime.InferenceSession(self.model_path)

        # 加载ImageNet标签
        print(f"加载ImageNet标签: {self.labels_path}")
        self.idx_to_labels = self._load_labels()

        # 保存最后的预测结果（供节点使用）
        self.last_predictions = None
        self.last_inference_time = 0.0

        # 设置图像预处理 - 修改为256x256以匹配ONNX模型输入要求
        self.test_transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(256),  # 修改为256以匹配模型输入
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

        print("识别系统初始化完成！")

    def _download_font_if_needed(self):
        """下载中文字体文件（如果不存在）"""
        if not os.path.exists(self.font_path):
            print("下载中文字体文件...")
            font_url = "https://zihao.openmmlab.com/mmclassification/dataset/SimHei.ttf"

            try:
                import urllib.request
                urllib.request.urlretrieve(font_url, self.font_path)
                print(f"字体文件已下载到: {self.font_path}")
            except Exception as e:
                print(f"下载字体失败: {e}")
                # 使用默认字体
                self.font_path = None

    def _load_labels(self):
        """加载ImageNet 1000类标签"""
        try:
            df = pd.read_csv(self.labels_path)
            idx_to_labels = {}
            for idx, row in df.iterrows():
                idx_to_labels[row['ID']] = row['Chinese']
            return idx_to_labels
        except Exception as e:
            print(f"加载标签文件失败: {e}")
            return {}

    def process_frame(self, img_bgr, top_n=5):
        """
        处理单帧图像并进行识别

        参数:
            img_bgr: BGR格式的输入图像
            top_n: 显示前n个预测结果

        返回:
            处理后的BGR图像，带有识别结果标注
        """
        start_time = time.time()

        try:
            # BGR转RGB
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            img_pil = PILImage.fromarray(img_rgb)

            # 预处理
            input_img = self.test_transform(img_pil)
            input_tensor = input_img.unsqueeze(0).numpy()

            # ONNX Runtime推理
            ort_inputs = {'input': input_tensor}
            pred_logits = self.ort_session.run(['output'], ort_inputs)[0]
            pred_logits = torch.tensor(pred_logits)

            # Softmax
            pred_softmax = F.softmax(pred_logits, dim=1)

            # 获取top-n预测结果
            top_n_result = torch.topk(pred_softmax, top_n)
            pred_ids = top_n_result[1].cpu().detach().numpy().squeeze()
            confs = top_n_result[0].cpu().detach().numpy().squeeze()

            # 保存预测结果（供ROS2节点使用）
            predictions = []
            for i in range(len(confs)):
                pred_class = self.idx_to_labels.get(pred_ids[i], f"Class_{pred_ids[i]}")
                predictions.append(f'{pred_class}: {confs[i]:.3f}')
            self.last_predictions = predictions

            # 在图像上绘制识别结果
            draw = ImageDraw.Draw(img_pil)
            for i in range(len(confs)):
                pred_class = self.idx_to_labels.get(pred_ids[i], f"Class_{pred_ids[i]}")
                text = f'{pred_class}: {confs[i]:.3f}'
                draw.text((10, 100 + 35 * i), text, font=self.font, fill=(255, 0, 0, 255))

            # 转回BGR格式
            img_rgb = np.array(img_pil)
            img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

            # 计算并显示FPS
            end_time = time.time()
            fps = 1 / (end_time - start_time)

            # 添加FPS和识别信息
            cv2.putText(img_bgr, f'FPS: {int(fps)}', (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 0, 255), 2)
            # cv2.putText(img_bgr, 'ImageNet识别', (10, 65),
            #            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            return img_bgr

        except Exception as e:
            print(f"识别过程出错: {e}")
            # 返回原始图像加错误提示
            cv2.putText(img_bgr, '识别失败', (10, 100),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            return img_bgr

def main(args=None):
    rclpy.init(args=args)

    # 允许用户选择是否启用识别
    enable_recognition = True

    # 如果识别依赖不可用，自动禁用识别
    if not RECOGNITION_AVAILABLE:
        print("图像识别依赖未安装，将只显示原始图像")
        enable_recognition = False

    node = CameraRecognitionSubscriber(enable_recognition=enable_recognition)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('收到中断信号，正在关闭节点...')
    finally:
        node.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()