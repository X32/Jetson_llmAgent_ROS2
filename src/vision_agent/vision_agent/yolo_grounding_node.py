"""E9-D: YOLO grounding → /detected_objects（E5 坐标链起点的快眼睛·替代 VLM 8.3s 慢推理）

与 grounding_node.py（VLM）实现同一 Grounding.srv 契约、同一服务名 → orchestrator/
e5_act_node/coord_check 零改动，切换 = 换启动节点（或 remap 做 A/B）。

路由（双 session 常驻，按目标词分发）：
  方块/立方体/cube → 自训 lift_cube 模型（E9-B，仿真自动标注训成）
  杯子/cup → COCO#41   球/ball → COCO#32   碗/bowl → COCO#45（yolo26n COCO 原模型）
grade='YOLO'（门控只排 C2 直通）、confidence=真概率（区别于 VLM 的格式规整度分）、
label 回填请求词。检出 0 个 → 空 objects + error='no detection'。
"""
import json
import os
import time

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from my_package.msg import DetectedObject, DetectedObjects
from my_package.srv import Grounding
from vision_agent.yolo_onnx import YoloOnnx

CUBE_MODEL = '/mnt/nvme01/workplace/yolo/runs/lift_cube/v1/weights/best.onnx'
COCO_MODEL = '/mnt/nvme01/workplace/yolo/yolo26n.onnx'

# 目标词 → (用哪个模型, COCO 类 id 或 None=cube 模型全部, 置信门)
ROUTES = [
    (('方块', '立方体', 'cube'), 'cube', None, 0.25),
    (('杯子', 'cup'), 'coco', 41, 0.25),
    (('球', 'ball'), 'coco', 32, 0.25),
    (('碗', 'bowl'), 'coco', 45, 0.25),
]


def route(target):
    t = target.lower()
    for keys, backend, cls, thr in ROUTES:
        if any(k in t for k in keys):
            return backend, cls, thr
    return None, None, None


class YoloGroundingNode(Node):
    def __init__(self):
        super().__init__('yolo_grounding')
        self.declare_parameter('cube_model', CUBE_MODEL)
        self.declare_parameter('coco_model', COCO_MODEL)
        self.declare_parameter('conf', 0.25)
        self.declare_parameter('save_debug', True)

        self.cube = YoloOnnx(self.get_parameter('cube_model').value)
        self.coco = YoloOnnx(self.get_parameter('coco_model').value)
        self.pub = self.create_publisher(DetectedObjects, 'detected_objects', 10)
        self.diag = self.create_publisher(String, 'latency_diag', 10)
        self.srv = self.create_service(Grounding, 'grounding', self.on_request)
        self.get_logger().info('yolo_grounding 就绪（cube+coco 双 session）')

    def on_request(self, req, resp):
        import cv2
        target, img_path = req.target.strip(), req.image_path.strip()
        self.get_logger().info(f'[yolo-grounding] target={target!r} img={img_path}')
        if not os.path.isfile(img_path):
            resp.error = f'图片不存在: {img_path}'
            return resp
        backend, cls, thr = route(target)
        if backend is None:
            resp.error = f'不认识的目标词 {target!r}（支持：方块/杯子/球/碗）'
            return resp

        img = cv2.imread(img_path)
        t0 = time.perf_counter()
        det = (self.cube if backend == 'cube' else self.coco)(img, thr, 0.45)
        ms = (time.perf_counter() - t0) * 1000.0
        if backend == 'coco':                       # 只留路由到的类
            keep = det['cls'] == cls
            det = {k: v[keep] for k, v in det.items()}

        msg = DetectedObjects()
        msg.header.stamp = self.get_clock().now().to_msg()
        for (x1, y1, x2, y2), c in zip(det['xyxy'], det['conf']):
            # 不 round()——int 传 float64 字段会被 rclpy 拒掉（坑位#13，同 VLM 节点）
            msg.objects.append(DetectedObject(
                label=target, grade='YOLO', confidence=float(c),
                x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2)))
        resp.objects = msg.objects
        resp.latency_ms = ms
        if not msg.objects:
            resp.error = 'no detection'
        self.pub.publish(msg)
        self.diag.publish(String(data=json.dumps(
            {'node': 'yolo_grounding', 'yolo_ms': round(ms), 'n_objects': len(msg.objects)},
            ensure_ascii=False)))
        self.get_logger().info(f'{len(msg.objects)} 个目标 {ms:.1f}ms（VLM 对照 8280ms）')
        if self.get_parameter('save_debug').value and msg.objects:
            self.save_debug(img_path, msg.objects)
        return resp

    def save_debug(self, img_path, objects):
        import cv2
        img = cv2.imread(img_path)
        for o in objects:
            cv2.rectangle(img, (int(o.x1), int(o.y1)), (int(o.x2), int(o.y2)), (0, 255, 0), 2)
        out = os.path.join('/tmp', 'yolo_grounding_' + os.path.basename(img_path))
        cv2.imwrite(out, img)
        self.get_logger().info(f'调试图: {out}')


def main(args=None):
    rclpy.init(args=args)
    node = YoloGroundingNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
