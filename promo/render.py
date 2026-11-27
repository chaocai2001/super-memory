#!/usr/bin/env python3
import argparse
import bisect
import functools
import math
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
FPS = 30
DURATION = 30
ROOT = Path(__file__).resolve().parent
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"
MONO_PATH = "/System/Library/Fonts/Menlo.ttc"
WHITE = (242, 245, 255)
MUTED = (151, 163, 190)
DIM = (95, 108, 138)
PURPLE = (157, 134, 255)
CYAN = (91, 226, 207)
BLUE = (99, 145, 255)
PANEL = (15, 22, 38, 242)
BORDER = (74, 89, 125, 120)
CUTS = [0, 4, 9, 14, 22, 26.5, 30]
TRANSITION = 0.4
LANG = "zh"
TRANSLATIONS = {
    "换个 Agent，": "Switch agents,",
    "记忆就清零？": "lose your context?",
    "项目背景，不必再从头讲一遍。": "Stop re-explaining your project in every new session.",
    "项目约定：使用 pnpm": "Convention: use pnpm",
    "缺少项目背景…": "Missing project context…",
    "# 项目约定": "# Project conventions",
    "包管理器": "Package manager",
    "已写入长期记忆": "Saved to long-term memory",
    "01  写入一次": "01  Remember once",
    "记住：这个项目统一使用 pnpm。": "Remember: this project uses pnpm.",
    "已提炼为项目约定": "Saved as a project convention",
    "记忆将在新会话中自动召回": "Recalled automatically in new sessions",
    "会话结束，结论留下。": "The session ends. The knowledge stays.",
    "不是聊天记录堆积": "NOT ANOTHER PILE OF CHAT LOGS",
    "而是一份消化过的知识": "Knowledge, distilled.",
    "• 包管理器统一使用 pnpm": "• Use pnpm as the package manager",
    "• 架构决策与踩坑结论持续合并": "• Decisions and lessons, merged",
    "• 每条知识都可回溯来源": "• Every fact links back to its source",
    "架构决策": "Architecture",
    "踩坑与解法": "Pitfalls & fixes",
    "用户偏好": "Preferences",
    "环境事实": "Environment",
    "本地纯 Markdown，不锁定任何平台": "Local plain Markdown. No platform lock-in.",
    "可见    ·    可改    ·    可用 Git 管理": "Visible  ·  Editable  ·  Git-ready",
    "02  随时召回": "02  Recall anywhere",
    "这个项目该用什么包管理器？": "Which package manager does this project use?",
    "这个项目统一使用 ": "This project uses ",
    "。": ".",
    "FROM super-memory  ·  已召回项目约定": "FROM super-memory  ·  Project convention recalled",
    "无需重复解释背景，直接继续工作。": "No re-explaining. Just keep building.",
    "一份记忆，连接所有 coding agents": "One memory for all your coding agents",
    "跨会话 · 跨 harness": "Cross-session · Cross-harness",
    "无向量数据库": "No vector database",
    "无需额外 API Key": "No extra API key",
    "让记忆跟着人走，不跟着工具走。": "Memory follows you, not your tools.",
}


def translate(value):
    return TRANSLATIONS.get(value, value) if LANG == "en" else value


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def smooth(value):
    value = clamp(value)
    return value * value * (3 - 2 * value)


def out_cubic(value):
    return 1 - (1 - clamp(value)) ** 3


def enter(t, start=0, duration=0.7):
    return out_cubic((t - start) / duration)


def rgba(color, alpha=255):
    return (*color[:3], int(clamp(alpha, 0, 255)))


@functools.lru_cache(maxsize=128)
def font(size, bold=False, mono=False):
    path = MONO_PATH if mono else FONT_PATH
    index = 1 if mono and bold else 2 if bold else 0
    return ImageFont.truetype(path, size, index=index)


