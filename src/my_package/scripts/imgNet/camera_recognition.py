#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
摄像头实时图像识别脚本
使用 ONNX Runtime 部署 ImageNet 预训练模型
支持中文标签显示
"""

import os
import cv2
import numpy as np
import pandas as pd
import time
import torch
import torch.nn.functional as F
from torchvision import transforms
import onnxruntime
from PIL import Image, ImageFont, ImageDraw

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
        self.font = ImageFont.truetype(self.font_path, 32)

        # 加载ONNX模型
        print(f"加载ONNX模型: {self.model_path}")
        self.ort_session = onnxruntime.InferenceSession(self.model_path)

        # 加载ImageNet标签
        print(f"加载ImageNet标签: {self.labels_path}")
        self.idx_to_labels = self._load_labels()

        # 设置图像预处理
        self.test_transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(256),
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
            font_url = "https://zihao-openmmlab.obs.cn-east-3.myhuaweicloud.com/20220716-mmclassification/dataset/SimHei.ttf"

            try:
                import urllib.request
                urllib.request.urlretrieve(font_url, self.font_path)
                print(f"字体文件已下载到: {self.font_path}")
            except Exception as e:
                print(f"下载字体失败: {e}")
                print("请手动下载SimHei.ttf字体文件")

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

        # BGR转RGB
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)

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
        top_n = torch.topk(pred_softmax, top_n)
        pred_ids = top_n[1].cpu().detach().numpy().squeeze()
        confs = top_n[0].cpu().detach().numpy().squeeze()

        # 在图像上绘制识别结果
        draw = ImageDraw.Draw(img_pil)
        for i in range(len(confs)):
            pred_class = self.idx_to_labels.get(pred_ids[i], f"Class_{pred_ids[i]}")
            text = '{:<15} {:>.3f}'.format(pred_class, confs[i])
            draw.text((50, 100 + 50 * i), text, font=self.font, fill=(255, 0, 0, 1))

        # 转回BGR格式
        img_rgb = np.array(img_pil)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

        # 计算并显示FPS
        end_time = time.time()
        fps = 1 / (end_time - start_time)
        cv2.putText(img_bgr, f'FPS  {int(fps)}', (50, 80),
                   cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 0, 255), 4, cv2.LINE_AA)

        return img_bgr

    def run_camera(self, camera_id=0, window_name='实时识别', exit_keys=['q', 27]):
        """
        运行摄像头实时识别

        参数:
            camera_id: 摄像头设备ID（默认0）
            window_name: 显示窗口名称
            exit_keys: 退出按键列表，['q', 27]表示q键或ESC键
        """
        print(f"启动摄像头 (设备ID: {camera_id})")
        print(f"按 {'/'.join(map(str, exit_keys))} 键退出")

        # 打开摄像头
        cap = cv2.VideoCapture(camera_id)

        if not cap.isOpened():
            print(f"无法打开摄像头 (设备ID: {camera_id})")
            return

        print("摄像头已启动，开始实时识别...")

        try:
            while cap.isOpened():
                # 读取帧
                success, frame = cap.read()

                if not success:
                    print("无法获取摄像头画面，退出")
                    break

                # 处理帧并显示识别结果
                processed_frame = self.process_frame(frame)
                cv2.imshow(window_name, processed_frame)

                # 检测退出键
                key = cv2.waitKey(60)
                if key in exit_keys:
                    print(f"检测到退出键，停止识别")
                    break

        except KeyboardInterrupt:
            print("用户中断，停止识别")
        finally:
            # 清理资源
            cap.release()
            cv2.destroyAllWindows()
            print("摄像头已关闭")

def main():
    """主函数"""
    print("=" * 50)
    print("摄像头实时图像识别系统")
    print("=" * 50)

    # 检查必要文件是否存在
    model_path = 'resnet18_imagenet.onnx'
    labels_path = 'imagenet_class_index.csv'

    if not os.path.exists(model_path):
        print(f"错误：模型文件不存在 - {model_path}")
        print("请确保ONNX模型文件在当前目录")
        return

    if not os.path.exists(labels_path):
        print(f"错误：标签文件不存在 - {labels_path}")
        print("请确保ImageNet标签文件在当前目录")
        return

    # 创建识别系统实例
    recognition_system = CameraRecognition(
        model_path=model_path,
        labels_path=labels_path
    )

    # 启动摄像头实时识别
    recognition_system.run_camera(camera_id=0)

    print("程序结束")

if __name__ == "__main__":
    main()