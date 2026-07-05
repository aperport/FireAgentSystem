"""
常用 Cypher 查询模板 — 按场景预定义的图遍历查询 + LLM 动态生成。

✅ 已实现。三种核心查询场景（预定义模板）：
    1. system_operations_navigation：从模块名出发，遍历功能→步骤→前置条件
    2. regulation_detail：从法规名出发，遍历条款→引用标准
    3. equipment_dependency：从设备名出发，遍历依赖设备→安装区域

每个查询模板为参数化的 Cypher 语句，由 graph_traverser.py 调用时填入具体参数。
模板设计原则：使用 OPTIONAL MATCH 避免因缺少关系而丢失主干节点。

LLM 动态查询（query_llm 方法）：
    当预定义模板无法匹配时，将实体和图 Schema 约束传入 LLM，
    生成参数化 Cypher 语句。作为三级降级路由的最终兜底。

⚠️ 已知问题：
    1. ~~NODE_TYPES / REL_TYPES 与 entity_extractor.py 中重复定义~~ ✅ 已统一到 schema.py

待优化：
    - ~~统一 Schema 常量定义位置（移至 schema.py）~~ ✅ 已完成
    - 增加 LLM 生成 Cypher 的安全校验（禁止 CREATE/DELETE/SET 等写操作）
    - 增加查询结果缓存（相同实体重复查询时命中缓存）
"""

from typing import LiteralString

from graph_rag.entity_extractor import Entity
from graph_rag.graph_db.schema import NODE_TYPES, REL_TYPES
from util_tools.logger import get_logger

logger = get_logger(__name__)
# 默认查询语句，后续需要改

class GraphQueries:
    # ── 系统操作子图 ──
    system_operations_navigation: LiteralString = """
    MATCH (module:Module {name: $module_name})
    OPTIONAL MATCH (module)-[:包含功能]->(function:Function)
    OPTIONAL MATCH (function)-[:操作步骤]->(step:Step)
    OPTIONAL MATCH (step)-[:前置条件]->(requirement:Requirement)
    RETURN module, function, step, requirement
    """

    # ── 法规详情子图（从法规出发） ──
    regulation_detail: LiteralString = """
    MATCH (regulation:Regulation {name: $regulation_name})
    OPTIONAL MATCH (regulation)-[:包含条款]->(clause:Clause)
    OPTIONAL MATCH (clause)-[:引用]->(standard:Standard)
    RETURN regulation, clause, standard
    """

    # ── 设备依赖子图 ──
    equipment_dependency: LiteralString = """
    MATCH (equipment:Equipment {name: $equipment_name})
    OPTIONAL MATCH (equipment)-[:依赖]->(dependent_equipment:Equipment)
    OPTIONAL MATCH (dependent_equipment)-[:安装于]->(zone:Zone)
    RETURN equipment, dependent_equipment, zone
    """

    def __init__(self,OpenAI_client):
        self.llm_client = OpenAI_client

    async def query_llm(self,key_words:Entity):
        # 构建节点类型描述
        node_desc = "\n".join(f"    - {k}：{v}" for k, v in NODE_TYPES.items())
        rel_desc = "\n".join(f"    - {k}：{v}" for k, v in REL_TYPES.items())

        prompt = f"""你是一个消防后勤领域的 Neo4j Cypher 查询生成专家。
请根据给定的关键词实体，生成一条 Cypher 查询语句，用于在知识图谱中检索关联信息。

## 关键词实体
- 名称：{key_words.name}
- 类型：{key_words.type}

## 图数据库节点类型（仅限以下类型，不得自行编造）
{node_desc}

## 图数据库关系类型（仅限以下类型，不得自行编造）
{rel_desc}

## 生成规则
1. 必须使用参数化查询，参数名使用 $param_name 格式（如 $entity_name），不要直接拼接字符串
2. 起始节点通过 {{name: $param_name}} 匹配，不要使用其他属性
3. 使用 OPTIONAL MATCH 而非 MATCH，避免因缺少关系而丢失主干节点
4. 关系类型和方向必须严格遵循上述关系定义，不得编造关系
5. 仅返回与关键词实体直接关联或 1-2 跳内关联的节点，不要过度扩展
6. RETURN 中应包含所有匹配到的节点，以便获取完整上下文
7. 不要添加 CREATE、DELETE、SET 等写操作语句
8. 只输出纯 Cypher 语句，不要包含任何解释说明

## 示例
关键词：名称=消防巡检, 类型=Module
生成语句：
MATCH (module:Module {{name: $module_name}})
OPTIONAL MATCH (module)-[:包含功能]->(function:Function)
OPTIONAL MATCH (function)-[:操作步骤]->(step:Step)
RETURN module, function, step

请根据上述关键词实体生成 Cypher 查询语句："""
        try:
            response = await self.llm_client.ainvoke(prompt)
            result = response.content
            # 去除 LLM 返回的 markdown 代码块标记（如 ```cypher ... ```）
            stripped = result.strip()
            if stripped.startswith("```"):
                # 去除开头的 ```cypher 或 ```
                first_newline = stripped.find("\n")
                if first_newline != -1:
                    stripped = stripped[first_newline + 1:]
                else:
                    stripped = stripped[3:]
                # 去除结尾的 ```
                if stripped.rstrip().endswith("```"):
                    stripped = stripped.rstrip()[:-3].rstrip()
            return stripped
        except Exception as e:
            logger.error("理解查询意图失败:%s", str(e))


        
    
    