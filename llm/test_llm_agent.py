#!/usr/bin/env python3
"""
Day6 LLM Agent 测试脚本：中文指令 → Ollama Function Calling → 结构化 JSON
核心验证：Function Calling 稳定触发 + 对话记忆 + 异常拒绝
"""
import json
import ollama

class LLMAgent:
    def __init__(self, config_path="llm_config.json"):
        # 加载配置：tools（Function Calling）+ options（生成参数）
        with open(config_path) as f:
            config = json.load(f)
        self.model = config.get("model", "qwen2.5:3b")
        self.tools_config = config.get("tools", [])
        # 关键：temperature/num_ctx 必须通过 options 传给 ollama.chat，
        # 否则用 Ollama 默认值 temperature=0.8，"低温度保稳定"就成空谈了
        self.gen_options = config.get("options", {})
        
        # 对话历史（支持"再走远一点"这种指代）
        # 注意：喂给模型的是 self.messages 本体，必须限长，否则 token 超限
        self.max_turns = 20  # system 之外最多保留 20 轮（40 条消息）
        self.messages = [
            {"role": "system", "content": "你是一个机器人控制助手，只能使用提供的工具输出执行动作的指令。"}
        ]
        
        # 拒绝规则（异常指令关键词）——第一层防护，在调用 LLM 之前拦截
        self.reject_rules = ["飞", "爬", "跳", "月球", "火星", "天花板", "楼顶"]
    
    def trimmed_messages(self):
        """system 提示词永远保留，其余只取最近 max_turns 轮"""
        return [self.messages[0]] + self.messages[-(self.max_turns * 2):]
    
    def validate_params(self, action, params):
        """参数合法性校验——schema 里的 minimum 只是给 LLM 的提示，Ollama 不校验"""
        if action == "move_forward":
            d = params.get("distance")
            if not isinstance(d, (int, float)) or not (0.05 <= d <= 10.0):
                return f"distance 非法: {d}（应在 0.05~10 米）"
        if action in ("turn_left", "turn_right"):
            a = params.get("angle")
            if not isinstance(a, (int, float)) or not (1 <= a <= 360):
                return f"angle 非法: {a}（应在 1~360 度）"
        if action == "query_sensor":
            if params.get("type") not in ("lidar", "camera"):
                return f"type 非法: {params.get('type')}"
        return None

    def chat(self, user_input):
        """处理用户输入，返回 Function Calling 结果"""
        # 先检查拒绝规则
        for reject_keyword in self.reject_rules:
            if reject_keyword in user_input:
                return {
                    "status": "rejected",
                    "message": f"机器人不能{reject_keyword}，超出能力范围",
                    "user_input": user_input
                }
        
        # 用户输入加入历史
        self.messages.append({"role": "user", "content": user_input})
        
        try:
            # 调用 Ollama（带 Function Calling + options 生成参数）
            response = ollama.chat(
                model=self.model,
                messages=self.trimmed_messages(),
                tools=self.tools_config if self.tools_config else None,
                options=self.gen_options,
                stream=False  # 不用流式，简化代码
            )
            
            message = response['message']

            print("message : ",message)
            print("*" * 80)
            
            # 检查是否有 Function Calling
            if message.get('tool_calls'):
                # Function Calling 触发成功
                tool_call = message['tool_calls'][0]
                function_name = tool_call['function']['name']
                arguments = tool_call['function']['arguments']
                # 兼容旧版 ollama-python：arguments 可能是 JSON 字符串
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                
                # 参数校验（LLM 的输出也不能全信）
                err = self.validate_params(function_name, arguments)
                if err:
                    return {
                        "status": "invalid_param",
                        "message": err,
                        "user_input": user_input
                    }
                
                # 构造标准化输出（为 Day7 ROS2 接口预留）
                result = {
                    "status": "success",
                    "action": function_name,
                    "parameters": arguments,
                    "user_input": user_input
                }
                print("result : ",result)
                print("*" * 80)
                # 关键：多轮 Function Calling 的历史必须存"原始 assistant 消息
                # （含 tool_calls）+ role="tool" 的执行结果"两条——只存一段文字摘要，
                # 下一轮模型会"失忆"，"再走远一点"这类指代就接不上了
                self.messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": message['tool_calls'],
                })
                self.messages.append({
                    "role": "tool",
                    "name": function_name,
                    "content": json.dumps({"executed": True, "args": arguments}, ensure_ascii=False),
                })
                
                return result
                
            else:
                # 没有触发 Function Calling，返回文本内容
                text_content = message.get('content', '').strip()
                
                # 加入历史
                self.messages.append({"role": "assistant", "content": text_content})
                
                return {
                    "status": "no_tool",
                    "message": "未识别为动作指令",
                    "llm_response": text_content,
                    "user_input": user_input
                }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"LLM 调用失败: {str(e)}",
                "user_input": user_input
            }

