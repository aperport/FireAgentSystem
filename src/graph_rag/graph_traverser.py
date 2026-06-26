"""
图遍历模块 — 基于 Neo4j Cypher 查询实现知识图谱的关联遍历。

以实体抽取结果为起点，沿关系路径扩展 N 跳，获取结构化的关联上下文。

三种典型遍历场景：
    1. 系统操作导航：Module → Function → Step → Requirement
    2. 法规关联检索：ZoneType → Regulation → Clause → Standard
    3. 设备依赖追踪：Equipment → Equipment(依赖) → Zone
    
遍历深度、关系类型过滤等参数由 orchestrator.py 传入。

由 MCP Tool (graph_query) 和 orchestrator.py 调用。
"""

import os

from neo4j import AsyncDriver
from graph_rag.entity_extractor import Entity, ExtractResult
from graph_rag.graph_db.connection import Neo4jDrivers
from util_tools.logger import get_logger

logger = get_logger(__name__)
uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD", "neo4j")

N4JD = Neo4jDrivers(uri, user, password)
class GraphTraverser:
    """
        遍历图谱，获取关联上下文,根据提取的关键词，采取逐层降级检索的方式
        1. 判断类型中是否存在type，如果存在，根据type选择模板进行检索
        2. 若为小模型提取或其他原因，type不可知，提取关键词进行一次图遍历，拿到类型后，继续按照模板进行检索。
        3. 若图遍历未找到具体节点或者类型确实，那么llm生成查询语句，再次进行检索。
        4. 若实在未找到，那么返回空，并提示未找到数据
        5. 中间查询到type后，回填如类型，可能后续有用。
    """
    def __init__(self,extract_result:ExtractResult,Neo4jDriver:Neo4jDrivers=N4JD):
        self.Neo4jDriver = Neo4jDriver
        self.extract_result = extract_result

    async def traverse(self):
      a_driver = await self.Neo4jDriver._get_async_driver()
      for entitie in self.extract_result.entities:
         if not entitie:
            logger.info("提取结果为空，无法进行图遍历")
            raise ValueError("提取结果为空，无法进行图遍历")
         if entitie.type.lower() in ["zonetype", "regulation", "equipment"]:
            logger.info("类型为 %s，进行图遍历", entitie.type)
            # 进行图遍历
            result = await self.by_moudle_query(entitie,a_driver)
            return result
         else:
            logger.info("类型为 %s，无法进行图遍历，将优先查询提取词类型", entitie.type) 
            new_entitie = await self.query_type(entitie,a_driver)
            # 判断回填的type是否存在模板
            if new_entitie.type.lower() in ["zonetype", "regulation", "equipment"]: # type: ignore
                result = await self.by_moudle_query(new_entitie,a_driver) # type: ignore
                return result
            else:
                logger.info("类型为 %s，无法进行图遍历，将进行llm查询", new_entitie.type) # type: ignore
                result = await self.llm_query(new_entitie,a_driver) # type: ignore
                if result is None:
                    logger.info("图遍历结果为空，图数据库无相应数据")
                    raise ValueError("图遍历结果为空，图数据库无相应数据")
                return result

        # 如果图反查结果存在，则取出类型回填入关键词类，并进行遍历，否则执行llm查询的函数
         
    async def by_moudle_query(self,entity:Entity,driver:AsyncDriver):
        """
        根据模板进行图遍历
        """
        if entity.type == "zonetype":
            # 关键词为zonetype，按照模板进行图遍历
            print("关键词为zonetype，按照模板进行图遍历")

        elif entity.type == "regulation":
            # 关键词为regulation，按照模板进行图遍历
            print("关键词为regulation，按照模板进行图遍历")
        else :
            # 关键词为equipment，按照模板进行图遍历
            pass
        if not result:
            logger.info("图遍历结果为空，图数据库无相应数据")
            raise ValueError("图遍历结果为空，图数据库无相应数据")
        return result
    async def query_type(self,entity:Entity,driver:AsyncDriver):
        """
        根据提取的关键词，取图数据进行查询，找出其类型，回填至Entity
        """
        pass

    async def llm_query(self,entity:Entity,driver:AsyncDriver):
        """
        根据llm生成的查询语句进行图遍历,返回结果
        """
        pass
        
