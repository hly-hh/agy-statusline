#!/usr/bin/env python3
"""Minimalist Status Line for Antigravity CLI (`agy`).

Reads the JSON telemetry stream piped by `agy` on stdin and renders a
balanced, full-width two-line terminal status bar:
  Row 1: Model │ 5h Quota bar (+ reset) │ 7d Quota bar (+ reset) │ Context bar
  Row 2: Dynamic alerts or steady rotating Chinese tips (left)
         + Short mode label, rotating anime-girl kaomoji & tip counter (right)

Zero third-party dependencies. Compatible with Python 3.8+.
"""

import codecs
import json
import os
import random
import re
import select
import signal
import sys
import time
import unicodedata
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
PINK = "\033[38;5;212m"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


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


BAR_WIDTH_EXPLICIT = "AGY_STATUS_BAR_WIDTH" in os.environ
BAR_WIDTH = _env_int("AGY_STATUS_BAR_WIDTH", 10, 4, 30)
TIP_INTERVAL = _env_float("AGY_STATUS_TIP_INTERVAL", 8.0, 2.0)
KAOMOJI_INTERVAL = _env_float("AGY_STATUS_KAOMOJI_INTERVAL", 4.0, 1.0)
WIDTH_MARGIN = _env_int("AGY_STATUS_MARGIN", 4, 0, 20)
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

# Short mode labels: mode_key -> (short_text, color)
MODE_SHORT: Dict[str, Tuple[str, str]] = {
    "": ("默认", GRAY),
    "default": ("默认", GRAY),
    "normal": ("默认", GRAY),
    "plan": ("规划", CYAN),
    "auto": ("自动", PURPLE),
    "accept-edits": ("改写", AMBER),
}

# Rotating anime-girl kaomoji sets
KAOMOJI_NORMAL: List[str] = [
    "(ﾉ◕ヮ◕)ﾉ*:･ﾟ✧",
    "(｡･ω･｡)ﾉ♡",
    "(๑•̀ㅂ•́)و✧",
    "(*≧ω≦)",
    "(つ≧▽≦)つ",
    "(・ω<)☆",
    "(✿◠‿◠)",
    "(๑´ڡ`๑)",
    "٩(◕‿◕｡)۶",
    "(≧◡≦)♡",
    "(｡•̀ᴗ-)✧",
    "(ฅ'ω'ฅ)",
    "(oﾟvﾟ)ノ",
    "(*^▽^*)",
    "(☆▽☆)",
    "(๑>؂<๑)۶",
]

KAOMOJI_CONFIRM: List[str] = [
    "(｡•́︿•̀｡)",
    "(・_・?)",
    "(つ﹏⊂)",
    "(๑•́ ₃ •̀๑)",
]

KAOMOJI_ALERT: List[str] = [
    "(⊙_⊙;)",
    "(；´Д｀)",
    "(°ロ°)!",
    "(ﾟДﾟ;)",
]


# ── Terminal Width & Display-Width Helpers ─────────────────────────────────────
def char_width(ch: str) -> int:
    code = ord(ch)
    if code < 32 or (0x7F <= code < 0xA0):
        return 0
    if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    return 1


def display_width(text: str) -> int:
    """Calculate terminal column width, ignoring ANSI codes and handling CJK/emoji."""
    plain = ANSI_RE.sub("", text)
    width = 0
    n = len(plain)
    i = 0
    while i < n:
        ch = plain[i]
        if i + 1 < n and plain[i + 1] == "\ufe0f":
            w = char_width(ch)
            width += max(w, 2) if w > 0 else 0
            i += 2
            continue
        width += char_width(ch)
        i += 1
    return width


