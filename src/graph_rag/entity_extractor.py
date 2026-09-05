"""
实体抽取模块 — 通用实体/关系抽取引擎，同时服务于查询端和入库端。
"""
import asyncio
import time
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel
from util_tools.logger import get_logger
from langchain_openai import ChatOpenAI
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
from graph_rag.graph_db.schema import NODE_TYPES, REL_TYPES
from functools import lru_cache

logger = get_logger(__name__)


# @lru_cache参数为1时，每次调用都会重新计算，为0时，相同的参数才会唯一，如传入不同的模型名称。会有两个实例
@lru_cache
def _get_ner_pipeline(model_name: str = "Davlan/bert-base-multilingual-cased-ner-hrl"):
    """
    获取唯一单例，懒加载。
    """
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForTokenClassification.from_pretrained(model_name)
    ner_pipeline = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy="simple")  # type: ignore
    return ner_pipeline


# 定义LLM输出结构

class Entity(BaseModel):
    name: str
    type: str


class Relation(BaseModel):
    source: str
    target: str
    relation: str


class ExtractResult(BaseModel):
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
    entities: list[Entity]
    relations: list[Relation]


class NerEntityExtractor:
    """
    利用本地NER实体抽取器，另一个方案是使用LLM进行抽取
    """

    def __init__(self, model_name: str = "Davlan/bert-base-multilingual-cased-ner-hrl"):
        self.pipe = _get_ner_pipeline(model_name)

    def _sync_extract(self, query: str) -> list[dict]:
        """
        使用小模型对问题进行抽取，之后按照模型提取字段映射返回数据
        """
        row_result = self.pipe(query)
        return [{"text": item["word"], "start": item["start"], "end": item["end"], "source": "Local_BERT"}
                for item in row_result]

    async def extract(self, query: str) -> list[dict]:
        """
        利用asyncio.to_thread 将 CPU 密集型的 BERT 推理丢给线程池，
        防止它在计算时阻塞 Python 的主事件循环，导致llm不执行。
        """
        return await asyncio.to_thread(self._sync_extract, query)


class LlmEntityExtractor:
    """
    使用LLM进行实体抽取
    """

    def __init__(self, llm: ChatOpenAI, config: RunnableConfig | None = None):
        self.llm = llm
        self.config = config

    NODE_TYPES = NODE_TYPES
    REL_TYPES = REL_TYPES

    @staticmethod
    def _format_schema() -> tuple[str, str]:
        """将 NODE_TYPES / REL_TYPES 格式化为 prompt 可用的描述文本。"""
        node_desc = "\n".join(f"    - {k}：{v}" for k, v in NODE_TYPES.items())
        rel_desc = "\n".join(f"    - {k}：{v}" for k, v in REL_TYPES.items())
        return node_desc, rel_desc

    def _build_extract_prompt(self, query: str) -> str:
        """构建实体抽取 prompt，将图 Schema 约束嵌入其中。"""
        node_desc, rel_desc = self._format_schema()

        return f"""你是一个消防后勤领域的实体抽取专家。请从用户问题中提取与图数据库查询相关的关键实体和关系。

    ## 用户问题
    {query}

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

    async def extract(self, query: str) -> ExtractResult | None:
        """
        利用 LLM 进行实体抽取，返回 ExtractResult（异步调用）,为防止模型不支持openAI格式化，使用两种方式。
        """
        try:
            async def _openai_structured_output(query: str) -> ExtractResult | None:
                # 方式1：OpenAI structured output ,有些模型可能不支持
                entily_llm = self.llm.with_structured_output(ExtractResult)
                response = await entily_llm.ainvoke(self._build_extract_prompt(query), config=self.config)
                if isinstance(response, ExtractResult):
                    return response
                response = None
                return response

            async def _general_output(query: str) -> ExtractResult | None:
                # 方式2，通用输出格式化，
                response = await self.llm.ainvoke(query, config=self.config, response_format=ExtractResult)
                if isinstance(response, ExtractResult):
                    return response
                response = None
                return response

            extract_result = await _openai_structured_output(query)
            if not extract_result:
                extract_result = await _general_output(query)
            return extract_result

        except Exception as e:
            logger.error(f"实体抽取失败：{e}")
            return None


class EntityFusionService:
    """
    相似度测试以及结果融合，用于对两种模型抽取的结果进行融合处理
    """

    def __init__(self, config: RunnableConfig | None = None):
        self.config = config

    @staticmethod
    def _is_simple_entity(text_a: str, text_b: str, threshold: float = 0.5) -> bool:
        """
        判断两个文本是否相似（包含关系或高重叠率）。
        - 包含关系：如 "烟感探测器" 包含于 "烟感探测器-01"
        - 字符重叠率：交集长度 / 较短文本长度 >= threshold
        args:
            text_a: 文本 A
            text_b: 文本 B
            threshold: 重叠率阈值
        returns:
            是否相似
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

    def fuse_entities(
            self,
            llm_result: list,
            ner_result: list,
            threshold: float = 0.5) -> ExtractResult:
        """
        融合两个实体列表，返回融合后的实体列表。
        llm的全部保留，ner模型进行补充
        args:
            entities_a: 实体列表 A
            entities_b: 实体列表 B
            threshold: 重叠率阈值
        returns:
            融合后的实体列表
        """
        if not llm_result:
            entitoes = [Entity(name=item["text"], type="Unknown") for item in ner_result]
            return ExtractResult(entities=entitoes, relations=[])

        # 收集llm抽取的实体名称
        llm_names = [e.name for e in getattr(llm_result, "entities", [])]

        # 遍历ner结果，无重叠则追加
        merged_entities = getattr(llm_result, "entities", [])
        for ner_item in ner_result:
            ner_text = ner_item["text"]
            # 检查是否与llm任一实体相似
            if not any(self._is_simple_entity(ner_text, name, threshold) for name in llm_names):
                merged_entities.append(Entity(name=ner_text, type="Unknown"))
                logger.info("NER补充实体: %s (LLM未提取)", ner_text)

        return ExtractResult(entities=merged_entities, relations=getattr(llm_result, "relations", []))


async def main_pip():
    """
    业务编排
    """
    start_time = time.time()
    # 1. 并发创建两个任务
    llm_task = asyncio.create_task(entity_extract_llm())
    ner_task = asyncio.create_task(predict())

    # 2. 聚合等待，并对大模型设置 6.0 秒的硬超时防死锁
    llm_result: ExtractResult | None = None
    try:
        llm_result = await asyncio.wait_for(llm_task, timeout=6.0)  # type: ignore[assignment]
    except asyncio.TimeoutError:
        logger.warning("LLM 推理超时")
    ner_list = await ner_task

    # 3. 融合结果
    result = merge_results(llm_result, ner_list)
    end_time = time.time()
    logger.info("总耗时:%.2f秒", end_time - start_time)
    return result