def text(im, xy, value, size, color=WHITE, bold=False, mono=False, anchor="la", alpha=255):
    value = translate(value)
    ImageDraw.Draw(im).text(
        xy,
        value,
        font=font(size, bold, mono),
        fill=rgba(color, alpha),
        anchor=anchor,
    )


def line(im, points, color=BORDER, width=2, alpha=255):
    ImageDraw.Draw(im).line(points, fill=rgba(color, alpha), width=width)


def panel(im, box, fill=PANEL, outline=BORDER, radius=28, alpha=255):
    layer = Image.new("RGBA", im.size)
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=rgba(fill, alpha), outline=rgba(outline, alpha), width=2)
    x1, y1, x2, _ = box
    d.line((x1 + radius, y1 + 1, x2 - radius, y1 + 1), fill=rgba((210, 220, 255), alpha * 0.12), width=2)
    im.alpha_composite(layer)


def composite(base, layer, opacity=1):
    if opacity <= 0:
        return
    if opacity < 1:
        layer.putalpha(layer.getchannel("A").point(lambda p: int(p * opacity)))
    base.alpha_composite(layer)


def pill(im, center, label, size=24, color=PURPLE, width=None, alpha=255):
    label = translate(label)
    f = font(size, True)
    bounds = f.getbbox(label)
    tw = bounds[2] - bounds[0]
    w = width or tw + 48
    h = size + 28
    x, y = center
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(
        (x - w / 2, y - h / 2, x + w / 2, y + h / 2),
        radius=h / 2,
        fill=rgba(color, alpha * 0.11),
        outline=rgba(color, alpha * 0.35),
        width=1,
    )
    text(im, center, label, size, color, True, anchor="mm", alpha=alpha)


@functools.lru_cache(maxsize=16)
def glow_sprite(size, color):
    yy, xx = np.mgrid[0:size, 0:size]
    radius = np.sqrt((xx - size / 2) ** 2 + (yy - size / 2) ** 2) / (size / 2)
    alpha = np.clip(1 - radius, 0, 1) ** 2
    data = np.zeros((size, size, 4), dtype=np.uint8)
    data[:, :, :3] = color
    data[:, :, 3] = (alpha * 105).astype(np.uint8)
    return Image.fromarray(data, "RGBA")


def glow(im, center, size, color, opacity=1):
    sprite = glow_sprite(size, color).copy()
    if opacity < 1:
        sprite.putalpha(sprite.getchannel("A").point(lambda p: int(p * opacity)))
    im.alpha_composite(sprite, (int(center[0] - size / 2), int(center[1] - size / 2)))


def logo(im, x, y, scale=1, name=True, alpha=255):
    d = ImageDraw.Draw(im)
    s = scale
    d.rounded_rectangle(
        (x, y, x + 56 * s, y + 64 * s),
        radius=13 * s,
        fill=rgba(PURPLE, alpha * 0.14),
        outline=rgba(PURPLE, alpha * 0.8),
        width=max(1, int(2 * s)),
    )
    for offset, width in [(18, 27), (30, 34), (42, 22)]:
        d.rounded_rectangle(
            (x + 12 * s, y + offset * s, x + (12 + width) * s, y + (offset + 4) * s),
            radius=2 * s,
            fill=rgba(CYAN if offset == 30 else WHITE, alpha * 0.9),
        )
    d.polygon(
        [
            (x + 48 * s, y + 2 * s),
            (x + 52 * s, y + 12 * s),
            (x + 62 * s, y + 16 * s),
            (x + 52 * s, y + 20 * s),
            (x + 48 * s, y + 30 * s),
            (x + 44 * s, y + 20 * s),
            (x + 34 * s, y + 16 * s),
            (x + 44 * s, y + 12 * s),
        ],
        fill=rgba(CYAN, alpha),
    )
    if name:
        text(im, (x + 76 * s, y + 31 * s), "super memory", int(34 * s), WHITE, True, anchor="lm", alpha=alpha)


