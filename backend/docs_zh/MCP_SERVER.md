# MCP（模型上下文协议）配置

DeerFlow 支持可配置的 MCP 服务器和技能来扩展其功能，这些服务器和技能是从项目根目录中的专用“extensions_config.json”文件加载的。

## 设置

1. 将 `extensions_config.example.json` 复制到项目根目录下的 `extensions_config.json` 中。
   

```bash
   # Copy example configuration
   cp extensions_config.example.json extensions_config.json
   ```

   
2. 通过设置 `"enabled": true` 启用所需的 MCP 服务器或技能。
3. 根据需要配置每个服务器的命令、参数和环境变量。
4. 重新启动应用程序以加载并注册 MCP 工具。

## OAuth 支持（HTTP/SSE MCP 服务器）

对于“http”和“sse”MCP 服务器，DeerFlow 支持 OAuth 令牌获取和自动令牌刷新。

- 支持的授权：`client_credentials`、`refresh_token`
- 在“extensions_config.json”中配置每个服务器的“oauth”块
- 应通过环境变量提供机密（例如：`$MCP_OAUTH_CLIENT_SECRET`）

示例：

```json
{
   "mcpServers": {
      "secure-http-server": {
         "enabled": true,
         "type": "http",
         "url": "https://api.example.com/mcp",
         "oauth": {
            "enabled": true,
            "token_url": "https://auth.example.com/oauth/token",
            "grant_type": "client_credentials",
            "client_id": "$MCP_OAUTH_CLIENT_ID",
            "client_secret": "$MCP_OAUTH_CLIENT_SECRET",
            "scope": "mcp.read",
            "refresh_skew_seconds": 60
         }
      }
   }
}
```

## 它是如何工作的

MCP 服务器公开了在运行时自动发现并集成到 DeerFlow 代理系统中的工具。启用后，代理即可使用这些工具，无需进行额外的代码更改。

## 示例功能

MCP 服务器可以提供对：

- **文件系统**
- **数据库**（例如 PostgreSQL）
- **外部 API**（例如 GitHub、Brave Search）
- **浏览器自动化**（例如，Puppeteer）
- **自定义 MCP 服务器实现**

## 了解更多

有关模型上下文协议的详细文档，请访问：  
https://modelcontextprotocol.io