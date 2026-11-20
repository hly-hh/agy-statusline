#!/usr/bin/env python3
"""Minimalist Status Line for Antigravity CLI (`agy`).

Reads the JSON telemetry stream piped by `agy` on stdin and renders a
compact, two-line terminal status bar:
  Row 1: Model │ Quota progress bar (+ reset & 7d) │ Context progress bar
  Row 2: Dynamic status alerts or rotating Chinese slash-command tips

Zero third-party dependencies. Compatible with Python 3.8+.
"""

import codecs
import json
import os
import random
import select
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── ANSI Styles ────────────────────────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
GRAY = "\033[90m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
ORANGE = "\033[38;5;208m"
AMBER = "\033[38;5;214m"
RED = "\033[31m"
CYAN = "\033[36m"
BLUE = "\033[34m"
PURPLE = "\033[38;5;141m"

# ── Configuration (via environment variables) ──────────────────────────────────
def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.environ.get(name, str(default)))))
    except ValueError:
        return default


def _env_float(name: str, default: float, lo: float) -> float:
    try:
        return max(lo, float(os.environ.get(name, str(default))))
    except ValueError:
        return default


BAR_WIDTH = _env_int("AGY_STATUS_BAR_WIDTH", 10, 4, 30)
TIP_INTERVAL = _env_float("AGY_STATUS_TIP_INTERVAL", 8.0, 2.0)
CTX_MODE = os.environ.get("AGY_STATUS_CTX_MODE", "used").strip().lower()
SHOW_TIPS = os.environ.get("AGY_STATUS_SHOW_TIPS", "1").strip().lower() not in (
    "0",
    "false",
    "off",
    "no",
)

# ── Chinese Slash-Command Quick Reference ──────────────────────────────────────
COMMAND_TIPS: List[str] = [
    "/model — 切换当前对话使用的 AI 模型与思考强度",
    "/compact — 压缩当前对话历史，释放上下文窗口空间",
    "/usage — 查看当前账号剩余额度与下次重置时间",
    "/plan — 先制定详细执行计划，确认后再动手修改",
    "/goal — 开启长任务自主模式，持续推进直到目标完成",
    "/boost — 复杂研发任务增强模式：深度思考与严格验证",
    "/teamwork — 启动多 Agent 协作团队并行处理大型项目",
    "/grill-me — 通过交互式问答梳理并敲定技术方案细节",
    "/schedule — 创建定时提醒或周期性自动执行任务",
    "/browser — 启动浏览器能力进行网页检索与页面交互",
    "/agents — 查看和管理当前正在运行的后台子 Agent",
    "/statusline — 开启、关闭或重载底部状态栏显示",
    "/mcp — 查看或管理已接入的外部 MCP 工具服务",
    "/learn — 将你的偏好或纠错沉淀下来，后续任务自动遵守",
    "/changelog — 查看 Antigravity CLI 最新版本更新内容",
    "/help — 查看全部可用斜杠指令与快捷键说明",
    "快捷键：输入 !命令 可直接执行终端命令，Ctrl+R 搜索历史",
    "快捷键：Ctrl+O 展开工具执行详情，拖入文件即可添加上下文",
]

MODE_LABELS: Dict[str, str] = {
    "plan": "规划模式（仅规划与分析，不直接改文件）",
    "auto": "全自动模式（自动批准操作，无需逐步确认）",
    "accept-edits": "自动改写模式（编辑文件自动放行）",
}


# ── Formatting Helpers ─────────────────────────────────────────────────────────
def clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, value))


def render_bar(pct: float, color: str, width: int = BAR_WIDTH) -> str:
    pct = clamp_pct(pct)
    filled = int(round((pct / 100.0) * width))
    if pct > 0.0 and filled == 0:
        filled = 1
    empty = width - filled
    return f"{color}{'█' * filled}{GRAY}{'░' * empty}{RESET}"


def quota_color(remaining_pct: float) -> str:
    if remaining_pct >= 50.0:
        return PURPLE
    if remaining_pct >= 20.0:
        return AMBER
    return RED


def context_color(used_pct: float) -> str:
    if used_pct < 60.0:
        return GREEN
    if used_pct < 80.0:
        return ORANGE
    return RED


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "now"
    minutes = (seconds + 59) // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, rem_mins = divmod(minutes, 60)
    if hours >= 24:
        days, rem_hours = divmod(hours, 24)
        return f"{days}d {rem_hours}h" if rem_hours else f"{days}d"
    return f"{hours}h {rem_mins}m" if rem_mins else f"{hours}h"


