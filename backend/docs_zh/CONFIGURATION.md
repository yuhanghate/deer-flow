# 配置指南

本指南介绍如何为您的环境配置 DeerFlow。

## 配置版本控制

`config.example.yaml` 包含一个跟踪架构更改的 `config_version` 字段。当示例版本高于本地“config.yaml”时，应用程序会发出启动警告：

```
WARNING - Your config.yaml (version 0) is outdated — the latest version is 1.
Run `make config-upgrade` to merge new fields into your config.
```

- **配置中缺少 `config_version`** 将被视为版本 0。
- 运行“make config-upgrade”以自动合并丢失的字段（保留现有值，创建“.bak”备份）。
- 更改配置架构时，在“config.example.yaml”中修改“config_version”。

## 配置部分

### 模型

配置代理可用的 LLM 模型：

```yaml
models:
  - name: gpt-4                    # Internal identifier
    display_name: GPT-4            # Human-readable name
    use: langchain_openai:ChatOpenAI  # LangChain class path
    model: gpt-4                   # Model identifier for API
    api_key: $OPENAI_API_KEY       # API key (use env var)
    max_tokens: 4096               # Max tokens per request
    temperature: 0.7               # Sampling temperature
```

**支持的提供商**：
- OpenAI (`langchain_openai:ChatOpenAI`)
- 人类 (`langchain_anthropic:ChatAnthropic`)
- DeepSeek (`langchain_deepseek:ChatDeepSeek`)
- 克劳德代码 OAuth (`deerflow.models.claude_provider:ClaudeChatModel`)
- Codex CLI (`deerflow.models.openai_codex_provider:CodexChatModel`)
- 任何兼容 LangChain 的提供商

CLI 支持的提供商示例：

```yaml
models:
  - name: gpt-5.4
    display_name: GPT-5.4 (Codex CLI)
    use: deerflow.models.openai_codex_provider:CodexChatModel
    model: gpt-5.4
    supports_thinking: true
    supports_reasoning_effort: true

  - name: claude-sonnet-4.6
    display_name: Claude Sonnet 4.6 (Claude Code OAuth)
    use: deerflow.models.claude_provider:ClaudeChatModel
    model: claude-sonnet-4-6
    max_tokens: 4096
    supports_thinking: true
```

**CLI 支持的提供商的身份验证行为**：
- `CodexChatModel` 从 `~/.codex/auth.json` 加载 Codex CLI 身份验证
- Codex 响应端点当前拒绝“max_tokens”和“max_output_tokens”，因此“CodexChatModel”不会公开请求级别的令牌上限
- `ClaudeChatModel` 接受 `CLAUDE_CODE_OAUTH_TOKEN`、`ANTHROPIC_AUTH_TOKEN`、`CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`、`CLAUDE_CODE_CREDENTIALS_PATH` 或纯文本 `~/.claude/.credentials.json`
- 在 macOS 上，DeerFlow 不会自动探测钥匙串。需要时使用“scripts/export_claude_code_oauth.py”显式导出 Claude Code auth

要将 OpenAI 的 `/v1/responses` 端点与 LangChain 一起使用，请继续使用 `langchain_openai:ChatOpenAI` 并设置：

```yaml
models:
  - name: gpt-5-responses
    display_name: GPT-5 (Responses API)
    use: langchain_openai:ChatOpenAI
    model: gpt-5
    api_key: $OPENAI_API_KEY
    use_responses_api: true
    output_version: responses/v1
```

对于兼容 OpenAI 的网关（例如 Novita 或 OpenRouter），请继续使用 `langchain_openai:ChatOpenAI` 并设置 `base_url`：

```yaml
models:
  - name: novita-deepseek-v3.2
    display_name: Novita DeepSeek V3.2
    use: langchain_openai:ChatOpenAI
    model: deepseek/deepseek-v3.2
    api_key: $NOVITA_API_KEY
    base_url: https://api.novita.ai/openai
    supports_thinking: true
    when_thinking_enabled:
      extra_body:
        thinking:
          type: enabled

  - name: minimax-m2.5
    display_name: MiniMax M2.5
    use: langchain_openai:ChatOpenAI
    model: MiniMax-M2.5
    api_key: $MINIMAX_API_KEY
    base_url: https://api.minimax.io/v1
    max_tokens: 4096
    temperature: 1.0  # MiniMax requires temperature in (0.0, 1.0]
    supports_vision: true

  - name: minimax-m2.5-highspeed
    display_name: MiniMax M2.5 Highspeed
    use: langchain_openai:ChatOpenAI
    model: MiniMax-M2.5-highspeed
    api_key: $MINIMAX_API_KEY
    base_url: https://api.minimax.io/v1
    max_tokens: 4096
    temperature: 1.0  # MiniMax requires temperature in (0.0, 1.0]
    supports_vision: true
  - name: openrouter-gemini-2.5-flash
    display_name: Gemini 2.5 Flash (OpenRouter)
    use: langchain_openai:ChatOpenAI
    model: google/gemini-2.5-flash-preview
    api_key: $OPENAI_API_KEY
    base_url: https://openrouter.ai/api/v1
```