def test_instruction(agent, instruction):
    """测试单条指令：输入 → Function Calling → 结果打印"""
    print(f"\n{'='*60}")
    print(f"🎯 用户指令：{instruction}")
    print(f"{'='*60}")
    
    # LLM 处理
    result = agent.chat(instruction)
    
    # 根据不同状态打印结果（返回完整 result，统计时按 status 分类）
    if result["status"] == "success":
        action = result["action"]
        params = result["parameters"]
        params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else "(无)"
        print(f"✅ Function Calling 触发成功")
        print(f"   动作: {action}")
        print(f"   参数: {params_str}")
        return result
        
    elif result["status"] == "rejected":
        print(f"❌ 指令被拒绝")
        print(f"   原因: {result['message']}")
        return result
        
    elif result["status"] == "no_tool":
        print(f"⚠️  未触发 Function Calling")
        print(f"   LLM 回复: {result.get('llm_response', '无')[:100]}")
        return result
        
    else:  # invalid_param / error
        print(f"💥 发生错误")
        print(f"   信息: {result['message']}")
        return result

# 主测试
if __name__ == "__main__":
    print("🤖 Day6 LLM Agent Function Calling 测试")
    print("模型: qwen2.5:3b-instruct-q4_0")
    print("=" * 60)
    
    agent = LLMAgent()
    
    # 10 条测试指令（8 条合理 + 2 条不合理）
    test_cases = [
        "向前走 1.5 米",              # 合理 - move_forward
        "左转九十度",              # 合理 - 汉字数字（ASR 输出形态）→ turn_left(90)
        "向右转 45 度",             # 合理 - turn_right
        "再走远一点",                # 合理 - 对话记忆测试
        "停下",                      # 合理 - stop
        "前面有障碍物吗",          # 合理 - query_sensor(lidar)
        "看看相机画面",              # 合理 - query_sensor(camera)
        "左转 270 度",              # 合理 - 大角度测试
        "飞到月球上去看看",         # 不合理 - 拒绝测试
        "跳起来试试",               # 不合理 - 拒绝测试
    ]
    
    success_count = 0
    rejected_count = 0
    fail_count = 0
    
    for instruction in test_cases:
        result = test_instruction(agent, instruction)
        if result["status"] == "success":
            success_count += 1
        elif result["status"] == "rejected":
            rejected_count += 1
        else:
            fail_count += 1
    
    print(f"\n{'='*60}")
    print("📊 测试统计：")
    print(f"   ✅ Function Calling 成功: {success_count}/10")
    print(f"   ❌ 合理拒绝: {rejected_count}/10")  
    print(f"   💥 失败: {fail_count}/10")
    print(f"{'='*60}")
    
    print("\n🎯 验收标准：")
    print("   1. 合理指令 100% 触发 Function Calling (8/8 = ✅)")
    print("   2. 不合理指令 100% 被拒绝机制拦截 (2/2 = ✅)")  
    print("   3. 对话记忆生效 ('再走远一点' 能理解上下文)")
    print("   4. 所有输出格式符合动作原语集规范")
