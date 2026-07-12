# 小智语音系统：结构与清理审计

审计时间：2026-07-12。范围为 `D:\system\py-xiaozhi` 及其实际运行时数据目录
`C:\Users\常永康\AppData\Local\py-xiaozhi\py-xiaozhi`。本审计未删除或修改业务文件。

## 结论

可以立即清理的仓库文件只有 Python 解释器缓存 `**/__pycache__/`（当前 100 个 `.pyc`，约 899 KiB）。
仓库中不存在 `build/`、`dist/`、`.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`、`.venv/` 或根目录 `cache/`。
因此不能以“清缓存”为理由删除 `assets/`、`models/`、`libs/`、`documents/` 或 `.trellis/tasks/archive/`；它们均是被跟踪的运行时、打包或开发资产。

真正占用空间的可选清理对象在用户数据目录：音乐缓存约 8.53 MiB，而不是项目目录。

## 可安全清理（停止应用后执行）

| 对象 | 现状与证据 | 处理建议 | 风险 |
| --- | --- | --- | --- |
| `src/**/__pycache__/`、`tests/__pycache__/` | `git status --ignored` 显示 100 个 `.pyc`；`git ls-files` 不含任何 `.pyc`；`.gitignore` 已有 `**/__pycache__/`。 | 递归删除全部 `__pycache__` 目录。Python 会在下次运行自动重建。 | 无功能风险；首次启动会稍慢。 |
| `C:\Users\常永康\AppData\Local\py-xiaozhi\py-xiaozhi\cache\music\temp\*` | `MusicPlayer._clean_temp_cache()` 在初始化时主动删除该目录内文件。 | 可删除临时文件；当前目录为空。 | 无。 |
| `C:\Users\常永康\AppData\Local\py-xiaozhi\py-xiaozhi\cache\music\440613.mp3` | 文件约 8.53 MiB；`MusicPlayer` 将 `get_user_cache_dir()/music` 定义为下载缓存，并能重新下载。 | 在没有播放音乐时，可清理该文件或整个 `cache/music/`。 | 会丢失离线/本地播放列表中的已下载歌曲；下次播放需联网重新下载。 |

`.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`、`.coverage`、`htmlcov/`、`.tox/`、`.nox/`、`*.egg-info/` 当前均不存在，不能把它们计入本次可释放空间；但应补入忽略规则，防止未来污染工作区。

## 仅可按保留策略清理，不能自动删除

| 对象 | 证据 | 建议与风险 |
| --- | --- | --- |
| `...\logs\app.log`（约 824 KiB）、`error.log`、历史 `app.2026-07-05.log.gz` | `resource_finder.get_user_log_dir()` 明确将日志写入用户数据；日志配置已启用文件日志、按日轮转，保留数为 30。 | 应实现保留天数/总大小策略，只删过期压缩日志；不要在程序运行时删除当前 `app.log`。会降低故障排查能力。 |
| `...\keywords\zh\keywords.txt.bak` | 设置页写入新唤醒词前会创建该备份，`plugins/wake_word.py` 可在热重载失败时恢复它。 | 保留。删除会失去唤醒词热更新失败的回滚能力。 |
| `...\keywords\zh_keywords.txt` | `resource_finder.get_user_keywords_path()` 仅在新版 `keywords/zh/keywords.txt` 不存在时读取此旧路径；当前新版文件已存在。 | 可作为迁移后的候选清理项，但建议先完成“旧路径迁移/兼容期”并备份后再删。体积仅 37 B，收益可忽略。 |
| `.trellis/.runtime/`、`.trellis/.developer` | 被 `.trellis/.gitignore` 忽略；用于当前 Trellis 会话和开发者状态。 | 当前有活跃任务，不能清理。任务完成且不再需要恢复上下文后才可删。 |

## 必须保留

