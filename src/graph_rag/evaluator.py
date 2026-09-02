"""
RAGAS 质量评估模块 — 对 GraphRAG 生成的回答进行质量评估。

"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Protocol
import yaml

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
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from graph_rag.config import get_settings
from util_tools.logger import get_logger


logger = get_logger(__name__)


class RAGASEvaluation(Protocol):
    def __init__(self) :
        ...

    def run_evaluation(self):
        ...

    def load_evaluation_data(self) -> dict:
        ...


class ReferenceFreeEvaluation:
    """
    无需人工标注答案，根据模型生成的结果进行评估，需要大模型实现评估
    """
    def __init__(self,reference_free_yaml:Path,llm: BaseChatModel | None = None) :
        """
        args:
            reference_free_yaml: yaml文件路径,无标注数据。
            llm: 大语言模型
        """
        self.test_data_path = reference_free_yaml
        self.llm = llm or ChatOpenAI(model="deepseek-chat")

    def load_evaluation_data(self) -> dict:
        """
        从yaml文件中读取数据集，字典形式。
        """
        with open(self.test_data_path,"r",encoding="utf-8") as f:
            evaluation_data = yaml.safe_load(f)
        if not evaluation_data:
            raise ValueError("未读取到yaml数据，请检查地址是否正确")
        return evaluation_data
        

    def run_evaluation(self):
        """
        运行无标注评估
        """
        logger.info("开始评估")
        # 加载数据
        eval_data_dict = self.load_evaluation_data()
        eval_data = eval_data_dict["data"]
        dataset = Dataset.from_list(eval_data)
        # 配置评估指标
        metrics = [
            Faithfulness(),      # 忠实度：答案是否基于上下文
            AnswerRelevancy(),   # 回答相关性：答案与问题的匹配度
        ]

        # 运行评估
        logger.info("开始评估")
        results = evaluate(
            dataset=dataset,
            llm=self.llm,
            metrics=metrics,
            show_progress=True,         # 显示进度条
            raise_exceptions=False      # 不抛出异常，报错继续执行
            )
        logger.info("评估完成")
        df_results = pd.DataFrame(results)      # 将评估结果转换为DataFrame
        return df_results


class ReferenceBasedEvaluation:
    """
    需要人工标注答案。
    """

    def __init__(self,reference_base_yaml:Path,llm: BaseChatModel | None = None) :
        """
        args:
            reference_base_yaml: yaml文件路径
            llm: 大语言模型
        """ 
        s = get_settings()
        self.model_name: str = s.embedding_model_name
        self.test_data_path = reference_base_yaml
        self.llm = llm or ChatOpenAI(model="deepseek-chat")

    def load_evaluation_data(self) -> dict:
        """
        从yaml文件中读取数据集，字典形式。
        """
        with open(self.test_data_path,"r",encoding="utf-8") as f:
            evaluation_data = yaml.safe_load(f)
        if not evaluation_data:
            raise ValueError("未读取到yaml数据，请检查地址是否正确")
        return evaluation_data

    def run_evaluation(self):
        """
        运行评估
        """
        logger.info("开始评估")
        s = get_settings()                      # 获取全局配置
        self.embeddings = HuggingFaceEmbeddings(model_name=self.model_name,
                                                model_kwargs={"device": s.embedding_device},
                                                encode_kwargs={"normalize_embeddings": True})
        # 加载数据
        eval_data_dict = self.load_evaluation_data()
        dataset = Dataset.from_dict(eval_data_dict)
        # 配置评估指标
        metrics = [
            Faithfulness(),      # 忠实度：答案是否基于上下文
            AnswerRelevancy(),   # 回答相关性：答案与问题的匹配度
            ContextPrecision(),  # 上下文精确率：检索内容的相关性
            ContextRecall(),     # 上下文召回率：是否检索到足够信息
            AnswerCorrectness()  # 回答正确性：与标准答案的对比
        ]
        # 配置运行参数（避免请求过载）
        run_config = RunConfig(
            max_workers=1,      # 单线程执行（中转站建议）
            max_retries=3,      # 失败重试次数
            timeout=60          # 单次请求超时时间
        )
        # 运行评估
        logger.info("开始评估")
        results = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=self.llm,
            embeddings=self.embeddings,
            run_config=run_config,
            show_progress=True,         # 显示进度条
            raise_exceptions=False      # 不抛出异常，报错继续执行
            )
        logger.info("评估完成")
        df_result = results.to_pandas()
        return df_result

    
class RAGASResult:
    def __init__(self, results, json_file_path) :
        """
        args:
            results: 评估结果,pd.DataFrame类型
            json_file_path: json文件路径
        """
        self.results = results
        self.json_file_path: str = json_file_path

    def print_result(self):
        """
        保存评估结果
        """
        input_dir = os.path.dirname(self.json_file_path) or "."
        result_dir = os.path.join(input_dir, "eval_results")
        os.makedirs(result_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(self.json_file_path))[0]

        csv_path = os.path.join(result_dir, f"{base_name}_{timestamp}.csv")
        self.results.to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.info(f"评估结果已保存至 {csv_path}")

        metric_cols = [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
        ]
        available_metrics = [c for c in metric_cols if c in self.results.columns]
        if available_metrics:
            summary = {
                "timestamp": timestamp,
                "source_file": self.json_file_path,
                "total_samples": len(self.results),
                "metrics": {
                    col: {
                        "mean": round(float(self.results[col].mean()), 4),
                        "min": round(float(self.results[col].min()), 4),
                        "max": round(float(self.results[col].max()), 4),
                    }
                    for col in available_metrics
                },
                "overall_mean": round(float(self.results[available_metrics].mean().mean()), 4),
                "pass": bool(self.results[available_metrics].mean().mean() >= 0.7),
            }
            json_path = os.path.join(result_dir, f"{base_name}_{timestamp}_summary.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            logger.info(f"评估摘要已保存至 {json_path}")

        return result_dir

    def save_result(self, result_dir):
        """
        保存评估结果
        """
        input_dir = os.path.dirname(self.json_file_path) or "."
        result_dir = os.path.join(input_dir, "eval_results")
        os.makedirs(result_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(self.json_file_path))[0]

        csv_path = os.path.join(result_dir, f"{base_name}_{timestamp}.csv")
        self.results.to_csv(csv_path, index=False, encoding="utf-8-sig")
        logger.info(f"评估结果已保存至 {csv_path}")

        metric_cols = [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
        ]
        available_metrics = [c for c in metric_cols if c in self.results.columns]
        if available_metrics:
            summary = {
                "timestamp": timestamp,
                "source_file": self.json_file_path,
                "total_samples": len(self.results),
                "metrics": {
                    col: {
                        "mean": round(float(self.results[col].mean()), 4),
                        "min": round(float(self.results[col].min()), 4),
                        "max": round(float(self.results[col].max()), 4),
                    }
                    for col in available_metrics
                },
                "overall_mean": round(float(self.results[available_metrics].mean().mean()), 4),
                "pass": bool(self.results[available_metrics].mean().mean() >= 0.7),
            }
            json_path = os.path.join(result_dir, f"{base_name}_{timestamp}_summary.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            logger.info(f"评估摘要已保存至 {json_path}")

        return result_dir