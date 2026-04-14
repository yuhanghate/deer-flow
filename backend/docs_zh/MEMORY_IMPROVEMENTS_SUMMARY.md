# 内存系统改进 - 摘要

## 同步笔记 (2026-03-10)

此摘要与“main”分支实现同步。
TF-IDF/上下文感知检索已**计划**，尚未合并。

## 已实施

- 在内存注入中使用“tiktoken”进行准确的令牌计数。
- 事实被注入到“<内存>”提示内容中。
- 事实按置信度排序，并以“max_injection_tokens”为界。

## 计划中（尚未合并）

- 基于最近对话上下文的 TF-IDF 余弦相似度召回。
- “format_memory_for_injection”的“current_context”参数。
- 加权排名（“相似性”+“置信度”）。
- 用于上下文感知事实选择的运行时提取/注入流程。

## 为什么需要同步

早期文档将 TF-IDF 行为描述为已实现，但与“main”中的代码不匹配。
这种不匹配在问题“#1059”中进行了跟踪。

## 当前 API 形状

```python
def format_memory_for_injection(memory_data: dict[str, Any], max_tokens: int = 2000) -> str:
```

当前“main”中没有可用的“current_context”参数。

## 验证指针

- 实现：`packages/harness/deerflow/agents/memory/prompt.py`
- 提示组件：`packages/harness/deerflow/agents/lead_agent/prompt.py`
- 回归测试：`backend/tests/test_memory_prompt_injection.py`