def terminal_header(im, box, title_value, accent=PURPLE):
    x1, y1, x2, _ = box
    line(im, (x1, y1 + 74, x2, y1 + 74), BORDER, 2)
    d = ImageDraw.Draw(im)
    for i, color in enumerate([(255, 111, 117), (255, 194, 99), (91, 213, 143)]):
        x = x1 + 34 + i * 28
        d.ellipse((x, y1 + 31, x + 12, y1 + 43), fill=rgba(color, 210))
    text(im, (x1 + 140, y1 + 38), title_value, 24, MUTED, mono=True, anchor="lm")
    d.ellipse((x2 - 42, y1 + 31, x2 - 30, y1 + 43), fill=rgba(accent, 230))


def typed(value, t, start, cps=13):
    value = translate(value)
    count = int(clamp((t - start) * cps, 0, len(value)))
    return value[:count]


def make_base():
    yy = np.linspace(0, 1, H)[:, None, None]
    top = np.array([7, 11, 23])[None, None, :]
    bottom = np.array([10, 15, 29])[None, None, :]
    rgb = top * (1 - yy) + bottom * yy
    rgb = np.repeat(rgb, W, axis=1).astype(np.uint8)
    im = Image.fromarray(rgb, "RGB").convert("RGBA")
    d = ImageDraw.Draw(im)
    for x in range(0, W, 80):
        d.line((x, 0, x, H), fill=(16, 23, 40, 255), width=1)
    for y in range(0, H, 80):
        d.line((0, y, W, y), fill=(16, 23, 40, 255), width=1)
    return im


BASE = make_base()
RNG = np.random.default_rng(7)
PARTICLES = [(int(x), int(y), float(s), float(p)) for x, y, s, p in zip(
    RNG.integers(30, W - 30, 36), RNG.integers(30, H - 30, 36), RNG.uniform(0.5, 1.5, 36), RNG.uniform(0, 6.28, 36)
)]


def background(t):
    im = BASE.copy()
    glow(im, (280 + 70 * math.sin(t * 0.12), 180), 850, PURPLE, 0.72)
    glow(im, (1650 + 80 * math.cos(t * 0.1), 850), 900, BLUE, 0.48)
    d = ImageDraw.Draw(im)
    for x, y, speed, phase in PARTICLES:
        a = int(18 + 14 * math.sin(t * speed + phase))
        d.ellipse((x, y, x + 2, y + 2), fill=(170, 190, 255, max(3, a)))
    return im


def scene_one(t, global_t):
    im = background(global_t)
    logo(im, 92, 64, 0.85)
    layer = Image.new("RGBA", im.size)
    pill(layer, (960, 208), "FOR AI CODING AGENTS", 22, PURPLE)
    text(layer, (960, 332), "换个 Agent，", 88, WHITE, True, anchor="mm")
    text(layer, (960, 442), "记忆就清零？", 96, PURPLE, True, anchor="mm")
    text(layer, (960, 558), "项目背景，不必再从头讲一遍。", 34, MUTED, anchor="mm")
    composite(im, layer, enter(t, 0.15, 0.9))

    cards = Image.new("RGBA", im.size)
    left = (322, 680, 822, 886)
    right = (1098, 680, 1598, 886)
    panel(cards, left)
    panel(cards, right)
    terminal_header(cards, left, "Codex · previous session")
    terminal_header(cards, right, "Claude Code · new session", CYAN)
    text(cards, (362, 790), "项目约定：使用 pnpm", 27, DIM, mono=False)
    text(cards, (362, 840), "session ended", 22, DIM, mono=True)
    text(cards, (1138, 790), "缺少项目背景…", 28, MUTED)
    text(cards, (1138, 840), "context not found", 22, DIM, mono=True)
    d = ImageDraw.Draw(cards)
    d.line((872, 783, 1048, 783), fill=rgba(DIM, 160), width=3)
    d.line((945, 757, 985, 809), fill=rgba((255, 116, 136), 220), width=5)
    d.line((985, 757, 945, 809), fill=rgba((255, 116, 136), 220), width=5)
    composite(im, cards, enter(t, 1.1, 0.8))
    return im