| 对象 | 证据 |
| --- | --- |
| `main.py` 与 `src/` | `main.py` 是 GUI/CLI/GPIO 统一启动入口；其创建 `ServiceContainer` 并加载 `src` 的激活、协议、插件、MCP、音频和 UI 层。 |
| `models/`（17.72 MiB） | `resource_finder.get_models_dir()` 和唤醒词检测直接读取 `models/zh`、`models/en` 的 ONNX、token 与关键词资源。删除将使离线唤醒失效。 |
| `libs/`（7.94 MiB） | `resource_finder.get_lib_path()` 按平台加载 `libopus`、`webrtc_apm`；README 和打包配置均将其作为运行时数据。 |
| `assets/`（45.34 MiB） | `resource_finder.get_assets_dir()` 将其作为只读运行资源；`build.json`/`release.py` 都把该目录纳入发行包。应另做“按 UI 引用”的资产审计，不能按大小删除。 |
| `scripts/` | 打包配置 `add_data` 显式包含该目录。 |
| `documents/` | 113 个被 Git 跟踪的 VitePress 文档文件，并有独立 `documents/.gitignore` 忽略 `dist`、`node_modules`。不是构建产物。 |
| `.trellis/tasks/archive/` 与 `.claude/` | 均为受版本控制的项目工作流/历史记录；删除会破坏 Trellis 追溯和团队辅助流程。 |
| 用户目录下 `config/config.json`、`config/efuse.json` | `ConfigManager` 从用户数据目录加载前者；`ActivationService` 使用后者保存激活状态。删除会丢失设备认证、服务端连接、音频设备、香薰与用户偏好。 |

## 结构与配置发现

1. 项目入口清晰但文档树已过时：`README.zh.md` 的目录树没有列出 `constants/`、`logging/`、`utils/`，也没有列出新增的 `mcp/tools/aroma/`。重构应更新该树，而非移动核心模块来迁就文档。
2. 配置实际采用**代码默认值 + 用户覆盖文件**：`ConfigManager.DEFAULT_CONFIG` 是完整默认值；运行时文件位于 `platformdirs.user_data_dir(APP_NAME)/config/config.json`。当前 Windows 实际路径为上文所列的双层 `py-xiaozhi` 目录，应通过 `get_user_data_dir()` 输出展示给用户，禁止在 UI 或文档中硬编码路径。
3. 仓库没有受版本控制的无密钥配置模板，且 `.gitignore` 直接忽略根 `config/`。后续应新增一个明确的 `config.example.json`（或 `config/config.example.json` 并为它添加 `.gitignore` 例外），仅含默认值和空的密钥字段；运行时仍只读取用户数据目录中的 `config.json`。这能形成用户所需的“统一配置文件”，同时避免提交 API Key、MQTT 密码和设备标识。
4. 当前运行时 `config.json` 无法被标准 JSON 解析器解析（解析错误发生在含中文文本的位置）。`ConfigManager._load_config()` 捕获该异常后回退到内置默认值，故用户设置可能被静默忽略。重构必须先修复/重新生成该文件的 UTF-8 JSON，再做字段迁移；不要在报告或提交中记录其中的密钥/令牌。
5. `build.json` 是 UnifyPy 的正式打包配置：`release.py` 会从 `src/constants/system.py` 生成它，文档也以 `unifypy . --config build.json` 为打包命令，故必须保留。`py-xiaozhi.spec` 则包含开发者机器的绝对 macOS 路径，且没有仓库内调用点；它是“先验证打包流程后可删除”的候选，不属于本次安全删除项。

## 推荐的实施顺序

1. 先备份用户运行时目录中的 `config/config.json`、`efuse.json` 和 `keywords/`；停止小智进程。
2. 删除全部 `__pycache__`，再按用户确认清理音乐缓存和过期日志。
3. 扩展 `.gitignore` 覆盖测试、类型检查、覆盖率、构建和 Python 打包缓存；保留已有的配置与运行日志忽略规则。
4. 创建并维护一份无密钥 `config.example.json`，在启动/设置页显示实际配置路径，并提供“验证配置 JSON”的显式报错。
5. 仅在验证 `unifypy` 打包通过后，移除过时 `py-xiaozhi.spec`；随后更新 README 目录树和配置说明。

