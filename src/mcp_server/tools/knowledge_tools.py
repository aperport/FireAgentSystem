"""
知识检索 MCP 工具 — 为 fire-qa-assistant 子智能体提供 GraphRAG 检索能力。

注册三个 MCP Tool：
    1. graph_rag_search  — 高层组合：向量检索+图遍历+融合，一键返回完整上下文
    2. knowledge_search  — 底层原子：纯向量检索（简单问答直接用）
    3. graph_query       — 底层原子：纯图查询（已知起点做深度遍历）

工具选择策略（由子智能体 system_prompt 引导）：
    - 简单问题（单文档/单条款）→ knowledge_search
    - 复杂关联（跨文档/法规引用链）→ graph_rag_search
    - 已知起点深度遍历（追踪某法规所有引用）→ graph_query

graph_query 同时被 fire-management-analyst 复用，限定用于故障影响链分析。

当前为 Mock 数据模式，Phase 2 接入 GraphRAG 后替换为真实检索。
"""

from fastmcp import FastMCP


# ============================================================
# Mock 知识检索数据
# ============================================================

_MOCK_KNOWLEDGE_DOCS = [
    {
        "answer": "ICU病房属于一类重点场所，消防系统需满足以下要求：\n"
                  "1. 应设置火灾自动报警系统，采用智能型烟感探测器\n"
                  "2. 应设置自动喷水灭火系统，喷头动作温度宜采用68℃\n"
                  "3. 应设置防排烟系统，排烟量按每小时6次换气计算\n"
                  "4. 电气设备应采用EPS应急电源，切换时间不超过0.5秒\n"
                  "5. 病房门应采用防火门，耐火极限不低于1.0小时\n"
                  "6. 疏散通道宽度不小于1.4米，应设置应急照明和疏散指示标志",
        "source": "GB 50974-2014《消防给水及消火栓系统技术规范》第3.0.2条",
        "score": 0.92,
    },
    {
        "answer": "烟感探测器误报后的复位操作步骤：\n"
                  "1. 确认为误报（现场核实无火灾）\n"
                  "2. 在消防控制室主机上操作复位键\n"
                  "3. 等待主机复位完成（约10-30秒）\n"
                  "4. 确认探测器指示灯恢复正常（绿灯闪烁）\n"
                  "5. 在值班日志中记录误报时间、原因和处理结果\n"
                  "6. 如反复误报，需安排清洁或更换探测器",
        "source": "消防系统操作手册-4.3 报警系统操作规程",
        "score": 0.88,
    },
    {
        "answer": "灭火器按充装灭火剂类型分为以下几种：\n"
                  "1. 水基型灭火器（清水、泡沫）— 适用于A类火灾\n"
                  "2. 干粉灭火器（BC类/ABC类）— 最常用，适用于多种火灾\n"
                  "3. 二氧化碳灭火器 — 适用于B类、C类及电气火灾\n"
                  "4. 洁净气体灭火器 — 适用于精密仪器和电子设备场所\n"
                  "医疗机构推荐配置：ABC干粉灭火器 + 二氧化碳灭火器",
        "source": "GB 50140-2005《建筑灭火器配置设计规范》第4.1节",
        "score": 0.85,
    },
    {
        "answer": "消防巡检模块数据录入操作步骤：\n"
                  "1. 登录消防管理系统，进入「巡检管理」模块\n"
                  "2. 点击「新建巡检任务」，选择巡检区域和巡检模板\n"
                  "3. 填写巡检日期、巡检人员\n"
                  "4. 按模板逐项检查并录入结果（正常/异常/不适用）\n"
                  "5. 异常项需填写异常描述和现场照片\n"
                  "6. 全部检查完毕后提交巡检报告\n"
                  "7. 如有异常项，系统自动生成维修工单",
        "source": "消防系统操作手册-3.1 巡检管理操作规程",
        "score": 0.90,
    },
]

_MOCK_GRAPH_PATHS = {
    "EPS电源-01": {
        "paths": [
            {"start": "EPS电源-01", "end": "喷淋泵-01", "relation": "供电给", "properties": {"供电类型": "主电源"}},
            {"start": "EPS电源-01", "end": "排烟风机-02", "relation": "供电给", "properties": {"供电类型": "主电源"}},
            {"start": "EPS电源-01", "end": "消防广播-03", "relation": "供电给", "properties": {"供电类型": "应急电源"}},
            {"start": "EPS电源-01", "end": "烟感探测器-01", "relation": "供电给", "properties": {"供电类型": "监控电源"}},
            {"start": "喷淋泵-01", "end": "B栋3层分区", "relation": "服务", "properties": {"系统": "自动喷水灭火系统"}},
            {"start": "排烟风机-02", "end": "B栋4层分区", "relation": "服务", "properties": {"系统": "防排烟系统"}},
        ],
        "entities": [
            {"name": "EPS电源-01", "type": "Equipment", "properties": {"category": "电气类", "status": "正常", "location": "A栋配电间"}},
            {"name": "喷淋泵-01", "type": "Equipment", "properties": {"category": "灭火类", "status": "正常", "location": "A栋地下1层"}},
            {"name": "排烟风机-02", "type": "Equipment", "properties": {"category": "通风排烟类", "status": "故障", "location": "B栋4层"}},
            {"name": "B栋3层分区", "type": "Zone", "properties": {"building": "B栋", "floor": "3层", "risk_level": "重点"}},
            {"name": "B栋4层分区", "type": "Zone", "properties": {"building": "B栋", "floor": "4层", "risk_level": "一般"}},
        ],
        "total_paths": 5,
    },
    "ICU病房": {
        "paths": [
            {"start": "ICU病房", "end": "一类重点场所", "relation": "属于分类", "properties": {"risk_level": "一类"}},
            {"start": "一类重点场所", "end": "GB 50974-2014", "relation": "适用法规", "properties": {}},
            {"start": "一类重点场所", "end": "GB 50016-2014", "relation": "适用法规", "properties": {}},
            {"start": "ICU病房", "end": "温感探测器-05", "relation": "安装于", "properties": {"反向": True}},
        ],
        "entities": [
            {"name": "ICU病房", "type": "Zone", "properties": {"building": "A栋", "risk_level": "一类重点"}},
            {"name": "一类重点场所", "type": "ZoneType", "properties": {"risk_level": "一类", "description": "人员密集场所"}},
            {"name": "GB 50974-2014", "type": "Regulation", "properties": {"code": "GB 50974-2014", "name": "消防给水及消火栓系统技术规范"}},
            {"name": "GB 50016-2014", "type": "Regulation", "properties": {"code": "GB 50016-2014", "name": "建筑设计防火规范"}},
            {"name": "温感探测器-05", "type": "Equipment", "properties": {"category": "火灾探测类", "status": "正常"}},
        ],
        "total_paths": 4,
    },
}


