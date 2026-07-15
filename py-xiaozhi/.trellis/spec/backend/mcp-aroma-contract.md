# 香薰服务端方案 MCP 契约

## 1. Scope / Trigger

小智服务端模型理解用户需求，客户端只负责校验并控制本地设备。服务端输出绝不能直接成为继电器命令。

## 2. Signatures

```python
@mcp_tool(
    name="aroma.start",
    props=[
        Prop("requirement", PropType.STR),
        Prop("recipe", PropType.STR, default=""),
    ],
)
async def aroma_start(args: dict[str, Any]) -> str: ...
```

当前 MCP schema 仅支持标量属性，因此 `recipe` 是可选 JSON 字符串。

## 3. Contracts

```json
{
  "summary": "简短说明",
  "stages": [{"aromas": ["lavender", "bergamot"], "duration_seconds": 30}]
}
```

客户端必须使用 `AROMA.CHANNEL_MAP` 将香型名称转换成 16 路 pattern。结果必须标记来源：`xiaozhi_server` 或 `fixed_library`。

## 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 缺失、非 JSON 或空方案 | 使用固定配方库 |
| 空阶段、未知/重复香型、非法阶段时长 | 拒绝整个方案并使用固定库 |
| 阶段总时长超过配置上限 | 拒绝整个方案并使用固定库 |
| 所有阶段有效 | 转换成 pattern 后执行 |

## 5. Good / Base / Bad Cases

- Good：服务端传入映射中存在的香型和受限时长。
- Base：服务端仅传 `requirement`，客户端选择固定安全配方。
- Bad：将服务端传入的 pattern 或继电器号直接写入设备。

## 6. Tests Required

- 工具 schema 将 `recipe` 暴露为可选字符串。
- 有效方案产生 16 路 pattern 和 `xiaozhi_server` 来源。
- 畸形 JSON、未知/重复香型、超限时长均回退 `fixed_library`。
- 固定库覆盖助眠、专注、提神和默认场景，且测试不访问真实串口。

## 7. Wrong vs Correct

```python
# Wrong: never bypass the local validator.
driver.write_pattern(server_recipe["pattern"])

# Correct: resolve names through CHANNEL_MAP and fall back when invalid.
recipe = await planner.create_recipe(requirement, server_recipe)
```
