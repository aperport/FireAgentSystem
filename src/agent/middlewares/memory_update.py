"""
记忆更新中间件 — 在每轮 Agent 回复完成后自动更新用户偏好文件。

Hook: aafter_agent

功能：
    自动提取对话中涉及的消防关键词，更新 StoreBackend 中的用户偏好文件。
    Agent 无需手动维护 recent_equipment / recent_queries —— 系统自动处理。

处理流程：
    1. 获取 user_id（从 runtime.context）
    2. 判断最后一条用户消息是否"有意义"（关键词匹配 + 子Agent委派检测）
    3. LLM 提取实体（设备名称、查询摘要）
    4. 合并更新 /memories/{user_id}/preferences.md
消防场景适配（相较于原采购项目）：
    - business_keywords 改为消防领域（巡检、维保、火警、故障、能耗、值班等）
    - 实体提取结果从 {suppliers: [...], query: "..."} 改为 {equipment: [...], query: "..."}
    - 偏好文件中 recent_suppliers 改为 recent_equipment
    - 去掉 preferred_currency

使用方式:
    from agent.middlewares.memory_update import MemoryUpdateMiddleware
    middleware = MemoryUpdateMiddleware(model=SUMMARY_MODEL)
"""

import json
from typing import Any, Dict
from datetime import datetime, timezone
from langchain.agents.middleware.types import AgentState
from langchain_core.messages import BaseMessage
from langchain.chat_models import BaseChatModel
from unitl_tools.logger import get_logger
from langchain.agents.middleware import AgentMiddleware
logger = get_logger(__name__)



class MemoryUpdateMiddlewareTools:

    def __init__(self):
        self.business_keywords = [
            "巡检", "维保", "火警", "故障", "能耗", "值班",
            "用电", "用水", "用气",
            "烟感", "喷淋", "设备", "消火栓", "报警", "探测器",
            "灭火", "消防", "配电", "泵", "电源",
        ]
        self.skip_words = [
            "你好", "在吗", "谢谢", "好的", "知道了", "嗯", "哦",
            "hi", "hello", "ok", "thanks",
        ]

    def _is_meaningful_last(self, message:list[BaseMessage])->str | None:
        """
        判断最后一条用户消息是否有意义
        """
        last_user_message = None
        # 使用反向迭代迭代message，根据type判断，寻找最后一条用户信息，找到最后一条结束循环
        for msg in reversed(message):
            msg_type = getattr(msg, "type", None)
            if msg_type == "human":
                last_user_message = msg
                break
        # 如果没找到用户消息或者最后一条用户消息为空，返回None
        if not last_user_message:
            return None
        
        content = last_user_message.content
        if isinstance(content, list):
            content = " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
            )
        content = str(content).strip()  # 去两边空格

        if not content:
            return None
        
        # 跳过无意义消息
        content_lower = content.lower().replace(" ", "")  # 删除字符串空格
        for pattern in self.skip_words:
            if pattern.lower().replace(" ", "") in content_lower:
                return None
            
        # 检查是否包含关键词信息
        has_keyword = any(
            keyword.lower() in content_lower for keyword in self.business_keywords)  # 是否含有任意一个关键词
        
        # 兜底：检查是否委派了子 Agent（messages 中有 task 工具调用）(工具调用这一块需要灵活修改)
        if not has_keyword:
            has_subagent_call = False
            for msg in message:
                if hasattr(msg, "tool_calls") and msg.tool_calls:  # type: ignore # 检查对象里是否含有特定属性hasattr
                    for tc in msg.tool_calls:  # type: ignore # 检查对象里是否含有特定属性hasattr
                        if tc.get("name") == "task":
                            has_subagent_call = True
                            break
                if has_subagent_call:
                    break
            if not has_subagent_call:
                return None

        return content
    
    def  _extract_ai_summary(self, message:list[BaseMessage])->str | None:
        """
        提取最后一条AI消息的前300字符作为摘要
        """ 
        for msg in reversed(message):
            if getattr(msg, "type", None) == "ai":
                content = msg.content
                if isinstance(content, list):
                    content = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                    )
                content = str(content).strip()  # 去两边空格
                return content[:300]
        # 如果没有找到AI消息，返回空字符串
        return ""
    
    async def _extract_entities(self,model:BaseChatModel,user_message:str,ai_summary:str | None = None)->Dict[str,Any]:
        """
        利用大语言模型对用户查询关键词进行提取
        args:
            model:大语言模型
            user_messsage:用户消息
            ai_summary:AI摘要
        return:
            entities
        """


        # 消防后勤场景实体提取
        prompt = f"""从以下消防后勤对话中提取关键实体。

规则：
1. "equipment": 对话中提及的消防设备名称（如：烟感探测器-01、喷淋泵、EPS电源）。未提及则为空列表。
2. "zones": 对话中提及的建筑区域（如：B栋3层、ICU病房、A栋配电间）。未提及则为空列表。
3. "query": 用户查询的一句话摘要。非消防相关问题则为空字符串。

用户消息：{user_message}

AI回复摘要：{ai_summary}

仅返回JSON对象，不要包含其他文字：
{{"equipment": ["设备A", "设备B"], "zones": ["区域A"], "query": "简要摘要"}}"""
        



        try:
            response = await model.ainvoke(prompt)
            
            # 从回复中提取json
            text = response.content
            if isinstance(text, list):
                text = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in text
                )
            text = str(text).strip()            
            # 提取json块，通过位置提取
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                result = json.loads(text[start:end + 1])
                return {
                    "equipment": result.get("equipment", []),
                    "zones": result.get("zones", []),
                    "query": result.get("query", ""),
                }
        except Exception:
            logger.warning("MemoryUpdateMiddleware: LLM 提取失败，跳过本次更新", exc_info=True)

        return {"equipment": [], "query": ""}
    

    def _create_file_value(self,content_str: str) -> dict:
        """
        创建 StoreBackend 兼容的文件值（与 deepagents.backends.utils.create_file_data 一致）。
        """
        lines = content_str.split("\n")
        now = datetime.now(datetime.timezone.utc).isoformat() # type: ignore
        return {
            "content": lines,
            "created_at": now,
            "modified_at": now,
        }


