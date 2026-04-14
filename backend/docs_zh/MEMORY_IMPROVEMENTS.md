# 内存系统改进

本文档跟踪内存注入行为和路线图状态。

## 状态（截至 2026 年 3 月 10 日）

在`main`中实现：
- 通过“format_memory_for_injection”中的“tiktoken”进行准确的令牌计数。
- 事实被注入提示记忆上下文中。
- 事实按置信度排名（降序）。
- 注入遵循“max_injection_tokens”预算。

计划/尚未合并：
- 基于 TF-IDF 相似性的事实检索。
- 用于上下文感知评分的“current_context”输入。
- 可配置的相似性/置信度权重（“similarity_weight”、“confidence_weight”）。
- 在每次模型调用之前进行上下文感知检索的中间件/运行时连接。

## 当前行为

今天的功能：

```python
def format_memory_for_injection(memory_data: dict[str, Any], max_tokens: int = 2000) -> str:
```

当前注入格式：
- 来自“user.*.summary”的“用户上下文”部分
- “history.*.summary”中的“History”部分
- 来自“facts[]”的“Facts”部分，按置信度排序，附加到达到代币预算

令牌计数：
- 在可用时使用“tiktoken”（“cl100k_base”）
- 如果分词器导入失败，则返回到 `len(text) // 4`

## 已知差距

本文档的先前版本描述了 TF-IDF/上下文感知检索，就像它已经发布一样。
这对于“main”来说并不准确，并引起了混乱。

问题参考：`#1059`

## 路线图（计划）

计划评分策略：

```text
final_score = (similarity * 0.6) + (confidence * 0.4)
```

计划整合形状：
1. 从过滤后的用户/最终助理轮次中提取最近的对话上下文。
2. 计算每个事实与当前上下文之间的 TF-IDF 余弦相似度。
3. 按加权分数排名并在代币预算下注入。
4. 如果上下文不可用，则退回到仅置信排名。

## 验证

当前的回归范围包括：
- 事实包含在内存注入输出中
- 信心订购
- 代币预算有限的事实包含

测试：
-`后端/测试/test_memory_prompt_injection.py`