def wiki_page(im, box, t, compact=False):
    x1, y1, x2, y2 = box
    panel(im, box, (17, 25, 43, 248), (128, 112, 220, 150), 26)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((x1 + 32, y1 + 29, x1 + 56, y1 + 61), radius=4, outline=rgba(PURPLE, 220), width=2)
    for offset in (39, 47, 55):
        d.line((x1 + 38, y1 + offset, x1 + 50, y1 + offset), fill=rgba(CYAN, 200), width=2)
    filename = "project.md" if compact else "project-conventions.md"
    text(im, (x1 + 76, y1 + 45), filename, 22 if compact else 25, MUTED, mono=True, anchor="lm")
    line(im, (x1 + 30, y1 + 84, x2 - 30, y1 + 84), BORDER)
    heading = "# Convention" if compact and LANG == "en" else "# 项目约定"
    text(im, (x1 + 36, y1 + 128), heading, 28 if compact else 34, WHITE, True, anchor="lm")
    text(im, (x1 + 36, y1 + 190), "包管理器", 22, MUTED, anchor="lm")
    text(im, (x1 + 36, y1 + 266), "pnpm", 62 if compact else 76, CYAN, True, mono=True, anchor="lm")
    if not compact:
        pill(im, ((x1 + x2) / 2, y2 - 70), "已写入长期记忆", 22, CYAN, width=320 if LANG == "en" else 250)


def scene_two(t, global_t):
    im = background(global_t)
    logo(im, 92, 60, 0.8)
    header = Image.new("RGBA", im.size)
    text(header, (100, 158), "01  写入一次", 58, WHITE, True, anchor="lm")
    text(header, (1810, 158), "Codex  →  super-memory", 25, PURPLE, mono=True, anchor="rm")
    composite(im, header, enter(t, 0.05, 0.6))

    term = Image.new("RGBA", im.size)
    box = (100, 250, 1200, 865)
    panel(term, box)
    terminal_header(term, box, "Codex · project-api")
    text(term, (148, 382), "›", 38, PURPLE, mono=True, anchor="lm")
    prompt = "记住：这个项目统一使用 pnpm。"
    typed_prompt = typed(prompt, t, 0.65, 18 if LANG == "en" else 11)
    text(term, (192, 382), typed_prompt, 34, WHITE, anchor="lm")
    if 0.65 < t < 2.95 and int(t * 3) % 2 == 0:
        width = font(34).getlength(typed_prompt)
        line(term, (196 + width, 356, 196 + width, 406), PURPLE, 3)
    if t > 2.35:
        response = Image.new("RGBA", im.size)
        panel(response, (142, 490, 1128, 650), (13, 40, 43, 210), (72, 190, 170, 100), 22)
        d = ImageDraw.Draw(response)
        d.line((182, 548, 192, 559), fill=rgba(CYAN, 255), width=4)
        d.line((192, 559, 214, 533), fill=rgba(CYAN, 255), width=4)
        text(response, (232, 548), "已提炼为项目约定", 31, CYAN, True, anchor="lm")
        text(response, (182, 605), "记忆将在新会话中自动召回", 24, MUTED, anchor="lm")
        composite(term, response, enter(t, 2.35, 0.55))
    text(term, (148, 770), "会话结束，结论留下。", 28, MUTED, anchor="lm")
    composite(im, term, enter(t, 0.25, 0.7))

    page = Image.new("RGBA", im.size)
    wiki_page(page, (1300, 285, 1800, 815), t)
    composite(im, page, enter(t, 1.85, 0.75))

    if 1.8 < t < 3.4:
        p = smooth((t - 1.8) / 1.2)
        x = 1215 + 70 * p
        glow(im, (x, 555), 130, CYAN, 0.8)
        d = ImageDraw.Draw(im)
        d.ellipse((x - 7, 548, x + 7, 562), fill=rgba(CYAN, 240))
    return im


