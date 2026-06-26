"""
常用 Cypher 查询模板 — 按场景预定义的图遍历查询。

三种核心查询场景：
    1. 系统操作导航：从模块名出发，遍历功能→步骤→前置条件
    2. 法规关联检索：从区域类型出发，遍历适用法规→条款→引用标准→配置要求
    3. 设备依赖追踪：从设备出发，遍历供电/控制依赖→受影响分区

每个查询模板为参数化的 Cypher 语句，由 graph_traverser.py 调用时填入具体参数。
模板设计原则：使用 OPTIONAL MATCH 避免因缺少关系而丢失主干节点。

考虑两种查询方式，一种使用模版化的 Cypher 语句，一种使用llm生成的cypher语句，优先生成，然后使用模版化的cypher。
模版化查询优先，查询无数据时，使用llm生成的cypher。
"""

from graph_rag.entity_extractor import ExtractResult


class GraphQueries:
    # ── 系统操作子图 ──
    system_operations_navigation = f"""
    MATCH (module:Module {{name: $module_name}})
    OPTIONAL MATCH (module)-[:BELONGS_TO]->(function:Function)
    OPTIONAL MATCH (function)-[:BELONGS_TO]->(step:Step)
    OPTIONAL MATCH (step)-[:PRECONDITION]->(precondition:Precondition)
    RETURN module, function, step, precondition
    """

    # ── 法规关联子图 ──
    regulation_association = f"""
    MATCH (zone_type:ZoneType {{name: $zone_type_name}})
    OPTIONAL MATCH (zone_type)-[:APPLIES_TO]->(regulation:Regulation)
    OPTIONAL MATCH (regulation)-[:CONTAINS]->(clause:Clause)
    OPTIONAL MATCH (clause)-[:REFERENCES]->(standard:Standard)
    RETURN zone_type, regulation, clause, standard
    """

    # ── 设备依赖子图 ──
    equipment_dependency = f"""
    MATCH (equipment:Equipment {{name: $equipment_name}})
    OPTIONAL MATCH (equipment)-[:DEPENDS_ON]->(dependent_equipment:Equipment)
    OPTIONAL MATCH (dependent_equipment)-[:LOCATED_IN]->(zone:Zone)
    RETURN equipment, dependent_equipment, zone
    """

    def __init__(self,OpenAI_client):
        self.llm_client = OpenAI_client

    async def query_llm(self,key_words:ExtractResult):
        prompt = f"基于以下关键词，生成查询语句：{key_words}"
        try:
            response = self.llm_client.ainvoke(prompt)
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


        
    
    