"""
成本计算工具

成本涉及非常小的数字（例如每百万 tokens $0.15），用 float 累加会产生精度丢失，
因此统一使用 Decimal，并保留 6 位小数与数据库 DECIMAL(10, 6) 精度对齐。
"""

from decimal import Decimal
from typing import Optional

# 价格单位：每百万 tokens 的美元价格
TOKEN_UNIT = Decimal("1000000")

# 成本保留小数位，与数据库 DECIMAL(10, 6) 一致
COST_PRECISION = Decimal("0.000001")


class CostCalculator:
    """Token 估算与成本计算"""

    @staticmethod
    def estimate_tokens(text: Optional[str]) -> int:
        """
        估算文本的 Token 数量

        流式响应过程中拿不到精确的 usage（要等流结束才有），所以先用估算值做实时展示。
        估算规则：中日韩字符按 1 字符 ≈ 1 token，其余字符按 4 字符 ≈ 1 token。

        Args:
            text: 待估算的文本

        Returns:
            估算出来的 Token 数
        """
        if not text:
            return 0

        cjk_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        other_count = len(text) - cjk_count
        return cjk_count + (other_count + 3) // 4

    @staticmethod
    def calculate_cost(
        model_name: str,
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        input_price: Optional[Decimal] = None,
        output_price: Optional[Decimal] = None,
    ) -> Decimal:
        """
        计算调用成本（USD）

        Args:
            model_name: 模型名称（仅用于日志与兜底，不参与计算）
            input_tokens: 输入 Token 数
            output_tokens: 输出 Token 数
            input_price: 输入价格（每百万 tokens，美元）
            output_price: 输出价格（每百万 tokens，美元）

        Returns:
            成本金额，保留 6 位小数
        """
        if input_price is None and output_price is None:
            return Decimal("0").quantize(COST_PRECISION)

        safe_input_price = Decimal(str(input_price)) if input_price is not None else Decimal("0")
        safe_output_price = Decimal(str(output_price)) if output_price is not None else Decimal("0")

        input_cost = (Decimal(str(input_tokens or 0)) / TOKEN_UNIT) * safe_input_price
        output_cost = (Decimal(str(output_tokens or 0)) / TOKEN_UNIT) * safe_output_price

        return (input_cost + output_cost).quantize(COST_PRECISION)
