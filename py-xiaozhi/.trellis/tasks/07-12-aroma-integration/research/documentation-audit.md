# 使用文档与 README 审计

审计时间：2026-07-12。范围仅包含仓库中的 README、VitePress 文档结构、启动入口、配置加载和内置 MCP/香薰实现。本记录不包含也不记录任何真实密钥、令牌、MQTT 凭据或设备标识。

## 结论

项目已经具备两层文档入口：仓库根目录 `README.zh.md` 适合提供首次部署所需的最短路径；`documents/` 是独立的 VitePress 站点，适合放置完整中文使用手册。新增文档不应另起一套配置格式，而应以仓库显式配置 `config/config.json` 为唯一主配置来源，并说明环境变量覆盖和旧目录兼容回退。

建议新增 `documents/docs/zh/guide/使用文档.md` 作为面向部署者的一站式中文手册，并在 VitePress 中文导航、`documents/docs/zh/guide/文档目录.md`、根 `README.zh.md` 中互相链接。README 保持可在一屏内完成“安装、配置、运行、验证”的定位；详细字段说明、鲁班猫-4 部署和香薰故障排查放入使用文档。

## 已核对的运行事实

### 启动与运行模式

`main.py` 是 GUI、CLI 和 GPIO 的统一入口，参数如下：

| 参数 | 可选值/含义 | 文档应说明 |
| --- | --- | --- |
| `--mode` | `gui`（默认）、`cli`、`gpio` | GUI 需要 GUI 可选依赖；GPIO 只适用于 Linux。鲁班猫-4 的无界面部署应优先示例 `--mode cli`，只有已完成物理按键接线时才使用 `--mode gpio`。 |
| `--protocol` | `websocket`（默认）、`mqtt` | 仅在后端要求 MQTT 时传入；连接信息来自配置或激活流程，文档不得要求用户公开凭据。 |
| `--skip-activation` | 布尔开关 | 仅用于调试；正常部署不应建议跳过激活。 |

常用启动命令可准确写为：

```bash
# 安装基础依赖后：CLI / GPIO
uv run python main.py --mode cli

# GUI（需先安装 GUI extra）
uv run python main.py

# MQTT 示例
uv run python main.py --mode cli --protocol mqtt
```

项目要求 Python >= 3.10。`pyproject.toml` 提供基础安装和 GUI 可选依赖；中文使用手册应沿用现有“uv 优先、pip/venv 备选”的安装路径。`documents/package.json` 的文档命令为 `pnpm docs:dev`、`pnpm docs:build`、`pnpm docs:preview`（均在 `documents/` 目录运行）。

### 配置来源与写入行为

`ConfigManager` 的配置读取优先级为：

1. 环境变量 `XIAOZHI_CONFIG_PATH` 指向的 JSON 文件；适合把私密配置放在仓库外。
2. 仓库/安装目录 `config/config.json`；这是鲁班猫-4 固定部署时应编辑的显式配置文件。
3. 旧版用户数据目录中的 `config/config.json`；仅为兼容已有安装。

不存在的配置文件会在本次运行使用代码默认值；不会自动生成并写入仓库配置。JSON 格式无效时，程序记录文件及行列位置、保留原文件并回退默认值，不会覆盖损坏文件。运行时更新配置时优先写回当前来源；如果仓库配置只读，才回退写入旧用户目录。

文档应明确：

- `config/config.json` 是完整 JSON，修改前先备份；JSON 不允许注释、尾随逗号或省略外层 `{}`。
- 仓库可保存无密钥默认配置，但实际 API Key、访问令牌、MQTT 密码和设备标识应以 `<YOUR_...>` 占位符示例展示；生产环境推荐用 `XIAOZHI_CONFIG_PATH` 指向私密文件，且不要提交该文件。
- 配置修改后需重启应用；运行时界面写回配置的行为应以实际读取来源为准。

当前代码默认配置顶层模块为：`SYSTEM_OPTIONS`、`WAKE_WORD_OPTIONS`、`CAMERA`、`AROMA`、`SHORTCUTS`、`AEC_OPTIONS`、`AUDIO_DEVICES`、`LOGGING`。使用文档不必重复所有默认值，应按“必填/按需启用/高级调优”分组，并链接到配置参考页。

### MCP 与香薰

MCP 启动时自动扫描 `src/mcp/tools/` 下的工具子包并导入其 `__init__.py`/`_tools.py`；单一工具包加载失败只会警告，不阻断其他工具。当前内置工具目录包括音量、应用、相机、音乐、截图、天气和香薰。

