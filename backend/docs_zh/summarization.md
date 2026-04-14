# 对话总结

DeerFlow 包括自动对话摘要，以处理接近模型令牌限制的长对话。启用后，系统会自动压缩较旧的消息，同时保留最近的上下文。

## 概述

摘要功能使用LangChain的“SummarizationMiddleware”来监控对话历史并根据可配置的阈值触发摘要。激活后，它：

1.实时监控消息令牌计数
2. 达到阈值时触发汇总
3. 保持最近的消息完整，同时总结旧的交流
4. 维护 AI/工具消息对以实现上下文连续性
5. 将摘要重新注入对话中

## 配置

汇总是在“config.yaml”中的“summarization”键下配置的：

```yaml
summarization:
  enabled: true
  model_name: null  # Use default model or specify a lightweight model

  # Trigger conditions (OR logic - any condition triggers summarization)
  trigger:
    - type: tokens
      value: 4000
    # Additional triggers (optional)
    # - type: messages
    #   value: 50
    # - type: fraction
    #   value: 0.8  # 80% of model's max input tokens

  # Context retention policy
  keep:
    type: messages
    value: 20

  # Token trimming for summarization call
  trim_tokens_to_summarize: 4000

  # Custom summary prompt (optional)
  summary_prompt: null
```

### 配置选项

#### `启用`
- **类型**：布尔值
- **默认**：`假`
- **描述**：启用或禁用自动摘要

#### `模型名称`
- **类型**：字符串或 null
- **默认**：`null`（使用默认模型）
- **描述**：用于生成摘要的模型。建议使用轻量级、经济高效的模型，如“gpt-4o-mini”或等效模型。

#### `触发`
- **类型**：单个“ContextSize”或“ContextSize”对象列表
- **必需**：启用时必须至少指定一个触发器
- **描述**：触发摘要的阈值。使用 OR 逻辑 - 当满足任何阈值时运行汇总。

**ContextSize 类型：**

1. **基于令牌的触发器**：当令牌计数达到指定值时激活
   

```yaml
   trigger:
     type: tokens
     value: 4000
   ```

2. **基于消息的触发器**：当消息计数达到指定值时激活
   

```yaml
   trigger:
     type: messages
     value: 50
   ```

3. **基于分数的触发器**：当令牌使用量达到模型最大输入令牌的百分比时激活
   

```yaml
   trigger:
     type: fraction
     value: 0.8  # 80% of max input tokens
   ```

**多个触发器：**

```yaml
trigger:
  - type: tokens
    value: 4000
  - type: messages
    value: 50
```

#### `保留`
- **类型**：`ContextSize` 对象
- **默认**：`{类型：消息，值：20}`
- **描述**：指定摘要后要保留多少最近的对话历史记录。

**示例：**

```yaml
# Keep most recent 20 messages
keep:
  type: messages
  value: 20

# Keep most recent 3000 tokens
keep:
  type: tokens
  value: 3000

# Keep most recent 30% of model's max input tokens
keep:
  type: fraction
  value: 0.3
```

#### `trim_tokens_to_summarize`
- **类型**：整数或空
- **默认**：`4000`
- **描述**：为摘要调用本身准备消息时要包含的最大标记。设置为“null”以跳过修剪（不建议用于很长的对话）。

#### `summary_prompt`
- **类型**：字符串或 null
- **默认**：`null`（使用LangChain的默认提示）
- **描述**：用于生成摘要的自定义提示模板。提示应引导模型提取最重要的上下文。

**默认提示行为：**
默认的 LangChain 提示指示模型：
- 提取最高质量/最相关的上下文
- 关注对总体目标至关重要的信息
- 避免重复已完成的动作
- 仅返回提取的上下文

## 它是如何工作的

### 总结流程

1. **监控**：在每次模型调用之前，中间件都会对消息历史记录中的 token 进行计数
2. **触发检查**：如果满足任何配置的阈值，则触发汇总
3. **消息分区**：消息分为：
   - 要总结的消息（超出“保留”阈值的旧消息）
   - 要保留的消息（“保留”阈值内的最新消息）
4. **摘要生成**：模型生成旧消息的简明摘要
5. **上下文替换**：消息历史记录更新：
   - 所有旧消息均被删除
   - 添加了一条摘要消息
   - 保留最近的消息
6. **AI/工具对保护**：系统确保AI消息与其对应的工具消息保持在一起

### 令牌计数

- 使用基于字符计数的近似令牌计数
- 对于人择模型：每个标记约 3.3 个字符
- 对于其他模型：使用LangChain的默认估计
- 可以使用自定义“token_counter”函数进行定制

### 消息保存

中间件智能地保留消息上下文：

- **最近消息**：基于“keep”配置始终保持完整
- **AI/工具对**：永不分裂 - 如果截止点落在工具消息内，系统会调整以将整个 AI + 工具消息序列保持在一起
- **摘要格式**：摘要作为 HumanMessage 注入，格式如下：
  

