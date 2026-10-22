#!/usr/bin/env python3
"""幂等合并/移除 ~/.codex/config.toml 中 super-memory 的沙箱放行配置。

把记忆目录加入 [sandbox_workspace_write].writable_roots 后，codex 沙箱可直接
读写记忆目录，记忆更新不再触发审批，规避 approvals_reviewer = "auto_review"
在缺少 codex-auto-review 通道的网关上持续 503 的问题。

用法:
  codex_config.py install --codex-home ~/.codex --memory-dir ~/.super-memory
  codex_config.py remove  --codex-home ~/.codex --memory-dir ~/.super-memory

合并失败（配置含内联表/点键等非常规写法）时不改动原文件，打印手动配置指引。
"""

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

TABLE = "sandbox_workspace_write"
KEY = "writable_roots"
MARK_START = "# >>> super-memory: codex sandbox 直接读写记忆目录（避免审批 503） >>>"
MARK_END = "# <<< super-memory <<<"

HEADER_RE = re.compile(r"^\s*\[sandbox_workspace_write\]\s*(?:#.*)?$")
ANY_HEADER_RE = re.compile(r"^\s*\[")
ASSIGN_RE = re.compile(r"^(\s*)writable_roots\s*=")

# 常见顶层键——出现在 [sandbox_workspace_write] 里说明表头贴错了位置（吞掉了顶层配置）
TOP_LEVEL_KEYS = (
    "model",
    "model_provider",
    "model_reasoning_effort",
    "model_reasoning_summary",
    "disable_response_storage",
    "approval_policy",
    "approvals_reviewer",
    "sandbox_mode",
    "profile",
    "notify",
)

MANUAL_SNIPPET = """\
    请手动在 {cfg} 中加入（保留已有 writable_roots 项）：

    [sandbox_workspace_write]
    writable_roots = ["{mem}"]
"""


def _toml_str(s):
    return json.dumps(str(s), ensure_ascii=False)


def _norm(p):
    return os.path.normpath(os.path.expanduser(str(p)))


def _contains(roots, mem):
    m = _norm(mem)
    return any(_norm(r) == m for r in roots)


def _roots_of(data):
    return (data.get(TABLE) or {}).get(KEY) or []


def _find_section(lines):
    """返回 [sandbox_workspace_write] 表的 (起始行, 结束行) 行号区间，不存在返回 None。"""
    start = None
    for i, ln in enumerate(lines):
        if HEADER_RE.match(ln):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if ANY_HEADER_RE.match(lines[j]):
            end = j
            break
    return start, end


def _assignment_span(lines, start):
    """从赋值行开始，按引号感知的方括号配平找到整个 writable_roots 赋值的结束行。"""
    depth = 0
    seen_open = False
    for i in range(start, len(lines)):
        in_str = None
        esc = False
        for ch in lines[i]:
            if in_str:
                if in_str == '"' and esc:
                    esc = False
                elif in_str == '"' and ch == "\\":
                    esc = True
                elif ch == in_str:
                    in_str = None
            else:
                if ch in "\"'":
                    in_str = ch
                elif ch == "[":
                    depth += 1
                    seen_open = True
                elif ch == "]":
                    depth -= 1
                elif ch == "#":
                    break
        if not seen_open:
            return start  # 非标量数组写法异常，只替换首行，交给校验兜底
        if depth <= 0:
            return i
    return len(lines) - 1


def _find_assignment(lines, sec):
    s, e = sec
    for i in range(s + 1, e):
        if ASSIGN_RE.match(lines[i]):
            return i
    return None


def _write_verified(cfg, text, expect):
    """写入前重新解析校验；校验不过则原文件不动。返回 0/1。"""
    try:
        data = tomllib.loads(text)
        ok = bool(expect(data))
    except Exception:
        ok = False
    if not ok:
        print(
            f"[super-memory] ⚠️  自动合并结果未通过 TOML 校验（配置可能含内联表/点键等写法），"
            f"{cfg} 未改动。",
            file=sys.stderr,
        )
        print(MANUAL_SNIPPET.format(cfg=cfg, mem=expect.mem), file=sys.stderr)
        return 1
    backup = cfg.with_name(cfg.name + ".super-memory.bak")
    try:
        shutil.copy2(cfg, backup)
    except OSError:
        backup = None
    fd, tmp = tempfile.mkstemp(dir=str(cfg.parent), prefix=cfg.name + ".")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, cfg)
    msg = f"[super-memory] 已更新 {cfg}"
    if backup:
        msg += f"（备份: {backup}）"
    print(msg)
    return 0


