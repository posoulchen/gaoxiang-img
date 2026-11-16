# -*- coding: utf-8 -*-
"""云端版发送器：在 GitHub Actions 里跑，电脑关机也能发。

环境变量：
  DINGTALK_WEBHOOK   必填
  DINGTALK_SECRET    必填（加签）
  GITHUB_TOKEN       用于读写 state/ 去重标记（workflow 自带）
  REPO               形如 owner/repo
  DAY_OVERRIDE       可选，指定第几天（测试用）
  DRY_RUN            true 时只打印消息摘要，不发
  PING               true 时只发一条连通性测试消息
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CST = timezone(timedelta(hours=8))
WEEK_CN = "一二三四五六日"


def log(msg: str) -> None:
    print(msg, flush=True)


def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def convert_markdown(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        is_row = line.lstrip().startswith("|")
        is_sep = i + 1 < len(lines) and set(lines[i + 1].strip().strip("|").replace(" ", "")) <= set("-:|")
        if is_row and is_sep:
            header = [c.strip() for c in line.strip().strip("|").split("|") if c.strip()]
            if header:
                out.append("**" + " ｜ ".join(header) + "**")
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|") if c.strip()]
                if cells:
                    out.append("· " + " ｜ ".join(cells))
                i += 1
            continue
        line = line.replace("- [ ] ", "- ").replace("- [x] ", "- ")
        if line.strip() and set(line.strip()) <= set("-*") and len(line.strip()) >= 3:
            line = "──────────"
        out.append(line)
        i += 1
    return "\n".join(out)


def split_text(text: str, limit: int) -> list[str]:
    chunks, buf, size = [], [], 0
    for line in text.split("\n"):
        if size + len(line) + 1 > limit and buf:
            chunks.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line) + 1
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def gh(method: str, path: str, body: dict | None = None) -> dict | None:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("REPO", "")
    if not token or not repo:
        return None
    url = f"https://api.github.com/repos/{repo}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "gaoxiang100-cloud",
    }
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def already_sent(day_key: str) -> bool:
    return gh("GET", f"contents/state/sent-{day_key}.txt") is not None


def mark_sent(day_key: str, content: str) -> None:
    body = {
        "message": f"sent {day_key}",
        "content": base64.b64encode(content.encode()).decode(),
    }
    gh("PUT", f"contents/state/sent-{day_key}.txt", body)


def send_dingtalk(title: str, text: str) -> int:
    webhook = os.environ.get("DINGTALK_WEBHOOK", "")
    secret = os.environ.get("DINGTALK_SECRET", "")
    if not webhook:
        log("FAIL DINGTALK_WEBHOOK 未配置")
        return 2
    url = webhook
    if secret:
        ts = str(int(time.time() * 1000))
        digest = hmac.new(secret.encode(), f"{ts}\n{secret}".encode(), hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest).decode())
        url += ("&" if "?" in url else "?") + f"timestamp={ts}&sign={sign}"
    payload = {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode())
    if resp.get("errcode") != 0:
        log(f"FAIL dingtalk errcode={resp.get('errcode')} {resp.get('errmsg')}")
        return 3
    return 0


def build_message(n: int, plan: dict) -> tuple[str, str]:
    entry = next(d for d in plan["days"] if int(d["day"]) == n)
    md = (ROOT / "days" / f"day-{n:03d}.md").read_text(encoding="utf-8")
    body = md.split("\n", 1)[1] if md.startswith("# ") else md
    body = convert_markdown(body)

    head = f"**高项100天** ｜ Day {n:03d}/100\n\n"
    fig = ROOT / "days" / "fig" / f"day-{n:03d}.json"
    if fig.exists():
        spec = load_json(fig)
        rows = []
        for b in (spec.get("branches") or [])[:4]:
            items = " / ".join((b.get("items") or [])[:3])
            t = b["title"].split("：")[0].strip("、，,：: ")
            rows.append(f"· {t[:20]}" + (f"：{items}" if items else ""))
        if rows:
            head += "🗺 **今日地图**\n" + "\n".join(rows) + "\n\n"

    kind_line = {"套卷": "套卷 1 套 · 限时", "案例": "案例专项 · 精讲 1 篇", "冲刺": "速记为主 · 5 题"}.get(
        entry["kind"], "精讲 1 篇 · 单选 8 题 · 自测 6 项")
    head += f"⏱ 约 {entry['minutes']} 分钟 ｜ {kind_line}\n\n"

    repo = os.environ.get("REPO", "")
    base = f"https://ghproxy.net/https://raw.githubusercontent.com/{repo}/main/img"
    if (ROOT / "img" / f"day-{n:03d}-map.png").exists():
        head += f"🖼 **知识地图**\n![]({base}/day-{n:03d}-map.png)\n\n"
    tail = ""
    if (ROOT / "img" / f"day-{n:03d}-memo.png").exists():
        tail = f"🖼 **记忆卡（口诀＋三个坑）**\n![]({base}/day-{n:03d}-memo.png)\n\n"

    foot = tail + (f"\n──────────\n💻 完整图文版：https://ghproxy.net/https://raw.githubusercontent.com/"
                   f"{repo}/main/days/day-{n:03d}.html\n完成今日任务后，在本群回复「打卡」。"
                   if (ROOT / "days" / f"day-{n:03d}.html").exists()
                   else f"\n──────────\n完成今日任务后，在本群回复「打卡」。")

    title = f"高项100天 · Day {n:03d}｜{entry['date'][5:7]}月{entry['date'][8:10]}日（周{entry['weekday']}）"
    return title, head + body + foot


def main() -> int:
    now = datetime.now(CST)
    today = now.date().isoformat()
    plan = load_json(ROOT / "plan" / "plan.json")
    repo = os.environ.get("REPO", "")

    if os.environ.get("PING") == "true":
        return send_dingtalk("高项100天 · 云端测试",
                             f"**云端定时任务连通性测试**\n\n{GITHUB_REPOSITORY_NOTE}\n发送时间：{now:%Y-%m-%d %H:%M}（北京时间）")

    override = os.environ.get("DAY_OVERRIDE", "").strip()
    if override:
        n = int(override)
    else:
        entry = next((d for d in plan["days"] if d["date"] == today), None)
        if not entry:
            log(f"SKIP {today} 不是计划内的学习日")
            return 0
        n = int(entry["day"])

    if not override and already_sent(today):
        log(f"SKIP {today} 已有发送记录（电脑端已发或已补发）")
        return 0

    title, text = build_message(n, plan)
    chunks = split_text(text, 11000)
    if os.environ.get("DRY_RUN") == "true":
        mp = (ROOT / "img" / f"day-{n:03d}-map.png").exists()
        mm = (ROOT / "img" / f"day-{n:03d}-memo.png").exists()
        log(f"DRY-RUN day={n} chars={len(text)} chunks={len(chunks)} title={title} map={mp} memo={mm}")
        log(text[:400])
        return 0

    for i, chunk in enumerate(chunks):
        t = title if len(chunks) == 1 else f"{title}（{i+1}/{len(chunks)}）"
        rc = send_dingtalk(t, chunk)
        if rc:
            return rc
        if i < len(chunks) - 1:
            time.sleep(1.5)
    log(f"OK day={n:03d} 已推送 {len(chunks)} 条")
    if not override:
        mark_sent(today, f"day {n:03d} at {datetime.now(CST):%Y-%m-%d %H:%M:%S} CST")
    return 0


GITHUB_REPOSITORY_NOTE = "仓库：" + os.environ.get("REPO", "")

if __name__ == "__main__":
    sys.exit(main())
