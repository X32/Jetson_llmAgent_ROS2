#!/usr/bin/env python3
"""Day6 大脑核心，Day7 原样移植（已在 Day6 10/10 验证）。改动仅一处：config 路径由调用方传入。"""
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
            {"role": "system", "content": """你是一个机器人控制助手。你的任务是理解用户的指令并调用相应的工具来控制机器人。

重要规则：
1. 对于所有动作指令，你必须调用对应的工具函数，不要只回答文字
2. 中文数字映射：九十=90，一百八十=180，三十六=36，四十五=45，一百二十=120
3. 指令示例：
   - "向前走1米" → move_forward(distance=1)
   - "左转90度" → turn_left(angle=90)
   - "右转180度" → turn_right(angle=180)
   - "左转九十度" → turn_left(angle=90)
   - "停止" → stop()
4. 如果无法理解指令或指令超出机器人能力范围，可以解释但不调用工具

可用工具：move_forward, turn_left, turn_right, stop, query_sensor"""}
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
                stream=False
            )

            message = response['message']

            # 检查是否有 Function Calling
            if message.get('tool_calls'):
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

                result = {
                    "status": "success",
                    "action": function_name,
                    "parameters": arguments,
                    "user_input": user_input
                }

                # 关键：多轮 FC 的历史必须存"原始 assistant 消息（含 tool_calls）
                # + role=tool 的执行结果"两条——只存文字摘要，下一轮模型会"失忆"
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
                text_content = message.get('content', '').strip()
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