如果您的 OpenRouter 密钥位于不同的环境变量名称中，请将“api_key”显式指向该变量（例如“api_key: $OPENROUTER_API_KEY”）。

**思维模型**：
一些模型支持复杂推理的“思考”模式：

```yaml
models:
  - name: deepseek-v3
    supports_thinking: true
    when_thinking_enabled:
      extra_body:
        thinking:
          type: enabled
```

**Gemini 通过 OpenAI 兼容网关进行思考**：

当在启用思考的情况下通过 OpenAI 兼容代理（Vertex AI OpenAI 兼容端点、AI Studio 或第三方网关）路由 Gemini 时，API 会将“thought_signature”附加到响应中返回的每个工具调用对象。  每个重播这些辅助消息的后续请求**必须**在工具调用条目或 API 返回上回显这些签名：

```
HTTP 400 INVALID_ARGUMENT: function call `<tool>` in the N. content block is
missing a `thought_signature`.
```

标准“langchain_openai:ChatOpenAI”在序列化消息时默默地删除“thought_signature”。  使用 `deerflow.models.patched_openai:PatchedChatOpenAI` 来代替 - 它将工具调用签名（源自 `AIMessage.additional_kwargs["tool_calls"]`）重新注入到每个传出的有效负载中：

```yaml
models:
  - name: gemini-2.5-pro-thinking
    display_name: Gemini 2.5 Pro (Thinking)
    use: deerflow.models.patched_openai:PatchedChatOpenAI
    model: google/gemini-2.5-pro-preview   # model name as expected by your gateway
    api_key: $GEMINI_API_KEY
    base_url: https://<your-openai-compat-gateway>/v1
    max_tokens: 16384
    supports_thinking: true
    supports_vision: true
    when_thinking_enabled:
      extra_body:
        thinking:
          type: enabled
```

对于没有**思考的 Gemini 访问（例如通过未激活思考的 OpenRouter），带有 `supports_thinking: false` 的普通 `langchain_openai:ChatOpenAI` 就足够了，不需要补丁。

### 工具组

将工具组织成逻辑组：

```yaml
tool_groups:
  - name: web          # Web browsing and search
  - name: file:read    # Read-only file operations
  - name: file:write   # Write file operations
  - name: bash         # Shell command execution
```

### 工具

配置代理可用的特定工具：

```yaml
tools:
  - name: web_search
    group: web
    use: deerflow.community.tavily.tools:web_search_tool
    max_results: 5
    # api_key: $TAVILY_API_KEY  # Optional
```

**内置工具**：
- `web_search` - 搜索网络（Tavily）
- `web_fetch` - 获取网页（Jina AI）
- `ls` - 列出目录内容
- `read_file` - 读取文件内容
- `write_file` - 写入文件内容
- `str_replace` - 文件中的字符串替换
- `bash` - 执行 bash 命令

### 沙盒

DeerFlow支持多种沙箱执行模式。在 config.yaml 中配置您的首选模式：

**本地执行**（直接在主机上运行沙箱代码）：

```yaml
sandbox:
   use: deerflow.sandbox.local:LocalSandboxProvider # Local execution
   allow_host_bash: false # default; host bash is disabled unless explicitly re-enabled
```

**Docker 执行**（在隔离的 Docker 容器中运行沙箱代码）：

```yaml
sandbox:
   use: deerflow.community.aio_sandbox:AioSandboxProvider # Docker-based sandbox
```

**使用 Kubernetes 进行 Docker 执行**（通过 Provisioner 服务在 Kubernetes Pod 中运行沙箱代码）：

此模式在 **主机集群** 上的隔离 Kubernetes Pod 中运行每个沙箱。需要 Docker Desktop K8s、OrbStack 或类似的本地 K8s 设置。

```yaml
sandbox:
   use: deerflow.community.aio_sandbox:AioSandboxProvider
   provisioner_url: http://provisioner:8002
```

当使用 Docker 开发（`make docker-start`）时，只有配置了该配置模式，DeerFlow 才会启动 `provisioner` 服务。在本地或普通 Docker 沙箱模式中，会跳过“provisioner”。

有关详细配置、先决条件和故障排除，请参阅[Provisioner 设置指南](../../docker/provisioner/README.md)。

选择本地执行或基于 Docker 的隔离：

**选项 1：本地沙箱**（默认，更简单的设置）：

```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: false
```

