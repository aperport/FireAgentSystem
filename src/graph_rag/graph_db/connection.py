"""
Neo4j 连接管理 — 管理 Neo4j 驱动的连接池与会话生命周期。

功能：
    - 初始化 Neo4j Driver（连接池配置）
    - 获取同步/异步 Session
    - 连接健康检查
    - 优雅关闭（lifespan 管理）

统一驱动：Neo4jDriver（内部同时持有同步与异步两个 Driver 实例）

配置来源：graph_rag/config.py（NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD）

使用方式：
    # 同步
    from graph_rag.graph_db.connection import Neo4jDriver
    driver = Neo4jDriver(uri, user, password)
    with driver.get_session() as session:
        result = session.run(cypher_query)

    # 异步
    async with await driver.get_async_session() as session:
        result = await session.run(cypher_query)
"""
from util_tools.logger import get_logger
from neo4j import GraphDatabase, AsyncGraphDatabase

logger = get_logger(__name__)


# 下面的数据类定义了 Neo4j 的节点和关系的数据结构，在查询时使用，与sql不同，图数据库更关注关系，而非字段，
# 所以节点和关系的数据结构是不同的，查询时先找标签，再找属性，之后靠关系
# @dataclass
# class Graphnode:
#     # Neo4j 节点数据结构
#     node_id : str
#     labels : str
#     properties : dict[str,Any]
#     name : str

# @dataclass
# class GraphRelation:
#     """图关系数据结构"""
#     start_node_id: str
#     end_node_id: str
#     relation_type: str
#     properties: dict[str, Any]

class Neo4jDrivers:
    """Neo4j 驱动（同时支持同步与异步 Session）

    内部持有两个独立的 Driver 实例：
        - _sync_driver  → GraphDatabase.driver()   → 同步 Session
        - _async_driver → AsyncGraphDatabase.driver() → 异步 Session

    按需懒初始化，未调用对应方法时不创建驱动。
    """

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        """
        初始化数据库连接
        args:
            uri: Neo4j 连接 URI
            user: Neo4j 用户名
            password: Neo4j 密码
            database: Neo4j 数据库名称
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self._sync_driver = None
        self._async_driver = None

    # ──────────────── 同步 API ────────────────

    def _get_sync_driver(self):
        """懒初始化同步驱动"""
        if not self._sync_driver:
            self._sync_driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                database=self.database,
            )
            logger.info("Neo4j 同步驱动已创建")
        return self._sync_driver

    def get_session(self):
        """获取同步 Session（配合 with 使用）

        用法:
            with driver.get_session() as session:
                result = session.run("RETURN 1")
        """
        return self._get_sync_driver().session(database=self.database)

    def verify_connectivity(self):
        """同步连接健康检查"""
        with self._get_sync_driver().session(database=self.database) as session:
            result = session.run("RETURN 1 as TEST")
            if result:
                logger.info("Neo4j 同步连接测试成功")

    # ──────────────── 异步 API ────────────────

    async def _get_async_driver(self):
        """懒初始化异步驱动"""
        if not self._async_driver:
            self._async_driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                database=self.database,
            )
            logger.info("Neo4j 异步驱动已创建")
        return self._async_driver

    async def get_async_session(self):
        """获取异步 Session（配合 async with 使用）

        用法:
            async with await driver.get_async_session() as session:
                result = await session.run("RETURN 1")
        """
        driver = await self._get_async_driver()
        return driver.session(database=self.database)

    async def verify_connectivity_async(self):
        """异步连接健康检查"""
        driver = await self._get_async_driver()
        async with driver.session(database=self.database) as session:
            result = await session.run("RETURN 1 as TEST")
            if result:
                logger.info("Neo4j 异步连接测试成功")

    # ──────────────── 生命周期 ────────────────

    def close(self):
        """同步关闭所有驱动"""
        if self._sync_driver:
            self._sync_driver.close()
            logger.info("Neo4j 同步驱动已关闭")
            self._sync_driver = None

    async def close_async(self):
        """异步关闭所有驱动"""
        if self._sync_driver:
            self._sync_driver.close()
            logger.info("Neo4j 同步驱动已关闭")
            self._sync_driver = None
        if self._async_driver:
            await self._async_driver.close()
            logger.info("Neo4j 异步驱动已关闭")
            self._async_driver = None

