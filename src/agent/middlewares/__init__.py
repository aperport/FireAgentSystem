"""
中间件集合 — 消防后勤智能助手的 Agent 生命周期钩子链。

当前中间件（5个，按执行顺序）：
    1. ContextInjectionMiddleware  — 用户信息注入 SystemMessage (before_agent)
    2. MemoryUpdateMiddleware      — 自动提取关键词更新用户偏好 (aafter_agent)
    3. ToolSummarizationMiddleware — 上下文过长时自动摘要压缩 (自动触发)
    4. ModelCallLimitMiddleware    — 限制模型调用次数 (框架内置)
    5. ToolCallLimitMiddleware     — 限制工具调用次数 (框架内置)

已移除：
    - SkillsSyncMiddleware       — 新项目子智能体不使用静态 skills 文件
    - UserSkillsRestoreMiddleware — 原项目已标注取消实现
"""
