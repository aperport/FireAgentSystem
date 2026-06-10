"""
在每轮 Agent 回复完成后（aafter_agent 钩子），自动提取对话中涉及的关键词，更新 StoreBackend 中的用户偏好文件。

Agent 无需手动维护 recent_suppliers / recent_queries —— 系统自动处理。

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
            "关键词","关键词2","关于业务","关键词"
        ]
        self.skip_words = [
            "你好","在吗","此处是可以略过的关键词","此处是可以略过的关键词2"
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


        # 注意，下方提示词需根据实际业务修改
        prompt = f"""Extract procurement-related entities from this conversation.

    Rules:
    1. "suppliers": Company/supplier names mentioned. Include both Chinese and English names. Empty list if none.  
    2. "query": One-line summary of the user's procurement need. Empty string if not procurement-related.

    User message: {user_message}

    Assistant response summary: {ai_summary}

    Return ONLY a JSON object, no other text:
    {{"suppliers": ["CompanyA", "CompanyB"], "query": "brief summary"}}"""
        



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
                    "suppliers": result.get("suppliers", []),  # suppliers 供应商
                    "query": result.get("query", ""),
                }
        except Exception:
            logger.warning("MemoryUpdateMiddleware: LLM 提取失败，跳过本次更新", exc_info=True)

        return {"suppliers": [], "query": ""}
    

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
           suppliers = entities.get("suppliers", [])    # 注意此处使用的为项目数据，供应商，应根据实际业务去提取的实体中修改
           query = entities.get("query", "")
           if not suppliers and not query:
               return None
           logger.info(f"已提取实体，供应商：{suppliers}, 查询：{query}")

           # 6.从 StoreBackend 中读取用户已有的偏好文件。
           store = getattr(runtime, "store", None)
           if not store:
               logger.warning("MemoryUpdateMiddleware: 未找到 StoreBackend，跳过本次更新")
               return None
           
           namespace = (user_id)
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
                current_lines, suppliers, query
            )

            # 8.更新记忆
           file_value = tools._create_file_value(updated_content) # type: ignore
           await store.aput(namespace, key, file_value)
           logger.info(f"已更新记忆，供应商：{suppliers}, 查询：{query}")
       except Exception as e:
           logger.warning(f"MemoryUpdateMiddleware: 更新失败，{e},跳过本次更新", exc_info=True,)

       return None
   def _merge_preferences(self, current_lines: list[str], suppliers: list[str], query: str):
        """
        将新的用户偏好合并至其中
        策略：先移除旧 recent_suppliers / recent_queries 区块，再在末尾追加合并后的版本。
        args:
            current_lines: 
            suppliers: 
            query:
        """

        # 1.解析旧的偏好
        ex_suppliers = []
        ex_queries = []
        def _parse_list_items(lines: list[str], start_idx: int):
            """
            从start_idx开始解析列表项
            """
            items:list[str] = []
            title_line = lines[start_idx].strip()



  
                
               
               

           
           









           

            

