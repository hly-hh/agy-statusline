# agy-statusline

[中文](#中文说明) | [English](#english)

---

## 中文说明

一个给 **Antigravity CLI (`agy`)** 使用的极简全宽进度条状态栏脚本，纯 Python 标准库实现，**零第三方依赖、不扫描本机进程或端口、不写临时缓存文件**，直接解析 `agy` 原生通过 `stdin` 推送的 JSON 状态流。

### 效果预览

```text
Gemini 4 Neon (High)    │    5h █████████░ 87% 3h40m    │    7d ███████░░░ 73% 4d12h    │    Context █░░░░░░░░░ 8%
💡 /compact — 压缩当前对话历史，释放上下文窗口空间                                           默认 (ﾉ◕ヮ◕)ﾉ*:･ﾟ✧ 3/18
```

### 核心特性

- **全宽均匀铺开**：自动检测终端宽度（支持窗口缩放），第一行将「当前模型、5h 额度进度条、7d 额度进度条、上下文进度条」均匀铺满整行；窄屏自动缩减进度条宽度并回退紧凑排布，不折行。
- **5h + 7d 独立进度条与简化倒计时**：自动按当前模型匹配 `gemini-5h`/`gemini-weekly` 或 `3p-5h`/`3p-weekly`（并兼容扁平 `quota` 结构），两条额度均带彩色进度条与紧凑阿拉伯数字刷新倒计时（如 `3h40m`、`4d12h`）。
- **直觉化上下文进度条**：默认展示**已用占比**（`<60%` 绿、`60%~80%` 橙、`≥80%` 红），对话越长进度条越满，执行 `/compact` 后进度条立刻回落。
- **稳定匀速的中文指令速查 + 萌系动漫娘颜表情**：
  - 采用基于系统绝对时间片的确定性轮播（无需临时文件），无论 `stdin` 推送多频繁，切换节奏始终稳定匀速，不再忽快忽慢；
  - 左侧按优先级展示待确认操作提醒、上下文 `≥80%` `/compact` 建议或中文 `/` 指令速查；
  - 右侧极简展示当前模式简写（`默认` / `规划` / `自动` / `改写`）+ 随状态变化的萌系动漫娘颜表情轮播 + 提示进度（如 `3/18`）。

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
| `AGY_STATUS_KAOMOJI_INTERVAL` | `4` | 右侧动漫娘颜表情切换间隔（秒） |
| `AGY_STATUS_CTX_MODE` | `used` | 上下文进度条模式：`used`（已用占比）或 `remaining`（剩余占比） |
| `AGY_STATUS_SHOW_TIPS` | `1` | 是否显示第二行提示（设为 `0` 隐藏，仅保留单行） |
| `AGY_STATUS_WIDTH` | 自动检测 | 手动指定状态栏目标宽度（列数） |
| `AGY_STATUS_MARGIN` | `4` | 相对终端宽度的安全边距（列数），防止 TUI 边距引起换行 |
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
Gemini 4 Neon (High)    │    5h █████████░ 87% 3h40m    │    7d ███████░░░ 73% 4d12h    │    Context █░░░░░░░░░ 8%
💡 /compact — 压缩当前对话历史，释放上下文窗口空间                                           默认 (ﾉ◕ヮ◕)ﾉ*:･ﾟ✧ 3/18
```

### Features

- **Full-Width Balanced Layout**: Automatically detects terminal width (and tracks resizes) to evenly distribute Model, 5h Quota bar, 7d Quota bar, and Context bar across Row 1, with automatic compact fallback on narrow terminals.
- **Dual Quota Bars (5h & 7d) with Compact Reset Timers**: Automatically matches `gemini-5h`/`gemini-weekly` or `3p-5h`/`3p-weekly` buckets based on the active model (plus flat quota fallback), each with its own color-coded bar and compact numeric countdown (`3h40m`, `4d12h`).
- **Intuitive Context Bar**: Defaults to showing **used** context percentage (`<60%` green, `60%–80%` orange, `≥80%` red), dropping cleanly after `/compact`. Set `AGY_STATUS_CTX_MODE=remaining` to display remaining percentage instead.
- **Steady Rotating Tips & Anime-Girl Kaomoji (Row 2)**: Uses deterministic wall-clock time slots for rock-steady rotation (immune to bursty `stdin` updates or process restarts). Left side displays alerts or Chinese command tips; right side displays a compact mode label (`默认`/`规划`/`自动`/`改写`), rotating anime-girl kaomoji, and tip counter.

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
