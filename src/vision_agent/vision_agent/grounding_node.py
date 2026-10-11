"""E1: Qwen2.5-VL grounding → /detected_objects（E5 坐标链起点·慢思考眼睛）"""
import base64
import json
import os
import time
import urllib.request

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from my_package.msg import DetectedObject, DetectedObjects   # 手册漏了 DetectedObject 的 import，实测补上
from my_package.srv import Grounding
from vision_agent.parse_grounding import CONF, parse

PROMPT_TMPL = ('请找出图中的{target}，只输出边界框坐标，'
               '格式：<ref>{target}</ref><box>(x1,y1),(x2,y2)</box>，'
               '坐标为0-1000归一化数值。')


class GroundingNode(Node):
    def __init__(self):
        super().__init__('vision_grounding')
        self.declare_parameter('server_url', 'http://localhost:8080')
        self.declare_parameter('temperature', 0.1)
        self.declare_parameter('max_tokens', 512)
        self.declare_parameter('save_debug', True)
        self.declare_parameter('resize', 768)   # 送检长边：与 Step3 验证过的协议一致（大载荷实测会打崩 llama-server）

        self.pub = self.create_publisher(DetectedObjects, 'detected_objects', 10)
        self.diag = self.create_publisher(String, 'latency_diag', 10)
        # 慢推理独占一个回调组 + 多线程 executor：2.5s HTTP 不饿死其他回调（Day9 教训）
        self.srv = self.create_service(
            Grounding, 'grounding', self.on_request,
            callback_group=MutuallyExclusiveCallbackGroup())

    # ---- HTTP：与 tools/arm/test_vlm.py 同款（长边 resize + JPEG 重编码），零第三方依赖 ----
    def call_vlm(self, image_path, target):
        import io

        from PIL import Image
        img = Image.open(image_path).convert('RGB')
        w0, h0 = img.size
        scale = int(self.get_parameter('resize').value) / max(w0, h0)
        sent = img.resize((round(w0 * scale), round(h0 * scale)))
        buf = io.BytesIO()
        sent.save(buf, 'JPEG')
        b64 = base64.b64encode(buf.getvalue()).decode()
        payload = {
            'messages': [{'role': 'user', 'content': [
                {'type': 'image_url',
                 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
                {'type': 'text', 'text': PROMPT_TMPL.format(target=target)}]}],
            'max_tokens': int(self.get_parameter('max_tokens').value),
            'temperature': float(self.get_parameter('temperature').value),
        }
        req = urllib.request.Request(
            f"{self.get_parameter('server_url').value.rstrip('/')}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={'Content-Type': 'application/json'}, method='POST')
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read())
        # 返回送检图尺寸——V9：模型坐标是送检图像素，parse 的锚点必须是它而非原图
        return out['choices'][0]['message']['content'], (time.time() - t0) * 1000.0, sent.size

    def on_request(self, req, resp):
        target, img_path = req.target.strip(), req.image_path.strip()
        self.get_logger().info(f'[grounding] target={target!r} img={img_path}')
        if not os.path.isfile(img_path):
            resp.error = f'图片不存在: {img_path}'
            return resp
        try:
            content, ms, (sw, sh) = self.call_vlm(img_path, target)
        except Exception as e:
            resp.error = f'VLM 调用失败: {e}'
            return resp
        self.get_logger().info(f'[VLM原始输出] {content!r}')   # 漂移审计永远留底

        from PIL import Image
        w, h = Image.open(img_path).size
        msg = DetectedObjects()
        msg.header.stamp = self.get_clock().now().to_msg()
        # V9 换算链：模型像素(送检图) --parse(sw,sh)--> 0-1000 归一化 --> ×原图尺寸
        # 锚点必须送检图尺寸；输出坐标统一原图像素（E5 下游直接可用）
        for grade, label, x1, y1, x2, y2 in parse(content, sw, sh):
            # 不能 round()——int 传 float64 字段会被 rclpy 类型断言拒掉（坑位#13）
            msg.objects.append(DetectedObject(
                label=label or target, grade=grade, confidence=CONF[grade],
                x1=x1 / 1000 * w, y1=y1 / 1000 * h,
                x2=x2 / 1000 * w, y2=y2 / 1000 * h))
        resp.objects = msg.objects
        resp.latency_ms = ms
        self.pub.publish(msg)
        self.diag.publish(String(data=json.dumps(
            {'node': 'vision_grounding', 'vlm_ms': round(ms),
             'n_objects': len(msg.objects)}, ensure_ascii=False)))
        if self.get_parameter('save_debug').value and msg.objects:
            self.save_debug(img_path, msg.objects)
        return resp

    def save_debug(self, img_path, objects):
        from PIL import Image, ImageDraw
        img = Image.open(img_path).convert('RGB')
        d = ImageDraw.Draw(img)
        for o in objects:
            d.rectangle([o.x1, o.y1, o.x2, o.y2], outline=(255, 0, 0), width=3)
        out = os.path.join('/tmp', 'grounding_' + os.path.basename(img_path))
        img.save(out)
        self.get_logger().info(f'调试图: {out}')


def main(args=None):
    rclpy.init(args=args)
    node = GroundingNode()
    executor = MultiThreadedExecutor()          # 慢推理不堵回调的关键
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