默认情况下，“allow_host_bash”有意设置为“false”。 DeerFlow的本地沙箱是主机端便利模式，而不是安全的shell隔离边界。如果您需要“bash”，请优先选择“AioSandboxProvider”。仅针对完全可信的单用户本地工作流程设置“allow_host_bash: true”。

**选项2：Docker Sandbox**（隔离，更安全）：

```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  port: 8080
  auto_start: true
  container_prefix: deer-flow-sandbox

  # Optional: Additional mounts
  mounts:
    - host_path: /path/on/host
      container_path: /path/in/container
      read_only: false
```

当您配置“sandbox.mounts”时，DeerFlow 在代理提示符中公开这些“container_path”值，以便代理可以直接发现并操作已安装的目录，而不是假设所有内容都必须位于“/mnt/user-data”下。

### 技能

为专门的工作流程配置技能目录：

```yaml
skills:
  # Host path (optional, default: ../skills)
  path: /custom/path/to/skills

  # Container mount path (default: /mnt/skills)
  container_path: /mnt/skills
```

**技能如何发挥作用**：
- 技能存储在`deer-flow/skills/{public,custom}/`中
- 每个技能都有一个包含元数据的“SKILL.md”文件
- 技能自动发现并加载
- 通过路径映射在本地和 Docker 沙箱中可用

**每座席技能过滤**：
自定义代理可以通过在“config.yaml”（位于“workspace/agents/<agent_name>/config.yaml”）中定义“skills”字段来限制加载哪些技能：
- **省略或“空”**：加载所有全局启用的技能（默认后备）。
- **`[]`（空列表）**：禁用该特定代理的所有技能。
- **`["技能名称"]`**：仅加载明确指定的技能。

### 标题生成

自动对话标题生成：

```yaml
title:
  enabled: true
  max_words: 6
  max_chars: 60
  model_name: null  # Use first model in list
```

### GitHub API 令牌（GitHub 深度研究技能可选）

默认的 GitHub API 速率限制非常严格。对于频繁的项目研究，我们建议配置具有只读权限的个人访问令牌（PAT）。

**配置步骤**：
1. 取消注释“.env”文件中的“GITHUB_TOKEN”行并添加您的个人访问令牌
2. 重新启动DeerFlow服务以应用更改

## 环境变量

DeerFlow 支持使用 `$` 前缀替换环境变量：

```yaml
models:
  - api_key: $OPENAI_API_KEY  # Reads from environment
```

**常用环境变量**：
- `OPENAI_API_KEY` - OpenAI API 密钥
- `ANTHROPIC_API_KEY` - Anthropic API 密钥
- `DEEPSEEK_API_KEY` - DeepSeek API 密钥
- `NOVITA_API_KEY` - Novita API 密钥（OpenAI 兼容端点）
- `TAVILY_API_KEY` - Tavilly 搜索 API 密钥
- `DEER_FLOW_CONFIG_PATH` - 自定义配置文件路径

## 配置位置

配置文件应该放在**项目根目录**（`deer-flow/config.yaml`），而不是后端目录。

## 配置优先级

DeerFlow 按以下顺序搜索配置：

1. 通过 `config_path` 参数在代码中指定的路径
2.`DEER_FLOW_CONFIG_PATH`环境变量的路径
3.当前工作目录中的`config.yaml`（运行时通常为`backend/`）
4. 父目录中的`config.yaml`（项目根目录：`deer-flow/`）

## 最佳实践

1. **将 `config.yaml` 放在项目根目录** - 不在 `backend/` 目录中
2. **永远不要提交`config.yaml`** - 它已经在`.gitignore`中
3. **使用环境变量作为机密** - 不要硬编码 API 密钥
4. **保持 `config.example.yaml` 更新** - 记录所有新选项
5. **在本地测试配置更改** - 部署之前
6. **使用 Docker 沙箱进行生产** - 更好的隔离和安全性

## 故障排除

###“找不到配置文件”
- 确保“config.yaml”存在于**项目根**目录中（“deer-flow/config.yaml”）
- 后端默认搜索父目录，因此优先选择根位置
- 或者，将“DEER_FLOW_CONFIG_PATH”环境变量设置为自定义位置

###“API 密钥无效”
- 验证环境变量设置正确
- 检查“$”前缀是否用于环境变量引用

###“技能未加载”
- 检查 `deer-flow/skills/` 目录是否存在
- 验证技能是否具有有效的“SKILL.md”文件
- 如果使用自定义路径，请检查“skills.path”配置

### “Docker 沙箱启动失败”
- 确保 Docker 正在运行
- 检查端口 8080（或配置的端口）是否可用
- 验证 Docker 镜像是否可访问

## 示例

有关所有配置选项的完整示例，请参阅“config.example.yaml”。