def _warn_posture(data):
    misplaced = [k for k in TOP_LEVEL_KEYS if k in (data.get(TABLE) or {})]
    if misplaced:
        print(
            f"[super-memory] ⚠️  检测到 {TABLE} 表内混入了顶层配置键: {', '.join(misplaced)}。\n"
            "    TOML 中表头之后的键都属于该表，这些键放在表内会被 codex 忽略\n"
            "    （典型后果：model_provider 失效 → 报 API key 无效）。\n"
            "    请把它们移到 config.toml 顶部、[sandbox_workspace_write] 表头之前。",
            file=sys.stderr,
        )
    reviewer = str(data.get("approvals_reviewer", "")).strip()
    if reviewer == "auto_review":
        print(
            "[super-memory] ⚠️  检测到 approvals_reviewer = \"auto_review\"。\n"
            "    若你的模型网关没有 codex-auto-review 通道，需要审批的写入会持续 503。\n"
            "    已将记忆目录加入 writable_roots，记忆写入通常不再触发审批；\n"
            "    若仍遇到 503，请在 config.toml 顶层设置 approvals_reviewer = \"user\"\n"
            "    并完全退出重启 codex。重启后仍被强制为 auto_review 说明被组织托管策略覆盖，"
            "需管理员调整或让网关提供 codex-auto-review 通道。",
            file=sys.stderr,
        )
    mode = str(data.get("sandbox_mode", "")).strip()
    if mode == "read-only":
        print(
            "[super-memory] ⚠️  sandbox_mode = \"read-only\"：writable_roots 不生效，"
            "记忆写入仍需审批。\n"
            "    建议改为 sandbox_mode = \"workspace-write\" 配合 writable_roots 使用。",
            file=sys.stderr,
        )


def cmd_install(cfg, mem):
    if not cfg.exists():
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(
            f"{MARK_START}\n[{TABLE}]\n{KEY} = [{_toml_str(mem)}]\n{MARK_END}\n"
        )
        print(f"[super-memory] 已创建 {cfg} 并放行 {mem}")
        return 0

    text = cfg.read_text()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        print(f"[super-memory] ⚠️  {cfg} 解析失败（{e}），未改动。", file=sys.stderr)
        print(MANUAL_SNIPPET.format(cfg=cfg, mem=mem), file=sys.stderr)
        return 1

    roots = _roots_of(data)
    if _contains(roots, mem):
        print(f"[super-memory] {mem} 已在 {KEY} 中，无需改动")
        _warn_posture(data)
        return 0

    new_roots = [str(r) for r in roots] + [mem]
    new_line = f"{KEY} = [{', '.join(_toml_str(r) for r in new_roots)}]"
    lines = text.splitlines()
    sec = _find_section(lines)
    if sec is None:
        lines += ["", MARK_START, f"[{TABLE}]", new_line, MARK_END]
    else:
        ai = _find_assignment(lines, sec)
        if ai is None:
            lines = lines[: sec[0] + 1] + [new_line] + lines[sec[0] + 1 :]
        else:
            indent = ASSIGN_RE.match(lines[ai]).group(1)
            lines = lines[:ai] + [indent + new_line] + lines[_assignment_span(lines, ai) + 1 :]

    def expect(d):
        return _contains(_roots_of(d), mem)

    expect.mem = mem
    rc = _write_verified(cfg, "\n".join(lines) + "\n", expect)
    if rc == 0:
        print(f"[super-memory] 已放行记忆目录 {mem}（codex 沙箱可直接读写，记忆更新不触发审批）")
        _warn_posture(tomllib.loads(cfg.read_text()))
    return rc


def cmd_remove(cfg, mem):
    if not cfg.exists():
        return 0
    text = cfg.read_text()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return 0  # 解析失败的文件不碰
    roots = _roots_of(data)
    if not _contains(roots, mem):
        return 0

    lines = text.splitlines()
    remaining = [str(r) for r in roots if _norm(r) != _norm(mem)]
    sec_keys = set((data.get(TABLE) or {}).keys())

    def find_mark(marker):
        for i, ln in enumerate(lines):
            if ln.strip() == marker:
                return i
        return None

    ms, me = find_mark(MARK_START), find_mark(MARK_END)
    if ms is not None and me is not None and ms < me and sec_keys == {KEY} and not remaining:
        # 整个表都是 super-memory 装的，连标记块一起删
        del lines[ms : me + 1]
        while lines and not lines[-1].strip():
            lines.pop()
        new_text = ("\n".join(lines) + "\n") if lines else ""
    else:
        sec = _find_section(lines)
        ai = _find_assignment(lines, sec) if sec else None
        if ai is not None:
            indent = ASSIGN_RE.match(lines[ai]).group(1)
            new_line = indent + KEY + " = [" + ", ".join(_toml_str(r) for r in remaining) + "]"
            lines = lines[:ai] + [new_line] + lines[_assignment_span(lines, ai) + 1 :]
        new_text = "\n".join(lines) + "\n"

    def expect(d):
        return not _contains(_roots_of(d), mem)

    expect.mem = mem
    rc = _write_verified(cfg, new_text, expect)
    if rc == 0:
        if cfg.exists() and not cfg.read_text().strip():
            cfg.unlink()
        print(f"[super-memory] 已从 {KEY} 移除 {mem}")
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["install", "remove"])
    ap.add_argument("--codex-home", required=True)
    ap.add_argument("--memory-dir", required=True)
    a = ap.parse_args()
    cfg = Path(a.codex_home).expanduser() / "config.toml"
    mem = str(Path(a.memory_dir).expanduser())
    return cmd_install(cfg, mem) if a.action == "install" else cmd_remove(cfg, mem)


if __name__ == "__main__":
    sys.exit(main())
