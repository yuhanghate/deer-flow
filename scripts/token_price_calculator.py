#!/usr/bin/env python3
"""Token 费用计算脚本（按模型单价计算输入/输出成本）"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass


TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class ModelPrice:
    name: str
    input_price_per_million: float
    output_price_per_million: float
    cached_input_price_per_million: float | None = None
    cache_write_price_per_million: float | None = None
    cache_read_price_per_million: float | None = None


MODEL_PRICES: dict[str, ModelPrice] = {
    "kimi2.5-pro": ModelPrice(
        name="kimi2.5-pro",
        input_price_per_million=4.0,
        output_price_per_million=21.0,
        cached_input_price_per_million=0.8,
        cache_write_price_per_million=5.0,
        cache_read_price_per_million=0.4,
    ),
    # glm-5 系列按当前截图价格配置
    "glm-5": ModelPrice(
        name="glm-5",
        input_price_per_million=6.0,
        output_price_per_million=24.0,
        cached_input_price_per_million=1.2,
        cache_write_price_per_million=7.5,
        cache_read_price_per_million=0.6,
    ),
    "glm-5.1": ModelPrice(
        name="glm-5.1",
        input_price_per_million=6.0,
        output_price_per_million=24.0,
        cached_input_price_per_million=1.2,
        cache_write_price_per_million=7.5,
        cache_read_price_per_million=0.6,
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="根据输入/输出 token 计算模型调用费用（元）"
    )
    parser.add_argument(
        "--model",
        choices=sorted(MODEL_PRICES.keys()),
        help="模型名称，不传则进入交互选择",
    )
    parser.add_argument(
        "--input-tokens",
        type=str,
        help="输入 token 数，支持 573000 / 573K / 0.573M，不传则交互输入",
    )
    parser.add_argument(
        "--output-tokens",
        type=str,
        help="输出 token 数，支持 12800 / 12.8K / 0.0128M，不传则交互输入",
    )
    return parser.parse_args()


def ask_model(default_model: str = "kimi2.5-pro") -> str:
    model_names = sorted(MODEL_PRICES.keys())
    print("可选模型：")
    for idx, model_name in enumerate(model_names, start=1):
        print(f"  {idx}. {model_name}")
    raw = input(f"请输入模型编号或模型名（默认 {default_model}）: ").strip()
    if not raw:
        return default_model
    if raw.isdigit():
        model_index = int(raw)
        if 1 <= model_index <= len(model_names):
            return model_names[model_index - 1]
        raise ValueError(f"模型编号超出范围：{raw}")
    if raw not in MODEL_PRICES:
        raise ValueError(f"不支持的模型：{raw}")
    return raw


def parse_token_text(raw: str) -> float:
    text = raw.strip().replace(",", "")
    match = re.fullmatch(r"([0-9]*\.?[0-9]+)\s*([kKmM]?)", text)
    if not match:
        raise ValueError(f"无法识别的 token 格式：{raw}")

    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "k":
        value *= 1_000
    elif unit == "m":
        value *= TOKENS_PER_MILLION

    if value < 0:
        raise ValueError("token 数不能为负数")
    return value


def ask_positive_number(prompt: str) -> float:
    raw = input(prompt).strip()
    return parse_token_text(raw)


def calculate_cost(tokens: float, price_per_million: float) -> float:
    return tokens / TOKENS_PER_MILLION * price_per_million


def main() -> int:
    args = parse_args()

    try:
        model_name = args.model or ask_model()
        input_tokens = (
            parse_token_text(args.input_tokens)
            if args.input_tokens is not None
            else ask_positive_number("请输入输入 token 数: ")
        )
        output_tokens = (
            parse_token_text(args.output_tokens)
            if args.output_tokens is not None
            else ask_positive_number("请输入输出 token 数: ")
        )
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token 数不能为负数")
    except ValueError as exc:
        print(f"参数错误：{exc}")
        return 1

    model = MODEL_PRICES[model_name]
    input_cost = calculate_cost(input_tokens, model.input_price_per_million)
    output_cost = calculate_cost(output_tokens, model.output_price_per_million)
    total_cost = input_cost + output_cost

    print("\n=== 价格配置 ===")
    print(f"模型: {model.name}")
    print(f"输入单价: {model.input_price_per_million:.4f} 元 / 1M tokens")
    print(f"输出单价: {model.output_price_per_million:.4f} 元 / 1M tokens")
    if model.cached_input_price_per_million is not None:
        print(f"输入(缓存命中)单价: {model.cached_input_price_per_million:.4f} 元 / 1M tokens")
    if model.cache_write_price_per_million is not None:
        print(f"显式缓存创建单价: {model.cache_write_price_per_million:.4f} 元 / 1M tokens")
    if model.cache_read_price_per_million is not None:
        print(f"显式缓存命中单价: {model.cache_read_price_per_million:.4f} 元 / 1M tokens")
    print(
        f"折合输入单价: {model.input_price_per_million / TOKENS_PER_MILLION:.10f} 元 / token"
    )
    print(
        f"折合输出单价: {model.output_price_per_million / TOKENS_PER_MILLION:.10f} 元 / token"
    )

    print("\n=== 本次使用量 ===")
    print(f"输入 tokens: {input_tokens:,.0f}")
    print(f"输出 tokens: {output_tokens:,.0f}")

    print("\n=== 费用明细 ===")
    print(f"输入费用: {input_cost:.6f} 元")
    print(f"输出费用: {output_cost:.6f} 元")
    print(f"总费用:   {total_cost:.6f} 元")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
