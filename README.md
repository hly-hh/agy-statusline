# agy-statusline

[中文](#中文说明) | [English](#english)

---

## 中文说明

一个给 **Antigravity CLI (`agy`)** 使用的极简双进度条状态栏脚本，纯 Python 标准库实现，**零第三方依赖、不扫描本机进程或端口、不写临时缓存文件**，直接解析 `agy` 原生通过 `stdin` 推送的 JSON 状态流。

### 效果预览

```text
Gemini 4 Neon (High) │ Quota █████████░ 87% · 4h (7d 73%) │ Context █░░░░░░░░░ 8%
  💡 /compact — 压缩当前对话历史，释放上下文窗口空间
```

### 核心特性

- **极简第一行**：只保留最有用的三项信息——当前模型、额度进度条、上下文进度条，去掉工作目录/状态/Token 计数等干扰项。
- **原生额度解析**：直接读取 `agy` `stdin` 中的分桶额度（自动按当前模型匹配 `gemini-5h`/`gemini-weekly` 或 `3p-5h`/`3p-weekly`，并兼容扁平 `quota` 结构），展示 10 格彩色进度条、重置倒计时与 7 日周额度。
- **直觉化上下文进度条**：默认展示**已用占比**（`<60%` 绿、`60%~80%` 橙、`≥80%` 红），对话越长进度条越满，执行 `/compact` 后进度条立刻回落。
- **中文 `/` 指令速查 + 智能状态提醒**：
  - 待确认工具操作时优先醒目提醒；
  - 上下文占用达到 `80%` 时提醒执行 `/compact`；
  - 非默认模式（`plan` / `auto` / `accept-edits`）显示当前模式中文说明；
  - 平时每 8 秒轮换一条常用 `/` 斜杠指令的中文解释。

### 安装

```bash
git clone https://github.com/hly-hh/agy-statusline.git
cd agy-statusline
./install.sh
```

安装完成后，重启 `agy` 或在当前会话执行 `/statusline off` 再 `/statusline on` 即可生效。

### 环境变量配置

| 变量名 | 默认值 | 说明 |
| --- | --- | --- |
| `AGY_STATUS_BAR_WIDTH` | `10` | 进度条格数（范围 `4`~`30`） |
| `AGY_STATUS_TIP_INTERVAL` | `8` | 底部中文指令提示轮换间隔（秒） |
| `AGY_STATUS_CTX_MODE` | `used` | 上下文进度条模式：`used`（已用占比）或 `remaining`（剩余占比） |
| `AGY_STATUS_SHOW_TIPS` | `1` | 是否显示第二行提示（设为 `0` 隐藏，仅保留单行） |
| `AGY_STATUSLINE_DIR` | `~/.antigravity` | 脚本安装目录 |
| `AGY_SETTINGS_FILE` | `~/.gemini/antigravity-cli/settings.json` | Antigravity CLI 配置文件路径 |

### 卸载

```bash
./uninstall.sh
```

### 致谢

灵感来源于 `60ke/antigravity-statusline`，本仓库为完全独立重写的原生 `stdin` 解析极简版，采用 MIT 协议开源。

---

## English

A minimalist, zero-dependency Python status line for **Antigravity CLI (`agy`)**. It parses the native JSON telemetry stream piped by `agy` over `stdin`—no local port probing, no process inspection, and no temporary state files.

### Preview

```text
Gemini 4 Neon (High) │ Quota █████████░ 87% · 4h (7d 73%) │ Context █░░░░░░░░░ 8%
  💡 /compact — 压缩当前对话历史，释放上下文窗口空间
```

### Features

- **Minimal Row 1**: Active model, 10-block colored quota bar (with reset countdown & 7-day quota), and 10-block colored context usage bar.
- **Native `stdin` Quota Parsing**: Automatically matches `gemini-5h`/`gemini-weekly` or `3p-5h`/`3p-weekly` buckets based on the active model, with fallback support for flat quota payloads.
- **Intuitive Context Bar**: Defaults to showing **used** context percentage (`<60%` green, `60%–80%` orange, `≥80%` red), dropping cleanly after `/compact`. Set `AGY_STATUS_CTX_MODE=remaining` to display remaining percentage instead.
- **Dynamic Alerts & Chinese Command Tips (Row 2)**: Highlights pending tool confirmations, high context usage (`≥80%`), active non-default modes, and rotates Chinese explanations of `agy` slash commands every 8 seconds.

### Install

```bash
git clone https://github.com/hly-hh/agy-statusline.git
cd agy-statusline
./install.sh
```

Then restart `agy` or run `/statusline off` followed by `/statusline on`.

### Uninstall

```bash
./uninstall.sh
```

### License

MIT — Inspired by `60ke/antigravity-statusline`.