def memory_chip(im, center, label, color, t, delay):
    layer = Image.new("RGBA", im.size)
    pill(layer, center, label, 25, color, width=250)
    composite(im, layer, enter(t, delay, 0.6))


def scene_three(t, global_t):
    im = background(global_t)
    logo(im, 92, 60, 0.8)
    layer = Image.new("RGBA", im.size)
    text(layer, (960, 150), "不是聊天记录堆积", 28, MUTED, anchor="mm")
    text(layer, (960, 225), "而是一份消化过的知识", 62, WHITE, True, anchor="mm")
    composite(im, layer, enter(t, 0.1, 0.7))

    page = Image.new("RGBA", im.size)
    box = (600, 310, 1320, 820)
    panel(page, box, (17, 25, 43, 248), (128, 112, 220, 150), 28)
    text(page, (650, 362), "wiki/pages/project.md", 24, PURPLE, mono=True, anchor="lm")
    line(page, (640, 405, 1280, 405), BORDER)
    text(page, (650, 460), "# 项目约定", 40, WHITE, True, anchor="lm")
    text(page, (650, 538), "• 包管理器统一使用 pnpm", 30, CYAN, anchor="lm")
    text(page, (650, 598), "• 架构决策与踩坑结论持续合并", 28, WHITE, anchor="lm")
    text(page, (650, 658), "• 每条知识都可回溯来源", 28, WHITE, anchor="lm")
    line(page, (650, 710, 1270, 710), BORDER)
    text(page, (650, 760), "PLAIN MARKDOWN  ·  LOCAL FIRST", 22, MUTED, mono=True, anchor="lm")
    composite(im, page, enter(t, 0.45, 0.8))

    memory_chip(im, (330, 405), "架构决策", PURPLE, t, 0.9)
    memory_chip(im, (300, 570), "踩坑与解法", BLUE, t, 1.15)
    memory_chip(im, (1590, 405), "用户偏好", CYAN, t, 1.35)
    memory_chip(im, (1620, 570), "环境事实", PURPLE, t, 1.6)
    connector = Image.new("RGBA", im.size)
    for points in [((455, 405), (590, 430)), ((425, 570), (590, 560)), ((1330, 430), (1465, 405)), ((1330, 560), (1495, 570))]:
        line(connector, points, BORDER, 2)
    composite(im, connector, enter(t, 1.2, 0.8))

    features = Image.new("RGBA", im.size)
    text(features, (960, 910), "本地纯 Markdown，不锁定任何平台", 30, MUTED, anchor="mm")
    text(features, (960, 975), "可见    ·    可改    ·    可用 Git 管理", 30, CYAN, True, anchor="mm")
    composite(im, features, enter(t, 1.65, 0.75))
    return im