```
  Here is a summary of the conversation to date:

  [Generated summary text]
  ```

## 最佳实践

### 选择触发阈值

1. **基于令牌的触发器**：推荐用于大多数用例
   - 设置为模型上下文窗口的 60-80%
   - 示例：对于 8K 上下文，使用 4000-6000 个令牌

2. **基于消息的触发器**：用于控制对话长度
   - 适合有很多短信的应用程序
   - 示例：50-100 条消息，具体取决于平均消息长度

3. **基于分数的触发器**：使用多个模型时的理想选择
   - 自动适应每个型号的容量
   - 示例：0.8（模型最大输入标记的 80%）

### 选择保留策略（`keep`）

1. **基于消息的保留**：最适合大多数场景
   - 保持自然的对话流程
   - 建议：15-25 条消息

2. **基于令牌的保留**：需要精确控制时使用
   - 适合管理精确的代币预算
   - 推荐：2000-4000 代币

3. **基于分数的保留**：适用于多模型设置
   - 根据模型容量自动扩展
   - 建议：0.2-0.4（最大输入的 20-40%）

### 型号选择

- **推荐**：使用轻量级、经济高效的模型进行摘要
  - 示例：`gpt-4o-mini`、`claude-haiku` 或同等内容
  - 摘要不需要最强大的模型
  - 大批量应用可显着节省成本

- **默认**：如果“model_name”为“null”，则使用默认模型
  - 可能更贵但确保一致性
  - 适合简单的设置

### 优化技巧

1. **平衡触发器**：结合令牌和消息触发器以实现稳健的处理
   

```yaml
   trigger:
     - type: tokens
       value: 4000
     - type: messages
       value: 50
   ```

2. **保守保留**：最初保留更多消息，根据性能进行调整
   

```yaml
   keep:
     type: messages
     value: 25  # Start higher, reduce if needed
   ```

3. **策略性修剪**：限制发送到汇总模型的令牌
   

```yaml
   trim_tokens_to_summarize: 4000  # Prevents expensive summarization calls
   ```

4. **监控和迭代**：跟踪摘要质量并调整配置

## 故障排除

### 质量问题总结

**问题**：摘要丢失重要上下文

**解决方案**：
1.增加`keep`值以保留更多消息
2. 降低触发阈值以提早总结
3.自定义`summary_prompt`以强调关键信息
4.使用更强大的模型进行总结

### 性能问题

**问题**：摘要调用花费的时间太长

**解决方案**：
1. 使用更快的模型进行摘要（例如“gpt-4o-mini”）
2. 减少 `trim_tokens_to_summarize` 以发送更少的上下文
3. 提高触发阈值以减少汇总频率

### 令牌限制错误

**问题**：尽管进行了总结，但仍然达到了代币限制

**解决方案**：
1. 降低触发阈值，提早总结
2. 减少“keep”值以保留更少的消息
3. 检查单条消息是否很大
4.考虑使用基于分数的触发器

## 实施细节

### 代码结构

- **配置**：`packages/harness/deerflow/config/summarization_config.py`
- **集成**：`packages/harness/deerflow/agents/lead_agent/agent.py`
- **中间件**：使用 `langchain.agents.middleware.SummarizationMiddleware`

### 中间件顺序

摘要在 ThreadData 和 Sandbox 初始化之后但在 Title 和 Clarification 之前运行：

1.ThreadData中间件
2.沙箱中间件
3. **SummarizationMiddleware** ← 在这里运行
4.标题中间件
5.澄清中间件

### 状态管理

- 摘要是无状态的 - 配置在启动时加载一次
- 摘要作为常规消息添加到对话历史记录中
- 检查点自动保存总结的历史记录

## 配置示例

### 最低配置

```yaml
summarization:
  enabled: true
  trigger:
    type: tokens
    value: 4000
  keep:
    type: messages
    value: 20
```

### 生产配置

```yaml
summarization:
  enabled: true
  model_name: gpt-4o-mini  # Lightweight model for cost efficiency
  trigger:
    - type: tokens
      value: 6000
    - type: messages
      value: 75
  keep:
    type: messages
    value: 25
  trim_tokens_to_summarize: 5000
```

### 多模型配置

```yaml
summarization:
  enabled: true
  model_name: gpt-4o-mini
  trigger:
    type: fraction
    value: 0.7  # 70% of model's max input
  keep:
    type: fraction
    value: 0.3  # Keep 30% of max input
  trim_tokens_to_summarize: 4000
```

### 保守配置（高品质）

```yaml
summarization:
  enabled: true
  model_name: gpt-4  # Use full model for high-quality summaries
  trigger:
    type: tokens
    value: 8000
  keep:
    type: messages
    value: 40  # Keep more context
  trim_tokens_to_summarize: null  # No trimming
```

## 参考文献

- [LangChain 汇总中间件文档](https://docs.langchain.com/oss/python/langchain/middleware/built-in#summarization)
- [LangChain源代码](https://github.com/langchain-ai/langchain)