def seconds_until_iso(iso_str: str) -> Optional[int]:
    try:
        target = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int((target - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return None


# ── Telemetry Parsers ──────────────────────────────────────────────────────────
def parse_model_name(data: Dict[str, Any]) -> str:
    model = data.get("model")
    if isinstance(model, dict):
        return str(model.get("display_name") or model.get("id") or "AGY")
    if model:
        return str(model)
    return "AGY"


def _parse_bucket(
    bucket: Any, elapsed_since_rx: float
) -> Optional[Tuple[float, str]]:
    if not isinstance(bucket, dict):
        return None

    frac = bucket.get("remaining_fraction")
    if frac is None:
        frac = bucket.get("remainingFraction")
    if frac is None:
        pct_val = bucket.get("remaining_percentage")
        if pct_val is None:
            return None
        try:
            pct = clamp_pct(float(pct_val))
        except (TypeError, ValueError):
            return None
    else:
        try:
            fval = float(frac)
            pct = clamp_pct(fval * 100.0 if fval <= 1.0 else fval)
        except (TypeError, ValueError):
            return None

    reset_label = ""
    reset_time = bucket.get("reset_time") or bucket.get("resetTime")
    if isinstance(reset_time, str) and reset_time:
        secs = seconds_until_iso(reset_time)
        if secs is not None:
            reset_label = format_duration(secs)
    elif bucket.get("reset_in_seconds") is not None:
        try:
            secs = int(float(bucket["reset_in_seconds"]) - elapsed_since_rx)
            reset_label = format_duration(secs)
        except (TypeError, ValueError):
            pass

    return pct, reset_label


def parse_quota(
    data: Dict[str, Any], model_name: str, elapsed_since_rx: float
) -> Optional[Dict[str, Any]]:
    raw = data.get("quota")
    if not isinstance(raw, dict) or not raw:
        return None

    # Flat quota object (single bucket)
    direct = _parse_bucket(raw, elapsed_since_rx)
    if direct is not None:
        pct, reset_label = direct
        return {"pct": pct, "reset": reset_label, "weekly_pct": None}

    # Bucketed quota map (e.g. gemini-5h / gemini-weekly / 3p-5h / 3p-weekly)
    is_gemini = "gemini" in model_name.lower()
    primary_order = (
        ("gemini-5h", "gemini-weekly", "3p-5h", "3p-weekly")
        if is_gemini
        else ("3p-5h", "3p-weekly", "gemini-5h", "gemini-weekly")
    )
    weekly_key = "gemini-weekly" if is_gemini else "3p-weekly"

    primary = None
    primary_key = None
    for key in primary_order:
        parsed = _parse_bucket(raw.get(key), elapsed_since_rx)
        if parsed is not None:
            primary = parsed
            primary_key = key
            break

    if primary is None:
        for key, val in raw.items():
            parsed = _parse_bucket(val, elapsed_since_rx)
            if parsed is not None:
                primary = parsed
                primary_key = key
                break

    if primary is None:
        return None

    pct, reset_label = primary
    weekly_pct = None
    if weekly_key != primary_key:
        weekly = _parse_bucket(raw.get(weekly_key), elapsed_since_rx)
        if weekly is not None:
            weekly_pct = weekly[0]

    return {"pct": pct, "reset": reset_label, "weekly_pct": weekly_pct}


def parse_context(data: Dict[str, Any]) -> Tuple[float, float]:
    """Return (used_pct, remaining_pct) clamped to [0.0, 100.0]."""
    cw = data.get("context_window")
    if not isinstance(cw, dict):
        return 0.0, 100.0

    used_raw = cw.get("used_percentage")
    if used_raw is not None:
        try:
            used = clamp_pct(float(used_raw))
            return used, clamp_pct(100.0 - used)
        except (TypeError, ValueError):
            pass

    rem_raw = cw.get("remaining_percentage")
    if rem_raw is not None:
        try:
            rem = clamp_pct(float(rem_raw))
            return clamp_pct(100.0 - rem), rem
        except (TypeError, ValueError):
            pass

    try:
        window_size = float(cw.get("context_window_size") or 0)
    except (TypeError, ValueError):
        window_size = 0.0

    if window_size > 0:
        used_tokens = cw.get("used_tokens")
        if used_tokens is None and isinstance(cw.get("current_usage"), dict):
            cu = cw["current_usage"]
            used_tokens = sum(
                float(cu.get(k) or 0)
                for k in (
                    "input_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                    "output_tokens",
                )
            )
        if used_tokens is not None:
            try:
                used = clamp_pct((float(used_tokens) / window_size) * 100.0)
                return used, clamp_pct(100.0 - used)
            except (TypeError, ValueError):
                pass

    return 0.0, 100.0


# ── Tip Rotator (in-memory, no temp files) ─────────────────────────────────────
class TipRotator:
    def __init__(self, tips: List[str], interval: float) -> None:
        self._tips = list(tips)
        self._interval = interval
        self._pool: List[str] = []
        self._current: str = ""
        self._switched_at: float = 0.0

    def current(self, now: float) -> str:
        if not self._tips:
            return ""
        if self._current and (now - self._switched_at) < self._interval:
            return self._current
        if not self._pool:
            self._pool = list(self._tips)
            random.shuffle(self._pool)
            if len(self._pool) > 1 and self._pool[-1] == self._current:
                self._pool[0], self._pool[-1] = self._pool[-1], self._pool[0]
        self._current = self._pool.pop()
        self._switched_at = now
        return self._current


# ── Renderer ───────────────────────────────────────────────────────────────────
SEP = f" {GRAY}│{RESET} "


def render(
    data: Dict[str, Any],
    rotator: TipRotator,
    received_at: float,
    now: float,
) -> str:
    elapsed = max(0.0, now - received_at)

    # 1. Model
    model_name = parse_model_name(data)
    model_seg = f"{YELLOW}{BOLD}{model_name}{RESET}"

    # 2. Quota progress bar (remaining)
    quota = parse_quota(data, model_name, elapsed)
    if quota is not None:
        q_pct = quota["pct"]
        qc = quota_color(q_pct)
        q_bar = render_bar(q_pct, qc)
        reset_seg = f"{GRAY} · {quota['reset']}{RESET}" if quota["reset"] else ""
        weekly_seg = ""
        if quota["weekly_pct"] is not None:
            w_pct = quota["weekly_pct"]
            wc = quota_color(w_pct)
            weekly_seg = f" {GRAY}({RESET}{wc}7d {w_pct:.0f}%{RESET}{GRAY}){RESET}"
        quota_seg = f"{qc}Quota{RESET} {q_bar} {qc}{q_pct:.0f}%{RESET}{reset_seg}{weekly_seg}"
    else:
        quota_seg = f"{GRAY}Quota /usage{RESET}"

    # 3. Context window progress bar
    used_pct, rem_pct = parse_context(data)
    cc = context_color(used_pct)
    if CTX_MODE == "remaining":
        c_bar = render_bar(rem_pct, cc)
        ctx_seg = f"{cc}Context{RESET} {c_bar} {cc}{rem_pct:.0f}% left{RESET}"
    else:
        c_bar = render_bar(used_pct, cc)
        ctx_seg = f"{cc}Context{RESET} {c_bar} {cc}{used_pct:.0f}%{RESET}"

    row1 = f"{model_seg}{SEP}{quota_seg}{SEP}{ctx_seg}"
    if not SHOW_TIPS:
        return row1

    # 4. Row 2: dynamic alert or rotating Chinese slash-command tip
    cycle_mode = str(data.get("cycle_mode") or "").strip().lower()
    if data.get("tool_confirmation_pending"):
        row2_body = f"{AMBER}⏳ 等待你确认操作 — 请按界面提示选择允许或拒绝{RESET}"
    elif used_pct >= 80.0:
        row2_body = (
            f"{ORANGE}⚠️ 上下文已用 {used_pct:.0f}% — 建议输入 /compact 压缩历史释放空间{RESET}"
        )
    elif cycle_mode in MODE_LABELS:
        row2_body = (
            f"{CYAN}🧭 当前为 {MODE_LABELS[cycle_mode]}{RESET}"
            f"  {GRAY}│{RESET}  "
            f"{BLUE}💡 {rotator.current(now)}{RESET}"
        )
    else:
        row2_body = f"{BLUE}💡 {rotator.current(now)}{RESET}"

    return f"{row1}\n  {row2_body}"


# ── Stream Loop ────────────────────────────────────────────────────────────────
def main() -> None:
    stdin_fd = sys.stdin.fileno()
    utf8 = codecs.getincrementaldecoder("utf-8")("replace")
    decoder = json.JSONDecoder()
    rotator = TipRotator(COMMAND_TIPS, TIP_INTERVAL)

    buf = ""
    last_data: Optional[Dict[str, Any]] = None
    last_rx_time = 0.0
    last_draw_time = 0.0

    while True:
        try:
            ready, _, _ = select.select([stdin_fd], [], [], 1.0)
            now = time.time()

            if ready:
                raw = os.read(stdin_fd, 4096)
                if not raw:
                    break
                buf += utf8.decode(raw)

                latest_payload: Optional[Dict[str, Any]] = None
                while buf:
                    stripped = buf.lstrip()
                    if not stripped:
                        buf = ""
                        break
                    try:
                        obj, end_idx = decoder.raw_decode(stripped)
                        buf = stripped[end_idx:]
                        if isinstance(obj, dict) and (
                            "model" in obj or "context_window" in obj or "quota" in obj
                        ):
                            latest_payload = obj
                    except json.JSONDecodeError:
                        # Discard non-JSON noise prefix if buffer grows unexpectedly
                        if len(stripped) > 262144:
                            brace = stripped.find("{", 1)
                            buf = stripped[brace:] if brace != -1 else ""
                        break

                if latest_payload is not None:
                    last_data = latest_payload
                    last_rx_time = now
                    print(render(last_data, rotator, last_rx_time, now), flush=True)
                    last_draw_time = now

            elif last_data is not None and SHOW_TIPS:
                if (now - last_draw_time) >= TIP_INTERVAL:
                    print(render(last_data, rotator, last_rx_time, now), flush=True)
                    last_draw_time = now

        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(0.05)


if __name__ == "__main__":
    main()
