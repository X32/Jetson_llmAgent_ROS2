# E1: grounding 单目标框（像素坐标·原图坐标系）
string label          # 目标名（<ref> 提取，缺省回填请求词）
float64 x1            # 像素坐标·左上
float64 y1
float64 x2            # 像素坐标·右下
float64 y2            # （手册6.1原稿漏了这行——bbox 少底边坐标，节点构造时 AssertionError → 服务静默挂起）
float64 confidence    # 解析格式规整度 A=1.0/A2=0.9/A3=0.8/B=0.6/C=0.4/C2=0.3（非模型概率，见手册2.3）
string grade          # 解析命中级别原值（可追溯）