香薰位于 `src/mcp/tools/aroma/`，分层为：

- `_tools.py`：注册 `aroma.enter`、`aroma.start`、`aroma.status`、`aroma.exit` 四个 MCP 工具；由模型根据工具描述调用。
- `manager.py`：维护单一香薰会话、异步任务、启动/退出和状态；退出会停止任务、关闭全部通道并恢复普通聊天。
- `planner.py`：优先调用 Qwen 的 OpenAI 兼容 Chat Completions 接口生成 JSON 配方；无 API Key、调用失败或返回无效时，使用本地规则生成安全的回退配方。
- `driver.py`：DAM1600C 兼容 Modbus RTU 串口继电器驱动；所有结束路径都会尝试关闭 1--16 号通道并关闭串口。

香薰语音流程应描述为“模型工具调用”，而不是本地关键词硬编码：

1. 用户说“开启香薰系统”“进入香薰模式”等，模型调用 `aroma.enter`；系统只进入模式并追问需求，不立即启动硬件。
2. 用户说明放松、专注、提神、助眠等目标后，模型调用 `aroma.start(requirement)`。
3. 用户可询问状态，模型调用 `aroma.status`。
4. 用户说“停止香薰”“退出香薰系统”“关闭香薰模式”等，模型必须调用 `aroma.exit`；它关闭全部通道并退出模式。

香薰开始前同时检查 `AROMA.ENABLED` 为 `true` 且 `AROMA.SERIAL_PORT` 非空。因此默认配置安全地保持硬件关闭。继电器通道只允许 1--16；每阶段最多三种香型；阶段与总时长分别受 `MAX_STAGE_SECONDS` 和 `MAX_TOTAL_SECONDS` 限制。文档必须提示先断开香薰负载完成软件验证，再连接硬件；首次测试从短时间、单通道开始，并确认有效电平与实际继电器一致。

适合在使用文档中展示的无密钥香薰片段如下：

```json
{
  "AROMA": {
    "ENABLED": true,
    "SERIAL_PORT": "<SERIAL_PORT>",
    "BAUDRATE": 9600,
    "DEVICE_ADDRESS": 1,
    "SERIAL_TIMEOUT": 1.0,
    "RETRIES": 1,
    "ACTIVE_HIGH": true,
    "MAX_STAGE_SECONDS": 600,
    "MAX_TOTAL_SECONDS": 1800,
    "CHANNEL_MAP": {
      "lavender": 1,
      "bergamot": 2
    },
    "QWEN": {
      "API_KEY": "<YOUR_QWEN_API_KEY>",
      "BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "MODEL": "qwen3.6-plus",
      "CONNECT_TIMEOUT": 5.0,
      "READ_TIMEOUT": 20.0
    }
  }
}
```

`CHANNEL_MAP` 的键名必须与实际接线和香薰瓶一致；未配置 Qwen 密钥不妨碍香薰运行，因为本地规则会回退处理睡眠、专注、提神和放松类需求。缺少 `pyserial` 时不能控制硬件，应按项目依赖安装流程安装，而不是手动复制驱动文件。

## 现有文档缺口

| 位置 | 现状 | 建议 |
| --- | --- | --- |
| `README.zh.md` | 已有快速开始、仓库配置位置和简化目录树；没有面向鲁班猫-4 的完整运行与验证路径，也没有香薰入口。 | 将快速开始缩成部署闭环，新增“鲁班猫-4/无界面启动”和“香薰系统”小节，链接到完整使用文档；目录树明确 `config/`、`src/mcp/tools/aroma/`、`documents/` 的职责。 |
| `README.md` | 英文 README 结构较完整，但不包含本次仓库内配置和香薰改动。 | 本任务若以中文交付为主，可只做最小的配置/香薰链接更新；不要伪造未验证的英文硬件教程。 |
| `documents/docs/zh/guide/配置说明.md` | 仍以旧的用户数据目录为主要配置位置，包含过时的“首次运行自动生成”与旧模板叙述，未列 `AROMA`。 | 重写开头的来源优先级、仓库配置、环境变量覆盖、损坏 JSON 保护；新增 `AROMA` 参考，移除或标为兼容说明的旧路径内容。 |
| `documents/docs/zh/guide/文档目录.md` | 入口页存在，但内容仍提及未在当前工具目录发现的功能，且未链接香薰。 | 将“使用文档”置于基础文档第一项，列出当前 MCP 工具并链接香薰章节。 |
| `documents/docs/zh/mcp/index.md` | 正确说明自动发现，但“现有工具模块”表缺少香薰。 | 加一行“香薰：会话、配方、DAM1600C 继电器控制”，链接至使用文档的香薰章节或新增专页。 |
| `documents/docs/.vitepress/config.mts` | 中文“指南”和“MCP”导航都没有使用文档或香薰入口。 | 在“指南”中加入“使用文档”；在“MCP”中加入“香薰系统”，确保链接路径为 `/zh/...`。 |