class MemoryUpdateMiddleware(AgentMiddleware):
   """
   人为干预，在agent回复后根据信息自动更新用户偏好
   """ 
   def __init__(self,model:BaseChatModel):
       self.model = model
    
    #同步钩子，不执行操作
   def after_agent(self, state: AgentState[Any], runtime: Any) -> Dict[str, Any] | None:
       return None
   
   # 异步钩子
   async def aafter_agent(self, state:Dict[str,Any], runtime:Any)->Dict[str,Any] | None:
       """
       Agent回复后触发，提取实体并更新记忆
       args:
           state: 
           runtime: 
       """
       try:
           # 1.获取user_id
           ctx = getattr(runtime, "context", {})
           if not ctx:
                return None
           user_id = getattr(ctx, "user_id", None)
           if not user_id:
               return None
           
           # 2.获取消息列表
           messages:list[BaseMessage] = getattr(state, "messages", [])
           if not messages:
               return None
           
           # 3.判断是否需要更新
           tools = MemoryUpdateMiddlewareTools()
           user_messages = tools._is_meaningful_last(messages)
           if not user_messages:
               return None
           
           # 4.获取AI摘要
           ai_summary = tools._extract_ai_summary(messages)

           # 5.LLM提取实体
           entities = await tools._extract_entities(self.model,user_messages,ai_summary)
           equipment = entities.get("equipment", [])
           zones = entities.get("zones", [])
           query = entities.get("query", "")
           if not equipment and not zones and not query:
               return None
           logger.info(f"已提取实体，设备：{equipment}, 区域：{zones}, 查询：{query}")

           # 6.从 StoreBackend 中读取用户已有的偏好文件。
           store = getattr(runtime, "store", None)
           if not store:
               logger.warning("MemoryUpdateMiddleware: 未找到 StoreBackend，跳过本次更新")
               return None
           
           namespace = (user_id,)
           key = f"/{user_id}/preferences.md"

           try:
               item = await store.aget(namespace, key)
           except Exception as e:
               item = None

            # 7.解析现有内容或者创建默认内容
           current_lines:list[str] = []
           if item and hasattr(item,"value"):
               value = item.value
               if isinstance(value, dict):
                   content = value.get("content", [])
                   if isinstance(content, list):
                       current_lines = content  # content 已经是 list[str]
                   elif isinstance(content, str):
                        current_lines = content.split("\n")
               elif isinstance(value, str):
                    current_lines = value.split("\n")
            # 内部调用，下面方法使用了self，此处也要使用self调用，不然下边方法不要写self
           updated_content = self._merge_preferences(
                current_lines, equipment, zones, query
            )

            # 8.更新记忆
           file_value = tools._create_file_value(updated_content) # type: ignore
           await store.aput(namespace, key, file_value)
           logger.info(f"已更新记忆，设备：{equipment}, 区域：{zones}, 查询：{query}")
       except Exception as e:
           logger.warning(f"MemoryUpdateMiddleware: 更新失败，{e},跳过本次更新", exc_info=True,)

       return None
   def _merge_preferences(self, current_lines: list[str], new_equipment: list[str], new_zones: list[str], new_query: str):
        """
        将新的用户偏好合并至其中
        策略：先移除旧 recent_equipment / recent_zones / recent_queries 区块，再在末尾追加合并后的版本。
        args:
            current_lines: 已有偏好文件行列表
            new_equipment: 新提取的设备实体
            new_zones: 新提取的区域实体
            new_query: 新提取的查询摘要
        """

        # 1.解析旧的偏好
        existing_equipment = []
        existing_zones = []
        existing_queries = []
        def _parse_list_items(lines: list[str], start_idx: int):
            """
            从start_idx开始解析列表项
            """
            items:list[str] = []
            title_line = lines[start_idx].strip()
            # 检查 inline 格式: recent_equipment: [a, b]
            colon_pos = title_line.find(":")
            if colon_pos != -1:
                inline = title_line[colon_pos + 1:].strip()
                if inline.startswith("[") and inline.endswith("]"):
                    inner = inline[1:-1].strip()
                    if inner:
                        return [s.strip().strip("'").strip('"') for s in inner.split(",") if s.strip()], 1
            # 多行格式: 从下一行开始收集 - xxx 项
            count = 1
            for j in range(start_idx + 1, len(lines)):
                stripped = lines[j].strip()
                if stripped.startswith("- "):
                    items.append(stripped[2:].strip().strip("'").strip('"'))
                    count += 1
                elif stripped and not lines[j].startswith(" "):
                    break  # 遇到下一个顶级字段
                else:
                    count += 1  # 空行或注释，仍属于当前区块
            return items, count
        # 2. 找出旧区块的位置和值
        equipment_start = -1
        equipment_len = 0
        zones_start = -1
        zones_len = 0
        queries_start = -1
        queries_len = 0

        for i, line in enumerate(current_lines):
            stripped = line.strip()
            if stripped.startswith("recent_equipment:"):
                equipment_start = i
                existing_equipment, equipment_len = _parse_list_items(current_lines, i)
            elif stripped.startswith("recent_zones:"):
                zones_start = i
                existing_zones, zones_len = _parse_list_items(current_lines, i)
            elif stripped.startswith("recent_queries:"):
                queries_start = i
                existing_queries, queries_len = _parse_list_items(current_lines, i)

        # 3. 从原内容中移除旧区块（从后往前移，避免索引偏移）
        clean_lines = list(current_lines)
        # 按起始位置降序排列，从后往前删除
        removals = []
        if equipment_start >= 0:
            removals.append((equipment_start, equipment_len))
        if zones_start >= 0:
            removals.append((zones_start, zones_len))
        if queries_start >= 0:
            removals.append((queries_start, queries_len))
        removals.sort(key=lambda x: x[0], reverse=True)

        for start, length in removals:
            del clean_lines[start:start + length]

        # 4. 合并新值和旧值
        merged_equipment = list(new_equipment)
        for s in existing_equipment:
            if s not in merged_equipment:
                merged_equipment.append(s)
        merged_equipment = merged_equipment[:10]

        merged_zones = list(new_zones)
        for z in existing_zones:
            if z not in merged_zones:
                merged_zones.append(z)
        merged_zones = merged_zones[:5]

        merged_queries = [new_query] if new_query else []
        for q in existing_queries:
            if q.strip() not in [m.strip() for m in merged_queries]:
                merged_queries.append(q)
        merged_queries = merged_queries[:5]

        # 5. 追加合并后的区块
        result_lines = list(clean_lines)

        # 确保末尾有空行分隔
        if result_lines and result_lines[-1].strip():
            result_lines.append("")

        result_lines.append("recent_equipment:")
        if merged_equipment:
            for s in merged_equipment:
                result_lines.append(f"  - {s}")
        else:
            result_lines[-1] = "recent_equipment: []"

        result_lines.append("recent_zones:")
        if merged_zones:
            for z in merged_zones:
                result_lines.append(f"  - {z}")
        else:
            result_lines[-1] = "recent_zones: []"

        result_lines.append("recent_queries:")
        if merged_queries:
            for q in merged_queries:
                result_lines.append(f"  - {q}")
        else:
            result_lines[-1] = "recent_queries: []"

        return "\n".join(result_lines).strip() + "\n"





  
                
               
               

           
           









           

            

