"""
RAGAS 质量评估模块 — 对 GraphRAG 生成的回答进行质量评估。

评估指标：
    1. ContextRelevance：检索到的上下文是否与问题相关
    2. ResponseRelevancy：生成的回答是否切题

评估结果处理：
    - score ≥ 0.7：通过，直接输出
    - score < 0.7：不达标
        - 人工审批模式 → approve/reject
        - 自动模式 → 返回"知识库暂未收录该内容的完整答案"

由 orchestrator.py 在 LLM 生成回答后调用。
"""