def truncate_ansi(text: str, max_width: int) -> str:
    """Truncate ANSI-styled text cleanly to <= max_width terminal columns."""
    if max_width <= 0:
        return ""
    if display_width(text) <= max_width:
        return text
    if max_width == 1:
        return "…"

    limit = max_width - 1
    out: List[str] = []
    width = 0
    has_ansi = False
    pos = 0
    n = len(text)

    while pos < n:
        if text[pos] == "\x1b":
            m = ANSI_RE.match(text, pos)
            if m:
                out.append(m.group(0))
                has_ansi = True
                pos = m.end()
                continue

        ch = text[pos]
        step = 1
        if pos + 1 < n and text[pos + 1] == "\ufe0f":
            w = char_width(ch)
            cw = max(w, 2) if w > 0 else 0
            step = 2
        else:
            cw = char_width(ch)

        if width + cw > limit:
            break

        out.append(text[pos : pos + step])
        width += cw
        pos += step

        # Keep trailing combining marks attached to the included base char
        while pos < n and text[pos] != "\x1b" and char_width(text[pos]) == 0:
            out.append(text[pos])
            pos += 1

    out.append("…")
    if has_ansi:
        out.append(RESET)
    return "".join(out)


def detect_terminal_width(data: Dict[str, Any]) -> int:
    """Detect current terminal width in columns (0 if unavailable)."""
    env_w = os.environ.get("AGY_STATUS_WIDTH")
    if env_w:
        try:
            w = int(env_w)
            if w > 0:
                return w
        except ValueError:
            pass

    for key in ("terminal_width", "columns", "width"):
        val = data.get(key)
        if val is not None:
            try:
                w = int(val)
                if w > 0:
                    return w
            except (TypeError, ValueError):
                pass

    term_obj = data.get("terminal")
    if isinstance(term_obj, dict):
        for key in ("width", "columns", "cols"):
            val = term_obj.get(key)
            if val is not None:
                try:
                    w = int(val)
                    if w > 0:
                        return w
                except (TypeError, ValueError):
                    pass

    # Query /dev/tty live so terminal window resizes are reflected immediately
    try:
        tty_fd = os.open("/dev/tty", os.O_RDONLY | os.O_NOCTTY)
        try:
            cols = os.get_terminal_size(tty_fd).columns
            if cols > 0:
                return cols
        finally:
            os.close(tty_fd)
    except OSError:
        pass

    for stream in (sys.stdout, sys.stderr):
        try:
            cols = os.get_terminal_size(stream.fileno()).columns
            if cols > 0:
                return cols
        except OSError:
            pass

    env_cols = os.environ.get("COLUMNS")
    if env_cols:
        try:
            cols = int(env_cols)
            if cols > 0:
                return cols
        except ValueError:
            pass

    return 0


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
    """Compact Arabic-numeral countdown (e.g. 45m, 3h20m, 4d6h)."""
    if seconds <= 0:
        return "0m"
    minutes = (seconds + 59) // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, rem_mins = divmod(minutes, 60)
    if hours >= 24:
        days, rem_hours = divmod(hours, 24)
        return f"{days}d{rem_hours}h" if rem_hours else f"{days}d"
    return f"{hours}h{rem_mins}m" if rem_mins else f"{hours}h"


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
) -> List[Dict[str, Any]]:
    """Return a list of quota bars: [{'label': '5h'|'7d'|'Quota', 'pct': float, 'reset': str}]."""
    raw = data.get("quota")
    if not isinstance(raw, dict) or not raw:
        return []

    # Flat quota object (single bucket)
    direct = _parse_bucket(raw, elapsed_since_rx)
    if direct is not None:
        pct, reset_label = direct
        return [{"label": "Quota", "pct": pct, "reset": reset_label}]

    # Bucketed quota map (e.g. gemini-5h / gemini-weekly / 3p-5h / 3p-weekly)
    is_gemini = "gemini" in model_name.lower()
    primary_order = (
        ("gemini-5h", "gemini-weekly", "3p-5h", "3p-weekly")
        if is_gemini
        else ("3p-5h", "3p-weekly", "gemini-5h", "gemini-weekly")
    )

    primary: Optional[Tuple[float, str]] = None
    primary_key: Optional[str] = None
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
                primary_key = str(key)
                break

    if primary is None or primary_key is None:
        return []

    pk_lower = primary_key.lower()
    if "5h" in pk_lower:
        primary_label = "5h"
    elif "weekly" in pk_lower or "7d" in pk_lower:
        primary_label = "7d"
    else:
        primary_label = "Quota"

    bars: List[Dict[str, Any]] = [
        {"label": primary_label, "pct": primary[0], "reset": primary[1]}
    ]

    # Pair with matching weekly bucket from the same model family
    if primary_label != "7d":
        if pk_lower.startswith("gemini"):
            weekly_candidates = ("gemini-weekly",)
        elif pk_lower.startswith("3p"):
            weekly_candidates = ("3p-weekly",)
        else:
            weekly_candidates = (
                ("gemini-weekly", "3p-weekly")
                if is_gemini
                else ("3p-weekly", "gemini-weekly")
            )

        for wkey in weekly_candidates:
            if wkey == primary_key:
                continue
            weekly = _parse_bucket(raw.get(wkey), elapsed_since_rx)
            if weekly is not None:
                bars.append({"label": "7d", "pct": weekly[0], "reset": weekly[1]})
                break

    return bars


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