def scene_four(t, global_t):
    im = background(global_t)
    logo(im, 92, 60, 0.8)
    header = Image.new("RGBA", im.size)
    text(header, (100, 155), "02  随时召回", 58, WHITE, True, anchor="lm")
    text(header, (1810, 155), "super-memory  →  Claude Code", 25, CYAN, mono=True, anchor="rm")
    composite(im, header, enter(t, 0.05, 0.6))

    page = Image.new("RGBA", im.size)
    wiki_page(page, (100, 340, 410, 760), t, compact=True)
    composite(im, page, enter(t, 0.45, 0.7))

    term = Image.new("RGBA", im.size)
    box = (490, 240, 1810, 875)
    panel(term, box)
    terminal_header(term, box, "Claude Code · new session", CYAN)
    pill(term, (1635, 285), "NEW SESSION", 17, CYAN, width=190)
    text(term, (545, 390), "›", 38, CYAN, mono=True, anchor="lm")
    prompt = "这个项目该用什么包管理器？"
    value = typed(prompt, t, 0.9, 22 if LANG == "en" else 12)
    text(term, (590, 390), value, 35, WHITE, anchor="lm")
    if 0.9 < t < 3.2 and int(t * 3) % 2 == 0:
        width = font(35).getlength(value)
        line(term, (594 + width, 363, 594 + width, 416), CYAN, 3)
    if t > 3.0:
        answer = Image.new("RGBA", im.size)
        panel(answer, (540, 492, 1755, 704), (13, 40, 43, 215), (72, 190, 170, 115), 22)
        prefix = translate("这个项目统一使用 ")
        text(answer, (585, 552), prefix, 34, WHITE, anchor="lm")
        pnpm_x = 585 + font(34).getlength(prefix)
        text(answer, (pnpm_x, 552), "pnpm", 38, CYAN, True, mono=True, anchor="lm")
        suffix_x = pnpm_x + font(38, True, True).getlength("pnpm")
        text(answer, (suffix_x, 552), "。", 34, WHITE, anchor="lm")
        line(answer, (585, 615, 1695, 615), (72, 190, 170, 80), 1)
        text(answer, (585, 657), "FROM super-memory  ·  已召回项目约定", 24, CYAN, anchor="lm")
        composite(term, answer, enter(t, 3.0, 0.65))
    if t > 5.0:
        note = Image.new("RGBA", im.size)
        text(note, (1150, 792), "无需重复解释背景，直接继续工作。", 29, MUTED, anchor="mm")
        composite(term, note, enter(t, 5.0, 0.7))
    composite(im, term, enter(t, 0.25, 0.75))

    if 2.4 < t < 3.8:
        p = smooth((t - 2.4) / 1.1)
        x = 420 + 60 * p
        glow(im, (x, 555), 140, CYAN, 0.8)
        ImageDraw.Draw(im).ellipse((x - 7, 548, x + 7, 562), fill=rgba(CYAN, 240))
    return im


def agent_card(im, center, label, color, t, delay):
    layer = Image.new("RGBA", im.size)
    x, y = center
    panel(layer, (x - 170, y - 60, x + 170, y + 60), (16, 24, 42, 245), rgba(color, 90), 24)
    d = ImageDraw.Draw(layer)
    d.ellipse((x - 140, y - 10, x - 120, y + 10), fill=rgba(color, 240))
    text(layer, (x - 98, y), label, 29, WHITE, True, mono=True, anchor="lm")
    composite(im, layer, enter(t, delay, 0.65))


def scene_five(t, global_t):
    im = background(global_t)
    layer = Image.new("RGBA", im.size)
    text(layer, (960, 160), "一份记忆，连接所有 coding agents", 62, WHITE, True, anchor="mm")
    text(layer, (960, 230), "MEMORY FOLLOWS YOU, NOT THE TOOL", 23, PURPLE, mono=True, anchor="mm")
    composite(im, layer, enter(t, 0.05, 0.7))

    connections = Image.new("RGBA", im.size)
    centers = [(380, 410), (380, 690), (1540, 410), (1540, 690)]
    for i, (x, y) in enumerate(centers):
        line(connections, ((x + (170 if x < 960 else -170), y), (815 if x < 960 else 1105, 550)), BORDER, 3)
    composite(im, connections, enter(t, 0.55, 0.8))

    hub = Image.new("RGBA", im.size)
    glow(hub, (960, 545), 560, PURPLE, 0.9)
    panel(hub, (790, 370, 1130, 710), (20, 27, 49, 252), (143, 123, 240, 160), 36)
    logo(hub, 925, 425, 1.2, False)
    text(hub, (960, 565), "super memory", 37, WHITE, True, anchor="mm")
    text(hub, (960, 620), "LOCAL MARKDOWN WIKI", 18, MUTED, mono=True, anchor="mm")
    composite(im, hub, enter(t, 0.35, 0.8))

    agent_card(im, centers[0], "Codex", PURPLE, t, 0.65)
    agent_card(im, centers[1], "Claude Code", CYAN, t, 0.85)
    agent_card(im, centers[2], "Kimi Code", BLUE, t, 1.05)
    agent_card(im, centers[3], "opencode", PURPLE, t, 1.25)

    if t > 1.2:
        for i, (x, y) in enumerate(centers):
            p = (t * 0.65 + i * 0.23) % 1
            start_x = x + (170 if x < 960 else -170)
            end_x = 815 if x < 960 else 1105
            px = start_x + (end_x - start_x) * p
            py = y + (550 - y) * p
            glow(im, (px, py), 90, CYAN if i % 2 else PURPLE, 0.55)
            ImageDraw.Draw(im).ellipse((px - 4, py - 4, px + 4, py + 4), fill=rgba(WHITE, 220))

    features = Image.new("RGBA", im.size)
    text(features, (960, 905), "跨会话 · 跨 harness", 28, WHITE, True, anchor="mm")
    text(features, (600, 970), "无向量数据库", 25, MUTED, anchor="mm")
    text(features, (960, 970), "·", 25, DIM, anchor="mm")
    text(features, (1270, 970), "无需额外 API Key", 25, MUTED, anchor="mm")
    composite(im, features, enter(t, 1.55, 0.8))
    return im


