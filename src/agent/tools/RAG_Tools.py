

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("name")

@mcp.tool()
def graph_rag_search(query:str):
    """
    图检索加向量检索，适用于复杂且需要多路径推理的问题。（例如：法规文件与实际案例的关联分析、多个数据源的综合判断）
    args:
        query:检索问题
    """

    return

@mcp.tool()
def knowledge_search(query:str):
    """
    纯向量检索，适用于简单直接的问题（单一条款、定义、规程），不需要多路径推理。
    args:
        query:检索问题
    """
    return

@mcp.tool()
def graph_query(query:str):
    """
    纯图遍历查询，适用于已知关键点的深度调取。（例如：列出某法规的所有引用、故障影响链分析）
    args:
        query:检索问题
    """
    return