# ── Deterministic Wall-Clock Slot Rotator (zero temp files, exact cadence) ────
class TimeSlotRotator:
    """Steady time-slot rotator consistent across both streaming & one-shot runs."""

    def __init__(self, items: List[str], interval: float, seed: int = 0) -> None:
        self._items = list(items)
        self._interval = max(1.0, float(interval))
        self._seed = seed
        self._cached_cycle: Optional[int] = None
        self._cached_order: List[int] = []

    def slot_at(self, now: float) -> int:
        return int(now // self._interval)

    def next_switch_time(self, now: float) -> float:
        return (self.slot_at(now) + 1) * self._interval

    def _shuffled_cycle(self, cycle: int) -> List[int]:
        n = len(self._items)
        order = list(range(n))
        if n <= 2:
            return order
        rng = random.Random((cycle * 2654435761) ^ self._seed)
        rng.shuffle(order)
        return order

    def _order_for_cycle(self, cycle: int) -> List[int]:
        n = len(self._items)
        if n <= 2:
            return list(range(n))
        order = self._shuffled_cycle(cycle)
        if cycle > 0:
            # Swapping indices 0 and 1 keeps order[-1] invariant across cycles
            prev_last = self._shuffled_cycle(cycle - 1)[-1]
            if order[0] == prev_last:
                order[0], order[1] = order[1], order[0]
        return order

    def current(self, now: float) -> Tuple[str, int, int]:
        """Return (item, 1-based position in current cycle, total count)."""
        n = len(self._items)
        if n == 0:
            return "", 0, 0
        slot = self.slot_at(now)
        cycle, pos = divmod(slot, n)
        if self._cached_cycle != cycle:
            self._cached_order = self._order_for_cycle(cycle)
            self._cached_cycle = cycle
        return self._items[self._cached_order[pos]], pos + 1, n


# ── Layout Helpers ─────────────────────────────────────────────────────────────
SEP = f" {GRAY}│{RESET} "


def spread_segments(segments: List[str], target_width: int) -> str:
    """Spread segments evenly across target_width with centered │ dividers."""
    if not segments:
        return ""
    if len(segments) == 1 or target_width <= 0:
        return SEP.join(segments)

    widths = [display_width(seg) for seg in segments]
    gaps_count = len(segments) - 1
    free_space = target_width - sum(widths)

    # Minimum 3 columns per gap (" │ ")
    if free_space < gaps_count * 3:
        return SEP.join(segments)

    base_gap, extra = divmod(free_space, gaps_count)
    parts: List[str] = [segments[0]]
    for idx in range(gaps_count):
        gap = base_gap + (1 if idx < extra else 0)
        left_pad = (gap - 1) // 2
        right_pad = gap - 1 - left_pad
        parts.append(f"{' ' * left_pad}{GRAY}│{RESET}{' ' * right_pad}")
        parts.append(segments[idx + 1])
    return "".join(parts)


def align_left_right(left: str, right: str, target_width: int) -> str:
    """Align left and right blocks to edges of target_width without wrapping."""
    if not right:
        return truncate_ansi(left, target_width) if target_width > 0 else left
    if target_width <= 0:
        return f"{left}{SEP}{right}"

    left_w = display_width(left)
    right_w = display_width(right)
    min_gap = 2

    if left_w + right_w + min_gap <= target_width:
        pad = target_width - left_w - right_w
        return f"{left}{' ' * pad}{right}"

    avail_left = target_width - right_w - min_gap
    if avail_left >= 12:
        clipped_left = truncate_ansi(left, avail_left)
        pad = max(min_gap, target_width - display_width(clipped_left) - right_w)
        return f"{clipped_left}{' ' * pad}{right}"

    return truncate_ansi(f"{left}{SEP}{right}", target_width)


# ── Renderer ───────────────────────────────────────────────────────────────────
def _choose_bar_width(target_width: int, num_bars: int) -> int:
    if BAR_WIDTH_EXPLICIT or target_width <= 0 or num_bars <= 2:
        return BAR_WIDTH
    if target_width >= 104:
        return BAR_WIDTH
    if target_width >= 90:
        return min(BAR_WIDTH, 8)
    return min(BAR_WIDTH, 6)


def _format_mode_short(cycle_mode: str) -> str:
    if cycle_mode in MODE_SHORT:
        label, color = MODE_SHORT[cycle_mode]
        weight = BOLD if cycle_mode not in ("", "default", "normal") else ""
        return f"{color}{weight}{label}{RESET}"
    return f"{CYAN}{BOLD}{cycle_mode[:6]}{RESET}"


def render(
    data: Dict[str, Any],
    tip_rotator: TimeSlotRotator,
    kaomoji_normal: TimeSlotRotator,
    kaomoji_confirm: TimeSlotRotator,
    kaomoji_alert: TimeSlotRotator,
    received_at: float,
    now: float,
) -> str:
    elapsed = max(0.0, now - received_at)
    term_width = detect_terminal_width(data)
    target_width = max(40, term_width - WIDTH_MARGIN) if term_width > 0 else 0

    # 1. Model
    model_name = parse_model_name(data)
    model_seg = f"{YELLOW}{BOLD}{model_name}{RESET}"

    # 2. Quota progress bars (5h + 7d independently, each with compact reset time)
    quota_bars = parse_quota(data, model_name, elapsed)
    bar_w = _choose_bar_width(target_width, len(quota_bars) + 1)

    segments: List[str] = [model_seg]
    if quota_bars:
        for qb in quota_bars:
            q_pct = qb["pct"]
            qc = quota_color(q_pct)
            q_bar = render_bar(q_pct, qc, width=bar_w)
            reset_seg = f" {GRAY}{qb['reset']}{RESET}" if qb["reset"] else ""
            segments.append(
                f"{qc}{qb['label']}{RESET} {q_bar} {qc}{q_pct:.0f}%{RESET}{reset_seg}"
            )
    else:
        segments.append(f"{GRAY}Quota /usage{RESET}")

    # 3. Context window progress bar
    used_pct, rem_pct = parse_context(data)
    cc = context_color(used_pct)
    ctx_label = "Context" if (target_width == 0 or target_width >= 100) else "Ctx"
    if CTX_MODE == "remaining":
        c_bar = render_bar(rem_pct, cc, width=bar_w)
        ctx_seg = f"{cc}{ctx_label}{RESET} {c_bar} {cc}{rem_pct:.0f}%{RESET}"
    else:
        c_bar = render_bar(used_pct, cc, width=bar_w)
        ctx_seg = f"{cc}{ctx_label}{RESET} {c_bar} {cc}{used_pct:.0f}%{RESET}"
    segments.append(ctx_seg)

    row1 = spread_segments(segments, target_width)
    if not SHOW_TIPS:
        return row1

    # 4. Row 2: left = alert/rotating tip, right = short mode + anime-girl kaomoji + counter
    cycle_mode = str(data.get("cycle_mode") or "").strip().lower()
    mode_seg = _format_mode_short(cycle_mode)

    if data.get("tool_confirmation_pending"):
        row2_left = f"{AMBER}⏳ 等待你确认操作 — 请按界面提示选择允许或拒绝{RESET}"
        kao, _, _ = kaomoji_confirm.current(now)
        row2_right = f"{mode_seg} {AMBER}{kao}{RESET}"
    elif used_pct >= 80.0:
        row2_left = (
            f"{ORANGE}⚠️ 上下文已用 {used_pct:.0f}% — 建议输入 /compact 压缩历史释放空间{RESET}"
        )
        kao, _, _ = kaomoji_alert.current(now)
        row2_right = f"{mode_seg} {ORANGE}{kao}{RESET}"
    else:
        tip_text, tip_pos, tip_total = tip_rotator.current(now)
        kao, _, _ = kaomoji_normal.current(now)
        row2_left = f"{BLUE}💡 {tip_text}{RESET}"
        counter_seg = f" {GRAY}{tip_pos}/{tip_total}{RESET}" if tip_total > 0 else ""
        row2_right = f"{mode_seg} {PINK}{kao}{RESET}{counter_seg}"

    row2 = align_left_right(row2_left, row2_right, target_width)
    return f"{row1}\n{row2}"


# ── Stream Loop ────────────────────────────────────────────────────────────────
def main() -> None:
    stdin_fd = sys.stdin.fileno()
    utf8 = codecs.getincrementaldecoder("utf-8")("replace")
    decoder = json.JSONDecoder()

    tip_rotator = TimeSlotRotator(COMMAND_TIPS, TIP_INTERVAL, seed=101)
    kaomoji_normal = TimeSlotRotator(KAOMOJI_NORMAL, KAOMOJI_INTERVAL, seed=202)
    kaomoji_confirm = TimeSlotRotator(KAOMOJI_CONFIRM, KAOMOJI_INTERVAL, seed=303)
    kaomoji_alert = TimeSlotRotator(KAOMOJI_ALERT, KAOMOJI_INTERVAL, seed=404)

    buf = ""
    last_data: Optional[Dict[str, Any]] = None
    last_rx_time = 0.0
    last_draw_time = 0.0
    last_slots: Optional[Tuple[int, int]] = None
    winch_received = False

    def _on_winch(_signum: int, _frame: Any) -> None:
        nonlocal winch_received
        winch_received = True

    if hasattr(signal, "SIGWINCH"):
        try:
            signal.signal(signal.SIGWINCH, _on_winch)
        except Exception:
            pass

    def _draw(now_ts: float) -> None:
        nonlocal last_draw_time, last_slots, winch_received
        assert last_data is not None
        out = render(
            last_data,
            tip_rotator,
            kaomoji_normal,
            kaomoji_confirm,
            kaomoji_alert,
            last_rx_time,
            now_ts,
        )
        print(out, flush=True)
        last_draw_time = now_ts
        last_slots = (tip_rotator.slot_at(now_ts), kaomoji_normal.slot_at(now_ts))
        winch_received = False

    while True:
        try:
            now = time.time()
            if last_data is not None and SHOW_TIPS:
                next_wake = min(
                    tip_rotator.next_switch_time(now),
                    kaomoji_normal.next_switch_time(now),
                )
                timeout = max(0.05, min(1.0, next_wake - now + 0.02))
            else:
                timeout = 1.0

            ready, _, _ = select.select([stdin_fd], [], [], timeout)
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
                    _draw(now)

            elif last_data is not None:
                cur_slots = (tip_rotator.slot_at(now), kaomoji_normal.slot_at(now))
                if winch_received:
                    _draw(now)
                elif SHOW_TIPS and cur_slots != last_slots:
                    _draw(now)
                elif not SHOW_TIPS and (now - last_draw_time) >= 30.0:
                    _draw(now)

        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(0.05)


if __name__ == "__main__":
    main()