def scene_six(t, global_t):
    im = background(global_t)
    glow(im, (960, 450), 1100, PURPLE, 0.75 + 0.1 * math.sin(global_t))
    layer = Image.new("RGBA", im.size)
    logo(layer, 895, 190, 2.0, False)
    text(layer, (960, 405), "Super Memory", 88, WHITE, True, anchor="mm")
    text(layer, (960, 510), "让记忆跟着人走，不跟着工具走。", 42, WHITE, anchor="mm")
    composite(im, layer, enter(t, 0.1, 0.9))

    link = Image.new("RGBA", im.size)
    panel(link, (515, 625, 1405, 725), (19, 28, 47, 245), (133, 116, 225, 150), 50)
    text(link, (580, 675), "↗", 38, CYAN, anchor="mm")
    text(link, (990, 675), "github.com/chaocai2001/super-memory", 30, WHITE, mono=True, anchor="mm")
    text(link, (960, 805), "OPEN SOURCE  ·  MIT", 22, MUTED, mono=True, anchor="mm")
    composite(im, link, enter(t, 0.85, 0.8))
    return im


SCENES = [scene_one, scene_two, scene_three, scene_four, scene_five, scene_six]


def render_frame(t):
    index = min(len(SCENES) - 1, max(0, bisect.bisect_right(CUTS, t) - 1))
    local = t - CUTS[index]
    current = SCENES[index](local, t)
    if index > 0 and local < TRANSITION:
        previous = SCENES[index - 1](CUTS[index] - CUTS[index - 1], t)
        return Image.blend(previous, current, smooth(local / TRANSITION))
    return current


