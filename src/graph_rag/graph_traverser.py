"""
图遍历模块 — 基于 Neo4j Cypher 查询实现知识图谱的关联遍历。

✅ 已实现。以实体抽取结果为起点，采用三级降级路由策略遍历知识图谱：

    Level 1 — 模板查询（type 已知）：
        实体类型为 Module / Regulation / Equipment 时，直接使用预定义 Cypher 模板
        - Module  → system_operations_navigation（模块→功能→步骤→前置条件）
        - Regulation → regulation_detail（法规→条款→标准）
        - Equipment  → equipment_dependency（设备→依赖设备→区域）

    Level 2 — 类型反查（type 未知）：
        先用 MATCH (n {name: $name}) 查图获取节点标签，回填 type 后重试模板查询
        适用于 NER 补充的 Unknown 类型实体

    Level 3 — LLM 生成查询（模板均失败）：
        将实体和图 Schema 约束传入 LLM，生成参数化 Cypher 语句执行
        作为最终兜底策略

三种典型遍历场景：
    1. 系统操作导航：Module → Function → Step → Requirement
    2. 法规关联检索：Regulation → Clause → Standard
    3. 设备依赖追踪：Equipment → Equipment(依赖) → Zone

由 MCP Tool (graph_query) 和 orchestrator.py 调用。

⚠️ 已知问题：
    1. 模块级全局 Neo4jDrivers 实例（N4JD）在 import 时即创建，应延迟到首次使用
    2. traverse() 中 raise ValueError 在空结果时直接中断，应返回空列表或由调用方决定
    3. 只处理 extract_result 中的第一个实体（for 循环内 return），多实体场景丢失结果

待优化：
    - 支持多实体并行遍历，合并多路图查询结果
    - 增加遍历深度控制（当前模板固定深度）
    - LLM 生成查询结果的安全性校验（防止误写操作）
"""



from typing import LiteralString

from neo4j import AsyncDriver
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.llm_config import DeepSeek_LLM
from graph_rag.config import get_settings
from graph_rag.entity_extractor import Entity, ExtractResult
from graph_rag.graph_db.connection import Neo4jDrivers
from graph_rag.graph_db.queries import GraphQueries
from util_tools.logger import get_logger

logger = get_logger(__name__)


def _get_neo4j_driver() -> Neo4jDrivers:
    """懒加载 Neo4j 驱动（替代模块级 N4JD 实例化）。"""
    s = get_settings()
    return Neo4jDrivers(s.neo4j_uri, s.neo4j_user, s.neo4j_password, s.neo4j_database)


_N4JD: Neo4jDrivers | None = None


def _shared_neo4j() -> Neo4jDrivers:
    """进程级 Neo4j 驱动单例。"""
    global _N4JD
    if _N4JD is None:
        _N4JD = _get_neo4j_driver()
    return _N4JD