def register_knowledge_tools(mcp: FastMCP):
    """注册知识检索工具到 MCP Server"""

    @mcp.tool(name="graph_rag_search")
    async def graph_rag_search(
        query: str,
        search_type: str = "hybrid",
        max_vector_results: int = 5,
        graph_depth: int = 2,
        score_threshold: float = 0.7,
    ) -> dict:
        """
        GraphRAG组合检索：向量检索+图遍历+融合，一键返回完整上下文。
        适用于复杂关联问题（跨文档/法规引用链/设备依赖链）。

        Args:
            query: 检索问题，如"ICU病房消防系统要满足哪些要求"
            search_type: 检索类型，可选：hybrid(默认)/vector_only/graph_only
            max_vector_results: 向量检索结果数量上限，默认5
            graph_depth: 图遍历深度，默认2
            score_threshold: 相似度阈值，默认0.7

        Returns:
            检索结果，包含 answer、sources、score、status
        """
        # TODO: Phase 2 接入 GraphRAG 后替换为真实编排器调用
        # from graph_rag.orchestrator import GraphRAGOrchestrator
        # result = await orchestrator.search(query, search_type, ...)

        # Mock: 简单关键词匹配
        matched_docs = []
        for doc in _MOCK_KNOWLEDGE_DOCS:
            if any(kw in doc["answer"] or kw in doc["source"]
                   for kw in query.split() if len(kw) > 1):
                matched_docs.append(doc)

        # 如果没匹配到，返回最高分的文档
        if not matched_docs:
            matched_docs = sorted(_MOCK_KNOWLEDGE_DOCS, key=lambda d: d["score"], reverse=True)[:2]

        best = matched_docs[0] if matched_docs else _MOCK_KNOWLEDGE_DOCS[0]
        score = best["score"]

        return {
            "answer": best["answer"],
            "sources": [{"type": "document", "title": best["source"], "path": ""}],
            "score": score,
            "status": "success" if score >= score_threshold else "low_score",
        }

    @mcp.tool(name="knowledge_search")
    async def knowledge_search(
        query: str,
        max_results: int = 5,
        score_threshold: float = 0.7,
    ) -> dict:
        """
        纯向量检索。适用于简单问题（单文档/单条款可直接回答）。
        复杂关联问题应使用 graph_rag_search。

        Args:
            query: 检索问题
            max_results: 返回结果数量上限，默认5
            score_threshold: 相似度阈值，默认0.7

        Returns:
            检索结果列表，包含 answer、source、score
        """
        # TODO: Phase 2 接入 Milvus 后替换为真实向量检索

        matched = []
        for doc in _MOCK_KNOWLEDGE_DOCS:
            if any(kw in doc["answer"] or kw in doc["source"]
                   for kw in query.split() if len(kw) > 1):
                matched.append(doc)

        if not matched:
            matched = sorted(_MOCK_KNOWLEDGE_DOCS, key=lambda d: d["score"], reverse=True)[:max_results]

        results = matched[:max_results]
        return {
            "total": len(results),
            "items": results,
        }

    @mcp.tool(name="graph_query")
    async def graph_query(
        entity: str,
        relation_types: list[str] | None = None,
        depth: int = 2,
        direction: str = "outgoing",
    ) -> dict:
        """
        纯图遍历查询。适用于已知起点做深度遍历（追踪某法规所有引用/故障影响链分析）。
        常规数据查询应走 MCP 明细工具。

        Args:
            entity: 起始实体名称，如"EPS电源-01"、"ICU病房"
            relation_types: 限定关系类型，如["依赖","安装于"]，为空则遍历所有关系
            depth: 遍历深度，默认2
            direction: 遍历方向，可选：outgoing(默认)/incoming/both

        Returns:
            图遍历结果，包含 paths 路径列表、entities 关联实体、total_paths
        """
        # TODO: Phase 2 接入 Neo4j 后替换为真实图遍历

        # Mock: 按实体名称匹配
        graph_data = _MOCK_GRAPH_PATHS.get(entity)

        if graph_data:
            paths = graph_data["paths"]
            entities = graph_data["entities"]
            # 按 relation_types 过滤
            if relation_types:
                paths = [p for p in paths if p["relation"] in relation_types]
            return {
                "paths": paths[:depth * 3],
                "entities": entities,
                "total_paths": len(paths),
            }

        # 未知实体返回空结果
        return {
            "paths": [],
            "entities": [],
            "total_paths": 0,
        }