## 推荐的中文使用文档目录

建议文件：`documents/docs/zh/guide/使用文档.md`。

1. **项目是什么、适合谁用**：Python 小智语音客户端；实时语音、视觉、MCP 工具和 IoT；桌面/ARM Linux 均可部署。避免把客户端描述为本地大模型或离线 ASR 服务端。
2. **部署前检查**：Python >= 3.10、网络、麦克风/扬声器；GUI 另需 `gui` extra；鲁班猫-4 使用 Linux CLI，GPIO 仅在物理按键需求明确时启用。
3. **快速安装与首次运行**：`uv sync`（基础）/`uv sync --extra gui`（GUI）；对应 `uv run python main.py --mode cli` 和 GUI 启动命令；正常激活与 `--skip-activation` 的边界。
4. **统一配置文件**：`config/config.json` 的位置、环境变量覆盖优先级、备份和 JSON 校验要点；展示不含任何秘密的最小片段，并按顶层模块说明用途。
5. **运行模式与协议**：GUI、CLI、GPIO、WebSocket、MQTT 的选择表；给出鲁班猫-4 推荐命令。避免写死设备路径、声卡编号或 MQTT 连接信息。
6. **常用功能**：唤醒词、手动/自动对话、相机、音乐、天气等功能只描述可用性和对应配置入口；不承诺后端没有提供的模型能力。
7. **香薰系统**：硬件前置条件（DAM1600C 兼容板、串口、通道接线）、`AROMA` 无密钥配置、启用/状态/退出语音示例、Qwen 与本地规则回退、安全注意事项和错误排查。
8. **日志与故障排查**：配置解析失败、GUI 依赖缺失、音频设备、激活、串口不可用、Qwen 调用失败的症状和处理；强调日志中不应粘贴密钥。
9. **项目结构与二次开发边界**：入口、配置、`src/bootstrap`/`core`/`protocols`/`plugins`/`mcp`/`ui`/`utils`、资源目录和文档站职责；说明新增 MCP 工具的自动发现规则并链接 MCP 开发指南。
10. **更新与安全清单**：停止应用再更新依赖；备份私密配置；不提交含密钥的配置；香薰硬件先离线测试和随时可用的物理断电措施。

## README.zh.md 的建议结构

README 应避免复制完整配置字段，推荐保留如下主线：

1. 项目简介和主要能力（补充“可选香薰 MCP 控制”）。
2. 30 秒快速开始：依赖安装、基础/GUI 安装、CLI/GUI 启动。
3. 配置位置与安全：明确 `config/config.json`，列出 `XIAOZHI_CONFIG_PATH` 优先级，链接使用文档；只使用占位符。
4. 鲁班猫-4：CLI 推荐命令、音频权限/设备准备和 GPIO 可选说明。
5. 香薰系统：一句功能说明、必要配置项表、进入/需求/状态/退出的语音样例，链接详细章节。
6. 精简且准确的项目目录树与状态流转图。
7. 文档、贡献、许可证链接。

## 验收清单

- 所有示例密钥、令牌、MQTT 密码、设备 ID 都是占位符；不从实际 `config/config.json` 复制任何值。
- 所有“配置位置”均与当前三层优先级一致，不再称首次运行会自动创建仓库配置。
- 所有启动命令均与 `main.py` 参数一致，明确 GUI 额外依赖和 GPIO 的 Linux 限制。
- 香薰功能准确表述为 MCP 工具调用与 DAM1600C 兼容串口继电器控制，且写明默认禁用、进入不启动、退出全关断、Qwen 失败本地回退。
- VitePress 中文导航、文档目录、README 和 MCP 工具表都能到达新手册/香薰章节；在 `documents/` 目录执行文档构建验证链接和 Markdown。
