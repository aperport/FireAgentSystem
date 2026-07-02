"""
RAGAS 质量评估模块 — 对 GraphRAG 生成的回答进行质量评估。

✅ 主体逻辑已实现。评估指标：
    1. Faithfulness（忠实度）：回答是否完全基于上下文，是否编造
    2. AnswerRelevancy（答案相关性）：回答是否切题、完整
    3. ContextPrecision（上下文精确率）：检索内容与问题的相关性
    4. ContextRecall（上下文召回率）：是否检索到足够信息
    5. AnswerCorrectness（回答正确性）：与标准答案的对比

    忠实度和答案相关性侧重点不同：
    - 忠实度关注模型是否严格遵循上下文
    - 答案相关性关注模型是否直接、完整且有效地回答了问题

评估结果处理：
    - score ≥ 0.7：通过，直接输出
    - score < 0.7：不达标
        - 人工审批模式 → approve/reject
        - 自动模式 → 返回"知识库暂未收录该内容的完整答案"

已实现方法：
    - load_evaluation_data()  加载 JSON 评估数据集
    - run_evaluation()        运行 RAGAS 五项指标评估
    - print_results()         打印格式化评估报告
    - save_results()          保存 CSV + JSON 摘要

⚠️ 已知问题：
    1. Embedding 模型硬编码为 BAAI/bge-small-zh-v1.5 + cuda，
       应从 config.py 读取

由 orchestrator.py 在 LLM 生成回答后调用（当前未接入）。

待优化：
    - 接入 orchestrator 的评估流程
    - 增量评估：仅评估新增数据，避免全量重跑
"""


import json
import os
from datetime import datetime

import pandas as pd
from datasets import Dataset
from ragas import evaluate, RunConfig
from ragas.metrics import (
    Faithfulness,
    AnswerRelevancy,
    ContextPrecision,
    ContextRecall,
    AnswerCorrectness,
)

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from agent.llm_config import DeepSeek_LLM
from util_tools.logger import get_logger


logger = get_logger(__name__)
class RAGASEvaluator:
    def __init__(self,json_file_path: str) -> None:
        self.model_name : str = "BAAI/bge-small-zh-v1.5"
        self.embeddings: HuggingFaceEmbeddings|None = None
        self.llm : ChatOpenAI = DeepSeek_LLM
        self.json_file_path : str = json_file_path

    def load_evaluation_data(self):
        """
        加载评估数据集
        数据格式要求：
            - question: 检索问题
            - contexts: 检索到的上下文
            - answer: 生成的回答
            - references: 参考答案
        """
        with open(self.json_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"加载评估数据集,数据量：{len(data)}")

        return data
    
    def run_evaluation(self):
        """
        运行评估
        """
        logger.info("开始评估")
        self.embeddings = HuggingFaceEmbeddings(model_name=self.model_name,
                                        model_kwargs={"device": "cuda"},
                                        encode_kwargs={"normalize_embeddings": True})
        # 1. 加载数据
        eval_data = self.load_evaluation_data()
        dataset = Dataset.from_list(eval_data)
        # 2. 配置评估指标
        metrics = [
        Faithfulness(),      # 忠实度：答案是否基于上下文
        AnswerRelevancy(),   # 回答相关性：答案与问题的匹配度
        ContextPrecision(),  # 上下文精确率：检索内容的相关性
        ContextRecall(),     # 上下文召回率：是否检索到足够信息
        AnswerCorrectness()  # 回答正确性：与标准答案的对比
    ]

        # 3. 配置运行参数（避免请求过载）
        run_config = RunConfig(
            max_workers=1,      # 单线程执行（中转站建议）
            max_retries=3,      # 失败重试次数
            timeout=60          # 单次请求超时时间
        )

        # 4. 运行评估
        logger.info("开始评估")
        results = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=self.llm,
            embeddings=self.embeddings,
            run_config=run_config,
            show_progress=True,         # 显示进度条
            raise_exceptions=False      # 不抛出异常,报错继续执行
        )
        logger.info("评估完成")

        # 5. 输出评估结果与可视化
        df = results.to_pandas()

        # 合并原始数据便于查看
        o_df = pd.DataFrame(eval_data)
        df = pd.concat([o_df, df], axis=1)

        # 打印结果
        self.print_results(df)
        # 保存结果
        self.save_results(df)
        return results
    
    def print_results(self,df: pd.DataFrame):
        """
        打印格式化的评估报告
        """
        metric_cols = [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
        ]

        # 汇总各指标均值
        print("\n" + "=" * 60)
        print("RAGAS 评估报告")
        print("=" * 60)

        available_metrics = [c for c in metric_cols if c in df.columns]
        if available_metrics:
            print("\n【各指标均值】")
            for col in available_metrics:
                mean_val = df[col].mean()
                status = "通过" if mean_val >= 0.7 else "未达标"
                print(f"  {col:25s}  {mean_val:.4f}  [{status}]")

            overall = df[available_metrics].mean().mean()
            overall_status = "通过" if overall >= 0.7 else "未达标"
            print(f"\n  {'总体得分':25s}  {overall:.4f}  [{overall_status}]")
        else:
            print("  未找到 RAGAS 指标列，仅展示原始数据")

        # 逐条低分样本
        if available_metrics:
            low_score_rows = df[
                df[available_metrics].mean(axis=1) < 0.7
            ]
            if not low_score_rows.empty:
                print(f"\n【低分样本（均值 < 0.7）：共 {len(low_score_rows)} 条】")
                for idx, row in low_score_rows.iterrows():
                    print(f"\n  --- 样本 {idx} ---")
                    if "question" in row:
                        print(f"  问题: {row['question']}")
                    for col in available_metrics:
                        print(f"  {col}: {row[col]:.4f}" if pd.notna(row[col]) else f"  {col}: N/A")

        print("\n" + "=" * 60)

    def save_results(self,df: pd.DataFrame):
        """
        保存评估结果
        """
        input_dir = os.path.dirname(self.json_file_path) or "."
        result_dir = os.path.join(input_dir, "eval_results")
        os.makedirs(result_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(self.json_file_path))[0]

        csv_path = os.path.join(result_dir, f"{base_name}_{timestamp}.csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.info(f"评估结果已保存至 {csv_path}")

        metric_cols = [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
        ]
        available_metrics = [c for c in metric_cols if c in df.columns]
        if available_metrics:
            summary = {
                "timestamp": timestamp,
                "source_file": self.json_file_path,
                "total_samples": len(df),
                "metrics": {
                    col: {
                        "mean": round(float(df[col].mean()), 4),
                        "min": round(float(df[col].min()), 4),
                        "max": round(float(df[col].max()), 4),
                    }
                    for col in available_metrics
                },
                "overall_mean": round(float(df[available_metrics].mean().mean()), 4),
                "pass": bool(df[available_metrics].mean().mean() >= 0.7),
            }
            json_path = os.path.join(result_dir, f"{base_name}_{timestamp}_summary.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            logger.info(f"评估摘要已保存至 {json_path}")

        return result_dir

    