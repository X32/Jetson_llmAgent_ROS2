#!/usr/bin/env python3
"""Day6 大脑核心，Day7 原样移植（已在 Day6 10/10 验证）。改动仅一处：config 路径由调用方传入。"""
import json
from collections import OrderedDict

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
5. 传感器查询类问题（有障碍物吗/离墙多远/走了多远/现在什么情况）必须调用 query_sensor
   获取真实数据后回答，禁止编造任何数值。示例：
   - "前面有障碍物吗" → query_sensor(type="lidar")
   - "离墙多远" → query_sensor(type="lidar")
   - "走了多远/走了多少米" → query_sensor(type="odom")
   - "现在周围什么情况" → query_sensor(type="all")
   注意：type 参数必填，只能取 lidar/odom/all。
   传感器数据是实时的，用户重复提问说明想要**此刻**的最新数据，
   上一轮的回答和工具结果都已过期——每次都必须重新调用 query_sensor
6. 拿到工具返回的数据后，用简短自然的中文回答（1-2句话），数值必须来自工具结果


可用工具：move_forward, turn_left, turn_right, stop, query_sensor"""}
        ]

        # 拒绝规则（异常指令关键词）——第一层防护，在调用 LLM 之前拦截
        self.reject_rules = ["飞", "爬", "跳", "月球", "火星", "天花板", "楼顶"]

        # ASR 同音错别字纠错表（SenseVoice 实测："左转"→"左传"）
        # 确定性替换：零延迟、零 token，比让 LLM 猜错别字可靠
        self.asr_fixes = {
            "左传": "左转",
            "右传": "右转",
            "钱进": "前进",
            "向钱": "向前",
        }

        # 指令缓存（LRU，仅动作类）：完全相同的动作指令直接复用上次的 FC 结果——
        # 零延迟、零 token，且绕开 3B 模型"重复指令当已执行"的 no_tool 坑
        # 不缓存的：感知查询（要的是"现在"的事实）、指代表达（"再走远一点"每次含义不同）
        self.cmd_cache = OrderedDict()          # text -> result dict（含 tool_calls）
        self.cmd_cache_max = 8
        self.cache_bypass_words = ("再", "又", "继续", "还", "刚才", "之前")

    def fix_asr_homophones(self, text):
        """ASR 后处理：领域同音词纠错 + 标点归一化（3B 模型对标点敏感）"""
        for wrong, right in self.asr_fixes.items():
            text = text.replace(wrong, right)
        # 去句末常见标点（"停止。"、"停下？"会被 3B 模型判错）
        if text.endswith(('。', '？', '！', '?', '!', '.', '~')):
            text = text[:-1]
        return text

    def _cacheable(self, text):
        """指代表达依赖上下文（"再走远一点"每次含义不同），不可缓存"""
        return not any(w in text for w in self.cache_bypass_words)

    def _cache_put(self, user_input, result, tool_calls):
        """FC 成功后写入 LRU 缓存。
        只缓存动作类（重复=再执行一次，FC 输出确定性高）；
        感知查询不缓存——"现在的情况"必须每次完整走 LLM + 真实服务"""
        if result.get('action') == 'query_sensor':
            return
        if not self._cacheable(user_input):
            return
        entry = dict(result)
        entry['tool_calls'] = tool_calls
        self.cmd_cache[user_input] = entry
        self.cmd_cache.move_to_end(user_input)
        while len(self.cmd_cache) > self.cmd_cache_max:
            self.cmd_cache.popitem(last=False)

    def _cache_hit(self, user_input):
        """缓存命中：直接返回上次结果，并回放历史（保证对话记忆一致）"""
        cached = self.cmd_cache.get(user_input)
        if cached is None:
            return None
        self.cmd_cache.move_to_end(user_input)
        # 历史照样记录 user + assistant(tool_calls)——模型记忆里这是"又执行了一次"
        self.messages.append({"role": "user", "content": user_input})
        self.messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": cached['tool_calls'],
        })
        if cached['action'] != 'query_sensor':
            # 动作类补执行回执；查询类的 tool 回执由 followup_tool_result 按真实数据补
            self.messages.append({
                "role": "tool",
                "name": cached['action'],
                "content": json.dumps({"executed": True, "args": cached['parameters']}, ensure_ascii=False),
            })
        out = dict(cached)
        out['cached'] = True
        return out

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
            if params.get("type") not in ("lidar", "odom", "all"):
                return f"type 非法: {params.get('type')}（应为 lidar/odom/all）"
        return None

    def chat(self, user_input):
        """处理用户输入，返回 Function Calling 结果"""
        # ASR 同音纠错（在拒绝规则和 LLM 之前）
        user_input = self.fix_asr_homophones(user_input)
        # 先检查拒绝规则
        for reject_keyword in self.reject_rules:
            if reject_keyword in user_input:
                return {
                    "status": "rejected",
                    "message": f"机器人不能{reject_keyword}，超出能力范围",
                    "user_input": user_input
                }

        # 重复指令：缓存命中直接返回（零 LLM 调用）
        if self._cacheable(user_input):
            hit = self._cache_hit(user_input)
            if hit is not None:
                return hit

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

                # Day9 实测坑（qwen2.5:3b）：
                # 1. 偶尔吐出带冒号的 key "type:"——先归一化，别把 intent 丢了
                # 2. 常丢 required 的 type——与其拒绝，不如兜底成 all（服务端本来就支持）
                if function_name == "query_sensor":
                    if "type" not in arguments and "type:" in arguments:
                        arguments["type"] = arguments.pop("type:")
                    if arguments.get("type") not in ("lidar", "odom", "all"):
                        arguments["type"] = "all"

                # 参数校验（LLM 的输出也不能全信）
                err = self.validate_params(function_name, arguments)
                if err:
                    # 回滚本条 user 消息：留着它会让历史出现"提问无回复"的断档，
                    # 下一轮模型容易跟着用纯文字回答（实测踩坑）
                    self.messages.pop()
                    return {
                        "status": "invalid_param",
                        "message": err,
                        "user_input": user_input
                    }

                # 先构建基础 result
                result = {
                    "status": "success",
                    "action": function_name,
                    "parameters": arguments,
                    "user_input": user_input
                }

                if function_name == "query_sensor":
                    # Day9：查询类工具由 llm_agent 真实执行后回填
                    # 必须立即追加 assistant 消息（含 tool_calls），否则历史里悬空的 user
                    # 消息会让下一轮格式错乱（实测：连续感知问题第二条必 no_tool）
                    self.messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": message['tool_calls'],
                    })
                    result["tool_calls"] = message["tool_calls"]
                    self._cache_put(user_input, result, message["tool_calls"])
                    return result

                # 动作类：维持 Day7 行为（假回执 + fire-and-forget）
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
                self._cache_put(user_input, result, message['tool_calls'])
                return result

            else:
                text_content = message.get('content', '').strip()
                # Day9 实测坑：上一轮刚做过感知问答后，3B 模型会模仿最近的
                # "纯文字回答"而跳过工具。疑似感知问题被文字回答 → nudge 重试一次。
                # 注意顺序：重试前不要把文字回答写进历史（写进去模型会认为
                # "已答过"，重试必然失败——实测踩坑）
                if self._looks_like_sensor_query(user_input):
                    retry = self._force_tool_retry(user_input)
                    if retry is not None:
                        return retry
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

    # 感知类问题关键词（用于 no_tool 时的兜底重试判断）
    SENSOR_QUERY_KEYWORDS = ("障碍", "多远", "距离", "周围", "什么情况", "里程", "走了多", "雷达")

    def _looks_like_sensor_query(self, text):
        return any(k in text for k in self.SENSOR_QUERY_KEYWORDS)

    def _force_tool_retry(self, user_input):
        """no_tool 兜底：追加提醒消息强推一次工具调用。
        成功返回 result dict；失败回滚提醒消息、返回 None（走原 no_tool 路径）"""
        self.messages.append({
            "role": "user",
            "content": f"{user_input}（系统：历史里的传感器数据已过期，本次必须重新调用 query_sensor 获取实时数据）"
        })
        try:
            response = ollama.chat(
                model=self.model,
                messages=self.trimmed_messages(),
                tools=self.tools_config,
                options=self.gen_options,
                stream=False
            )
            message = response['message']
            if message.get('tool_calls') \
                    and message['tool_calls'][0]['function']['name'] == 'query_sensor':
                arguments = message['tool_calls'][0]['function']['arguments']
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if "type" not in arguments and "type:" in arguments:
                    arguments["type"] = arguments.pop("type:")
                if arguments.get("type") not in ("lidar", "odom", "all"):
                    arguments["type"] = "all"
                return {
                    "status": "success",
                    "action": "query_sensor",
                    "parameters": arguments,
                    "user_input": user_input,
                    "tool_calls": message["tool_calls"],
                }
        except Exception:
            pass
        self.messages.pop()   # 重试失败：撤掉提醒消息，保持历史干净
        return None

    def followup_tool_result(self, function_name, tool_result):
        """Day9：真实工具结果回填 → 二次推理 → 自然语言回答
        注意：chat() 已追加 assistant(tool_calls)，这里只补 tool 结果+二次回答"""
        self.messages.append({
            "role": "tool",
            "name": function_name,
            "content": tool_result,
        })
        response = ollama.chat(
            model=self.model,
            messages=self.trimmed_messages(),
            tools=None,                 # 关键：答案阶段不再提供工具
            options=self.gen_options,
            stream=False
        )
        answer = response['message']['content'].strip()
        # 关键：二次回答必须追加历史，否则对话不完整（实测踩坑）
        self.messages.append({"role": "assistant", "content": answer})
        return answer