def render_stills(directory):
    directory.mkdir(parents=True, exist_ok=True)
    times = [2.2, 7.1, 12.1, 19.2, 24.6, 28.8]
    frames = []
    for i, t in enumerate(times, 1):
        frame = render_frame(t).convert("RGB")
        path = directory / f"scene-{i}.png"
        frame.save(path)
        frames.append(frame.resize((640, 360), Image.Resampling.LANCZOS))
    sheet = Image.new("RGB", (1920, 720), (5, 8, 16))
    for i, frame in enumerate(frames):
        sheet.paste(frame, ((i % 3) * 640, (i // 3) * 360))
    sheet.save(directory / "contact-sheet.png")


def make_audio(path):
    sample_rate = 44100
    count = sample_rate * DURATION
    audio = np.zeros((count, 2), dtype=np.float64)
    chords = [
        [130.81, 164.81, 196.00, 246.94],
        [110.00, 130.81, 164.81, 196.00],
        [87.31, 130.81, 174.61, 220.00],
        [98.00, 146.83, 196.00, 246.94],
    ]
    for chord_index, frequencies in enumerate(chords):
        start = chord_index * 7.5
        end = start + 7.5
        i0, i1 = int(start * sample_rate), int(end * sample_rate)
        tt = np.arange(i1 - i0) / sample_rate
        envelope = np.minimum(tt / 1.2, 1) * np.minimum((7.5 - tt) / 1.2, 1)
        for note_index, frequency in enumerate(frequencies):
            pad = (np.sin(2 * np.pi * frequency * tt) + 0.18 * np.sin(2 * np.pi * frequency * 2 * tt))
            audio[i0:i1, note_index % 2] += 0.013 * pad * envelope
            audio[i0:i1, 1 - note_index % 2] += 0.009 * pad * envelope
        for beat in range(15):
            onset = start + beat * 0.5
            frequency = frequencies[(beat * 3 + chord_index) % len(frequencies)] * 2
            i = int(onset * sample_rate)
            length = min(int(0.65 * sample_rate), count - i)
            tt = np.arange(length) / sample_rate
            pluck = 0.045 * np.sin(2 * np.pi * frequency * tt) * np.exp(-tt * 7)
            pluck += 0.009 * np.sin(2 * np.pi * frequency * 2.01 * tt) * np.exp(-tt * 10)
            pan = 0.25 + 0.5 * ((beat % 4) / 3)
            audio[i:i + length, 0] += pluck * (1 - pan)
            audio[i:i + length, 1] += pluck * pan
    rng = np.random.default_rng(12)
    for transition in CUTS[1:-1]:
        length = int(0.55 * sample_rate)
        tt = np.arange(length) / sample_rate
        noise = rng.normal(0, 1, length)
        noise = np.convolve(noise, np.ones(18) / 18, mode="same")
        swell = np.sin(np.pi * tt / 0.55) ** 2 * np.exp(-tt * 2)
        effect = noise * swell * 0.026
        i = int((transition - 0.3) * sample_rate)
        audio[i:i + length, 0] += effect
        audio[i:i + length, 1] += effect[::-1]
    for onset, frequency in [(6.45, 880), (9.9, 660), (17.2, 990), (27.2, 740)]:
        length = int(0.3 * sample_rate)
        tt = np.arange(length) / sample_rate
        tone = 0.028 * np.sin(2 * np.pi * frequency * tt) * np.exp(-tt * 18)
        i = int(onset * sample_rate)
        audio[i:i + length, :] += tone[:, None]
    fade = int(sample_rate * 1.2)
    audio[:fade] *= np.linspace(0, 1, fade)[:, None]
    audio[-fade:] *= np.linspace(1, 0, fade)[:, None]
    audio = np.clip(audio * 3.8, -0.85, 0.85)
    pcm = (audio * 32767).astype("<i2")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(pcm.tobytes())


def render_video(output):
    work = ROOT / ".render"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    silent = work / "silent.mp4"
    soundtrack = work / "soundtrack.wav"
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", str(silent),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    for frame_index in range(FPS * DURATION):
        frame = render_frame(frame_index / FPS).convert("RGB")
        process.stdin.write(frame.tobytes())
        if frame_index % 90 == 0:
            print(f"Rendered {frame_index}/{FPS * DURATION} frames", flush=True)
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg video encoding failed")
    make_audio(soundtrack)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(soundtrack),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", str(DURATION), "-movflags", "+faststart",
        "-metadata", "title=Super Memory — 30 second product demo", str(output),
    ], check=True)
    shutil.rmtree(work)
    print(f"Created {output}", flush=True)


def main():
    global LANG
    parser = argparse.ArgumentParser()
    parser.add_argument("--stills", action="store_true")
    parser.add_argument("--lang", choices=["zh", "en"], default="zh")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    LANG = args.lang
    output = args.output or ROOT / ("super-memory-30s-en.mp4" if LANG == "en" else "super-memory-30s.mp4")
    if args.stills:
        preview = ROOT / (".preview-en" if LANG == "en" else ".preview")
        render_stills(preview)
    else:
        render_video(output)


if __name__ == "__main__":
    main()
