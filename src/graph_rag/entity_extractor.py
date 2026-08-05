"""
实体抽取模块 — 通用实体/关系抽取引擎，同时服务于查询端和入库端。

✅ 查询端已实现：从用户自然语言问题中提取关键实体，供 graph_traverser 图遍历。
❌ 入库端待重构：从知识文档段落中抽取实体和关系，供 ingestion/entity_relation_extractor 写入 Neo4j。

抽取方式（两端共用）：
    1. LLM抽取：通过 with_structured_output(ExtractResult) 提取实体名称和类型
    2. NER抽取：基于 HuggingFace BERT 小模型（Davlan/bert-base-multilingual-cased-ner-hrl）
    3. 两种抽取结果进行去重融合（LLM 为主，NER 为补充），采用异步模式

已实现方法：
    - entity_extract_llm()   LLM 结构化抽取（异步，2秒超时）
    - entity_extract_ner()   NER 小模型抽取（同步，通过 asyncio.to_thread 包装）
    - merge_results()        LLM+NER 结果融合（LLM 为主，NER 补充 Unknown 类型实体）
    - _is_similar()          文本相似度判断（包含关系 / 字符重叠率）
    - main_pip()             异步管线入口（LLM+NER 并行 → 融合）

消防领域典型实体：
    - 设备：烟感探测器-01、喷淋泵、EPS电源
    - 法规：建筑设计防火规范、医疗机构消防安全管理规范
    - 区域：ICU病房、B栋3层、地下车库
    - 模块：消防巡检、消防维修

补充：
    目前优先使用 LLM 抽取结果，可考虑在LLM抽取时，将问题以及LLM的输出结果持久化入数据库，
    后续考虑对提问数据进行清洗，用于训练本地小模型，效果好的话，可以直接使用本地小模型进行抽取，
    LLM作为兜底，进而降低LLM调用次数与时间。

"""
import asyncio
import os
import time
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel
from util_tools.logger import get_logger
from langchain_openai import ChatOpenAI
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
import httpx
from graph_rag.graph_db.schema import NODE_TYPES, REL_TYPES

logger = get_logger(__name__)

_NER_PIPELINE = None
_NER_LOCK = asyncio.Lock() if hasattr(asyncio, 'Lock') else None


def _get_ner_pipeline(model_name: str = "Davlan/bert-base-multilingual-cased-ner-hrl"):
    """获取 NER pipeline 全局单例（懒加载，模型只加载一次 ~400MB）。"""
    global _NER_PIPELINE
    if _NER_PIPELINE is None:
        logger.info("首次加载 NER 模型: %s", model_name)
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForTokenClassification.from_pretrained(model_name)
        _NER_PIPELINE = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy="simple")
        logger.info("NER 模型加载完成")
    return _NER_PIPELINE


# 定义LLM输出结构
class Entity(BaseModel):
    name: str
    type: str

class Relation(BaseModel):
    source: str
    target: str
    relation: str

class ExtractResult(BaseModel):
    entities: list[Entity]
    relations: list[Relation]
"""
范例
ExtractResult(
    entities=[
        Entity(name="烟感探测器", type="Equipment"),
        Entity(name="ICU病房", type="Zone"),
        Entity(name="消防巡检", type="Module"),
    ],
    relations=[
        Relation(source="烟感探测器", target="ICU病房", relation="安装于"),
    ]
)
"""



