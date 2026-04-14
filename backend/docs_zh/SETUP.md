# 设置指南

DeerFlow 的快速设置说明。

## 配置设置

DeerFlow 使用 YAML 配置文件，该文件应放置在 **项目根目录** 中。

### 步骤

1. **导航到项目根目录**：
   

```bash
   cd /path/to/deer-flow
   ```

2. **复制示例配置**：
   

```bash
   cp config.example.yaml config.yaml
   ```

3. **编辑配置**：
   

```bash
   # Option A: Set environment variables (recommended)
   export OPENAI_API_KEY="your-key-here"

   # Option B: Edit config.yaml directly
   vim config.yaml  # or your preferred editor
   ```

4. **验证配置**：
   

```bash
   cd backend
   python -c "from deerflow.config import get_app_config; print('✓ Config loaded:', get_app_config().models[0].name)"
   ```

## 重要提示

- **位置**：`config.yaml`应该位于`deer-flow/`（项目根目录），而不是`deer-flow/backend/`
- **Git**：`config.yaml` 会被 git 自动忽略（包含机密）
- **优先**：如果 `backend/config.yaml` 和 `../config.yaml` 都存在，则后端版本优先

## 配置文件位置

后端按以下顺序搜索“config.yaml”：

1. `DEER_FLOW_CONFIG_PATH` 环境变量（如果设置）
2. `backend/config.yaml` （从 backend/ 运行时的当前目录）
3.`deer-flow/config.yaml`（父目录 - **推荐位置**）

**推荐**：将 `config.yaml` 放在项目根目录中 (`deer-flow/config.yaml`)。

## 沙箱设置（可选但推荐）

如果您计划使用基于 Docker/Container 的沙箱（在 `sandbox.use: deerflow.community.aio_sandbox:AioSandboxProvider` 下的 `config.yaml` 中配置），强烈建议预先拉取容器镜像：

```bash
# From project root
make setup-sandbox
```

**为什么要预拉？**
- 沙盒映像（~500MB+）在首次使用时被拉取，导致长时间等待
- 预拉提供清晰的进度指示
- 避免首次使用代理时出现混乱

如果您跳过此步骤，图像将在第一次代理执行时自动拉取，这可能需要几分钟的时间，具体取决于您的网络速度。

## 故障排除

### 找不到配置文件

```bash
# Check where the backend is looking
cd deer-flow/backend
python -c "from deerflow.config.app_config import AppConfig; print(AppConfig.resolve_config_path())"
```

如果找不到配置：
1. 确保您已将 `config.example.yaml` 复制到 `config.yaml`
2. 确认您位于正确的目录中
3. 检查文件是否存在：`ls -la ../config.yaml`

### 权限被拒绝

```bash
chmod 600 ../config.yaml  # Protect sensitive configuration
```

## 另请参阅

- [配置指南](CONFIGURATION.md) - 详细配置选项
- [架构概述](../CLAUDE.md) - 系统架构