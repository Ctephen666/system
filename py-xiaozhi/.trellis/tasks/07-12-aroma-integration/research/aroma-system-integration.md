# 香薰系统集成调研

## 上游系统可复用边界

上游仓库将功能分为独立层：配方生成、分阶段执行、DAM1600C 串口继电器控制、PyQt/QML 界面、SQLite 历史和远程 API。本任务只复用前三项的语义：一个配方由多个阶段组成，每个阶段开启 1 至 3 个通道，阶段结束必须关闭本阶段通道；任务完成、异常或被停止时必须关闭全部通道。

原继电器驱动使用 Modbus RTU 风格帧写单个线圈，通道编号从 1 开始，支持配置串口、波特率、设备地址、超时、有效电平、重试次数和香薰通道映射。集成版应保持该协议，但不得把阻塞的串口操作放在小智的 asyncio 事件循环中。

## Qwen3.6 调用方案

香薰配方使用 OpenAI 兼容的 Chat Completions 调用，所有凭据和部署差异必须配置化：`API_KEY`、`BASE_URL`、`MODEL`、连接超时和读取超时。默认模型设为 `qwen3.6-plus`，但允许配置覆盖；API Key 只从本地配置读取，绝不写入代码、日志或提交文件。

阿里云模型服务提供 OpenAI 兼容的 `/compatible-mode/v1/chat/completions` 接口，并要求使用与区域一致的 API Key。官方文档确认该接口支持用 `model` 和 `messages` 发起请求；Qwen Code 官方示例列出了 `qwen3.6-plus`。参考：

- https://help.aliyun.com/en/model-studio/compatibility-of-openai-with-dashscope
- https://help.aliyun.com/en/model-studio/qwen-code

API 返回无效、超时或未配置密钥时，使用上游项目的本地关键字规则生成配方，不影响香薰模式退出和安全关断。

## 集成设计

将功能实现为 `src/mcp/tools/aroma/` 下的 MCP 工具：进入模式、按需求启动、状态查询、退出模式。工具结果向主对话模型明确下一步对话要求，因此语音系统仍由现有 MCP 自动发现和模型工具调用机制驱动。模块维护单一设备会话；同一时间只运行一个香薰任务，退出会取消任务并关闭通道。

不引入上游 PyQt、SQLite、FastAPI、QML 或它们的依赖，以免与小智的事件循环、界面和服务端口冲突。