class EntityExtractor:
    def __init__(self,llm_client:ChatOpenAI,query:str,config:RunnableConfig|None=None,entity_extract_model:str="Davlan/bert-base-multilingual-cased-ner-hrl"):
        self.config = config
        self.llm_client = llm_client
        self.query = query
        self.driver = None
        self.entity_extract_model = entity_extract_model

        self.entity_cache = {}
        self.relation_cache = {}
        self.subgraph_cache = {}

        self.pipe = _get_ner_pipeline(entity_extract_model)


    
    # ── 图 Schema 常量（来自 graph_db/schema.py），供 prompt 引用 ──
    # ponytail: 统一到 schema.py，此处仅引用，不再重复定义

    NODE_TYPES = NODE_TYPES
    REL_TYPES = REL_TYPES

    @staticmethod
    def _format_schema() -> tuple[str, str]:
        """将 NODE_TYPES / REL_TYPES 格式化为 prompt 可用的描述文本。"""
        node_desc = "\n".join(f"    - {k}：{v}" for k, v in NODE_TYPES.items())
        rel_desc = "\n".join(f"    - {k}：{v}" for k, v in REL_TYPES.items())
        return node_desc, rel_desc

    def _build_extract_prompt(self) -> str:
        """构建实体抽取 prompt，将图 Schema 约束嵌入其中。"""
        node_desc, rel_desc = self._format_schema()

        return f"""你是一个消防后勤领域的实体抽取专家。请从用户问题中提取与图数据库查询相关的关键实体和关系。

## 用户问题
{self.query}

## 图数据库节点类型（仅限以下类型，不得自行编造）
{node_desc}

## 图数据库关系类型（仅限以下类型，不得自行编造）
{rel_desc}

## 抽取规则
1. 仅提取问题中明确提及或可强推断的实体，不要臆造问题中未涉及的内容
2. 每个实体的 type 必须是上述节点类型之一，无法确定时选最接近的
3. 关系的 relation 必须是上述关系类型之一，且 source/target 的类型须与关系定义的方向一致
4. 如果问题中无法提取出关系，relations 可返回空列表
5. 不要输出与问题无关的实体

## 返回格式
请严格返回如下 JSON 格式，不要输出任何其他内容：
```json
{{
  "entities": [{{"name": "实体名", "type": "节点类型"}}],
  "relations": [{{"source": "源实体名", "target": "目标实体名", "relation": "关系类型"}}]
}}
```
"""

    async def entity_extract_llm(self):
        """
        利用 LLM 进行实体抽取，返回 ExtractResult（异步调用）。

        DeepSeek 不支持 with_structured_output，使用 JSON Output 模式：
        1. 设置 response_format={'type': 'json_object'} 强制 JSON 输出
        2. prompt 中包含 json 字样和格式样例（DeepSeek JSON Output 前提条件）
        3. 手动解析为 ExtractResult 类
        """
        prompt = self._build_extract_prompt()
        try:
            # 方式1：OpenAI structured output（DeepSeek 不支持，保留供兼容）
            # entity_llm = self.llm_client.with_structured_output(ExtractResult)
            # response = await entity_llm.ainvoke(prompt)

            # 方式2：DeepSeek JSON Output 模式 — response_format + 手动解析
            # DeepSeek 官方要求：response_format={'type': 'json_object'}，
            # prompt 中必须含有 "json" 字样并给出格式样例
            response = await self.llm_client.ainvoke(
                prompt,
                config=RunnableConfig(
                    max_concurrency=1,
                ),
            )
            # langchain_openai ChatOpenAI 通过 model_kwargs 传 response_format，
            # 但 ainvoke 不支持，改用 bind 方式
            # 实际已在 __init__ 中通过 model_kwargs 传入
            text = response.content

            # DeepSeek JSON Output 模式下可能返回空 content，按官方说明处理
            if not text or not text.strip():
                logger.warning("DeepSeek 返回空 content，尝试 NER 兜底")
                return None

            # 从 LLM 返回文本中提取 JSON（兼容 ```json ... ``` 包裹和裸 JSON）
            import re, json
            json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 兜底：直接尝试整段文本解析
                json_str = text

            data = json.loads(json_str)
            # 将 JSON 解析为与 structured_output 相同的 ExtractResult 类
            entities = [Entity(**e) for e in data.get("entities", [])]
            relations = [Relation(**r) for r in data.get("relations", [])]
            return ExtractResult(entities=entities, relations=relations)

        except Exception as e:
            logger.error("LLM 实体抽取失败:%s, 开始使用NER抽取关键信息", str(e))

    async def predict(self):
        """
        利用asyncio.to_thread 将 CPU 密集型的 BERT 推理丢给线程池，
        防止它在计算时阻塞 Python 的主事件循环，导致llm不执行。
        """
        return await asyncio.to_thread(self.entity_extract_ner)
        
        

    def entity_extract_ner(self):
        """
        根据规则对用户问题进行实体抽取用作llm的保底,此处采用本地小模型提取，而非关键词匹配。
        """
        raw_result = self.pipe(self.query)
        formatted = []
        for entity in raw_result:
            formatted.append({
                "text": entity["word"],
                "start": entity["start"],
                "end": entity["end"],
                "source": "Local_BERT"
            })
            
        return formatted
    
    @staticmethod
    def _is_similar(text_a: str, text_b: str, threshold: float = 0.6) -> bool:
        """
        判断两个文本是否相似（包含关系或高重叠率）。
        - 包含关系：如 "烟感探测器" 包含于 "烟感探测器-01"
        - 字符重叠率：交集长度 / 较短文本长度 >= threshold
        """
        a, b = text_a.strip(), text_b.strip()
        if not a or not b:
            return False
        # 包含关系
        if a in b or b in a:
            return True
        # 字符级重叠率
        set_a, set_b = set(a), set(b)
        overlap = len(set_a & set_b)
        shorter = min(len(set_a), len(set_b))
        return shorter > 0 and overlap / shorter >= threshold

    def merge_results(self, llm_result: ExtractResult | None, ner_result: list[dict]) -> ExtractResult:
        """
        融合 LLM 和 NER 的抽取结果，策略：LLM 为主，NER 为补充。

        1. LLM 结果全部保留（有准确的类型信息）
        2. NER 结果中与 LLM 已有实体无重叠的，追加为补充实体
        3. NER 补充的实体 type 默认设为 "Unknown"，待后续图遍历时再确认
        """
        # LLM 抽取失败时，完全依赖 NER
        if llm_result is None:
            entities = [
                Entity(name=item["text"], type="Unknown")
                for item in ner_result
            ]
            return ExtractResult(entities=entities, relations=[])

        # 收集 LLM 已有的实体名称
        llm_names = [e.name for e in llm_result.entities]

        # 遍历 NER 结果，无重叠则追加
        merged_entities = list(llm_result.entities)
        for ner_item in ner_result:
            ner_text = ner_item["text"]
            # 检查是否与 LLM 任一实体相似
            if not any(self._is_similar(ner_text, name) for name in llm_names):
                merged_entities.append(Entity(name=ner_text, type="Unknown"))
                logger.info("NER补充实体: %s (LLM未提取)", ner_text)

        return ExtractResult(
            entities=merged_entities,
            relations=llm_result.relations
        )
    
    async def main_pip(self):
        start_time = time.time()
        # 1. 并发创建两个任务
        llm_task = asyncio.create_task(self.entity_extract_llm())
        ner_task = asyncio.create_task(self.predict())

        # 2. 聚合等待，并对大模型设置 6.0 秒的硬超时防死锁
        llm_result: ExtractResult | None = None
        try:
            llm_result = await asyncio.wait_for(llm_task, timeout=6.0)  # type: ignore[assignment]
        except asyncio.TimeoutError:
            logger.warning("LLM 推理超时")
        ner_list = await ner_task

        # 3. 融合结果
        result = self.merge_results(llm_result, ner_list)
        end_time = time.time()
        logger.info("总耗时:%.2f秒", end_time - start_time)
        return result

#  测试