class GraphTraverser:
    """
        遍历图谱，获取关联上下文,根据提取的关键词，采取逐层降级检索的方式
        1. 判断类型中是否存在type，如果存在，根据type选择模板进行检索
        2. 若为小模型提取或其他原因，type不可知，提取关键词进行一次图遍历，拿到类型后，继续按照模板进行检索。
        3. 若图遍历未找到具体节点或者类型确实，那么llm生成查询语句，再次进行检索。
        4. 若实在未找到，那么返回空，并提示未找到数据
        5. 中间查询到type后，回填如类型，可能后续有用。
    """
    def __init__(self,extract_result:ExtractResult,Neo4jDriver:Neo4jDrivers|None=None):
        self.Neo4jDriver = Neo4jDriver or _shared_neo4j()
        self.extract_result = extract_result

    async def traverse(self):
      a_driver = await self.Neo4jDriver._get_async_driver()
      for entitie in self.extract_result.entities:
         if not entitie:
            logger.info("提取结果为空，跳过该实体")
            continue
         if entitie.type.lower() in ["module", "regulation", "equipment"]:
            logger.info("类型为 %s，进行图遍历", entitie.type)
            # 进行图遍历
            result = await self.by_module_query(entitie,a_driver)
            return result
         else:
            # 如果图反查结果存在，则取出类型回填入关键词类，并进行遍历，否则执行llm查询的函数
            logger.info("类型为 %s，无法进行图遍历，将优先查询提取词类型", entitie.type) 
            new_entitie = await self.query_type(entitie,a_driver)
            # 判断回填的type是否存在模板
            if new_entitie.type.lower() in ["module", "regulation", "equipment"]: # type: ignore
                result = await self.by_module_query(new_entitie,a_driver) # type: ignore
                return result
            else:
                logger.info("类型为 %s，无法进行图遍历，将进行llm查询", new_entitie.type) # type: ignore
                result = await self.llm_query(new_entitie,a_driver) # type: ignore
                if not result:
                    logger.info("LLM图遍历结果为空")
                    return []
                return result

    async def by_module_query(self,entity:Entity,driver:AsyncDriver):
        """
        根据模板进行图遍历
        args:
            entity: Entity                      抽取的关键词
            driver: AsyncDriver                 neo4j 驱动
        return:
            result                              图遍历结果
        """
        if entity.type == "module":
            # 关键词为module，按照模板进行系统操作导航遍历
            query: LiteralString = GraphQueries.system_operations_navigation
            params = {"module_name": entity.name}
            async with driver.session(database=self.Neo4jDriver.database) as session:
                query_result = await session.run(query, params) 
                records = await query_result.data()
            result = records

        elif entity.type == "regulation":
            # 关键词为regulation，按照模板进行法规详情遍历
            query: LiteralString = GraphQueries.regulation_detail
            params = {"regulation_name": entity.name}
            async with driver.session(database=self.Neo4jDriver.database) as session:
                query_result = await session.run(query, params)
                records = await query_result.data()
            result = records
        else :
            # 关键词为equipment，按照模板进行图遍历
            query: LiteralString = GraphQueries.equipment_dependency
            params = {"equipment_name": entity.name}
            async with driver.session(database=self.Neo4jDriver.database) as session:
                query_result = await session.run(query, params) 
                records = await query_result.data()
            result = records
        if not result:
            logger.info("图遍历结果为空，图数据库无相应数据")
            return []
        return result
    async def query_type(self,entity:Entity,driver:AsyncDriver):
        """
        根据提取的关键词，去图数据进行查询，找出其类型，回填至Entity
        args:
            entity: Entity                      抽取的关键词
            driver: AsyncDriver                 neo4j 驱动
        return:
            entity                              回填后的实体
        """
        query: LiteralString = """
        MATCH (n {name: $entity_name})
        RETURN labels(n) AS nodeLabels
        LIMIT 1
        """
        params = {"entity_name": entity.name}
        async with driver.session(database=self.Neo4jDriver.database) as session:
            query_result = await session.run(query, params)
            records = await query_result.data()
        if not records:
            logger.info("实体[%s]在图数据库中未找到匹配节点，无法确定类型", entity.name)
            entity.type = "Unknown"
            return entity
        node_labels = records[0]["nodeLabels"]
        if not node_labels:
            logger.info("实体[%s]匹配的节点无标签，无法确定类型", entity.name)
            entity.type = "Unknown"
            return entity
        # 优先匹配已知的模板类型，忽略内部标签（如 __Entity__ 等）
        known_types = {"Module", "Regulation", "Equipment"}
        matched = [label for label in node_labels if label in known_types]
        if matched:
            entity.type = matched[0].lower()
            logger.info("实体[%s]类型回填为: %s", entity.name, entity.type)
        else:
            entity.type = node_labels[0].lower()
            logger.info("实体[%s]类型回填为非标准标签: %s", entity.name, entity.type)
        return entity
    async def llm_query(self,entity:Entity,driver:AsyncDriver):
        """
        根据llm生成的查询语句进行图遍历,返回结果
        args:
            entity: Entity                      抽取的关键词
            driver: AsyncDriver                 neo4j 驱动
        return:
            result                              图遍历结果
        """
        llm = GraphQueries(DeepSeek_LLM)
        result = await llm.query_llm(entity)
        if not result:
            logger.info("LLM未正常生成查询语句，无法进行图遍历")
            return ("LLM生成查询语句失败")
        query = result["query"]
        params = result.get("params", {})
        async with driver.session(database=self.Neo4jDriver.database) as session:
            query_result = await session.run(query, params)
            records = await query_result.data()
        if not records:
            logger.info("图遍历结果为空，图数据库无相应数据")
            return ("图遍历结果为空，图数据库无相应数据")
        return records
        
        
 
