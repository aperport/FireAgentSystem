"""
实体抽取模块 — 从用户自然语言问题中提取关键实体。

支持两种抽取方式：
    1. LLM抽取：通过结构化输出提取实体名称和类型
    2. NER抽取：基于小模型识别专业实体（设备名、法规名、区域名等）
    3. 两种抽取结果进行去重融合，得到最终的抽取结果，采用异步模式。

补充：
    目前优先使用 LLM 抽取结果，可考虑在LLM抽取时，将问题以及LLM的输出结果持久化入数据库，后续考虑对提问数据进行清洗，用于训练本地小模型，效果好的话，可以直接使用本地小模型进行抽取，LLM作为兜底，进而降低LLM调用次数与时间

抽取结果供 graph_traverser.py 作为图遍历的起点实体。

消防领域典型实体：
    - 设备：烟感探测器-01、喷淋泵、EPS电源
    - 法规：建筑设计防火规范、医疗机构消防安全管理规范
    - 区域：ICU病房、B栋3层、地下车库
    - 模块：消防巡检、消防维修
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

logger = get_logger(__name__)

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

        # 图结构缓存
        self.entity_cache = {}
        self.relation_cache = {}
        self.subgraph_cache = {}

        # 模型初始化
        self.initialize_model()


    
    # ── 图 Schema 常量（来自 graph_db/schema.py），供 prompt 引用 ──

    NODE_TYPES = {
        "Module": "系统功能模块（如：值班、巡检、维修）",
        "Function": "模块下的具体功能",
        "Step": "功能的操作步骤",
        "Requirement": "执行步骤所需的前置条件/要求",
        "Regulation": "消防法规/规范（如：《建筑设计防火规范》GB50016）",
        "Clause": "法规中的具体条款（如：第5.1.1条）",
        "Standard": "被条款引用的技术标准（如：GB 17945-2010）",
        "ZoneType": "建筑分区分类（如：高层住宅、地下车库、ICU病房）",
        "EquipmentType": "设备分类规格（如：烟感探测器、喷淋头、消防泵）",
        "Equipment": "具体设备实例（如：烟感探测器-01、EPS电源-01）",
        "Zone": "建筑区域实例（如：B栋3层、地下车库A区）",
    }

    REL_TYPES = {
        "包含功能": "Module → Function",
        "操作步骤": "Function → Step",
        "下一步": "Step → Step",
        "前置条件": "Step → Requirement",
        "包含条款": "Regulation → Clause",
        "引用": "Clause → Standard",
        "适用法规": "ZoneType → Regulation",
        "要求配置": "Clause → EquipmentType",
        "属于分类": "Equipment → EquipmentType",
        "安装于": "Equipment → Zone",
        "依赖": "Equipment → Equipment（供电/控制）",
    }

    def _build_extract_prompt(self) -> str:
        """构建实体抽取 prompt，将图 Schema 约束嵌入其中。"""
        node_desc = "\n".join(f"    - {k}：{v}" for k, v in self.NODE_TYPES.items())
        rel_desc = "\n".join(f"    - {k}：{v}" for k, v in self.REL_TYPES.items())

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
严格按照约束格式返回
"""

    async def entity_extract_llm(self):
        """
        利用llm大模型进行实体抽取，并强制输出 ExtractResult（异步调用）
        """
        prompt = self._build_extract_prompt()
        try:
            # 强制输出 ExtractResult类型，无需后续json.loads
            entity_llm = self.llm_client.with_structured_output(ExtractResult)
            response = await entity_llm.ainvoke(prompt)
            return response

        except Exception as e:
            logger.error("理解查询意图失败:%s, 开始使用NER抽取关键信息", str(e))
    
    def initialize_model(self):
        """
        初始化小模型
        """
        # 加载分词器和模型，并组装成管道
        self.tokenizer = AutoTokenizer.from_pretrained(self.entity_extract_model)
        self.model = AutoModelForTokenClassification.from_pretrained(self.entity_extract_model)
        self.pipe = pipeline("ner", model=self.model, tokenizer=self.tokenizer, aggregation_strategy="simple")

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

        # 2. 聚合等待，并对大模型设置 2.0 秒的硬超时防死锁
        llm_result: ExtractResult | None = None
        try:
            llm_result = await asyncio.wait_for(llm_task, timeout=2.0)  # type: ignore[assignment]
        except asyncio.TimeoutError:
            logger.warning("LLM 推理超时")
        ner_list = await ner_task

        # 3. 融合结果
        result = self.merge_results(llm_result, ner_list)
        end_time = time.time()
        logger.info("总耗时:%.2f秒", end_time - start_time)
        return result

#  测试
