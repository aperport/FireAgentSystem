"""
技能恢复中间件(不一定有啥用，主要处理防止沙箱崩溃重启后技能可用)

在每个 Agent 运行周期开始前，将 StoreBackend 中持久化的技能
恢复到沙箱 /skills/{scope}/{skill_name}/ 路径下，使子 Agent 可以通过
渐进式披露发现和使用。

与 SkillsSyncMiddleware 分工：
  - SkillsSyncMiddleware: 本地 src/skills/ → 沙箱（预置技能）
  - UserSkillsRestoreMiddleware: StoreBackend → 沙箱（持久化技能）
"""