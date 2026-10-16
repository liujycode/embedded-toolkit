#!/usr/bin/env python3
"""触发评测运行器：把 tests/trigger/<skill>.json 的用例逐条跑成无头 Agent 输出。

用法：
  python tools/trigger_run.py --agent claude  --skill embedded-register-verify --out <目录>
  python tools/trigger_run.py --agent opencode --skill embedded-register-lookup --out <目录>
判定（离线，见 tools/trigger_eval.py）：
  python tools/trigger_eval.py --dir <目录> --agent claude --skill embedded-register-verify \
      --script verify.py --subcommands check,rules

说明：
- 每条用例一次独立无头会话；工作目录为空临时目录，避免用例句/仓库文件污染（第一轮教训）；
- 输出逐例 <out>/<id>.jsonl（p 开头正例、n 开头反例）；失败写 <id>.error.txt 并继续；
- --only p01,n02 只跑指定用例；--timeout 每例超时秒数（默认 300）。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load_cases(skill):
    path = os.path.join(ROOT, "tests", "trigger", "%s.json" % skill)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    cases = []
    for index, text in enumerate(data.get("positive", []), 1):
        cases.append(("p%02d" % index, "positive", text))
    for index, text in enumerate(data.get("negative", []), 1):
        cases.append(("n%02d" % index, "negative", text))
    return cases


def build_command(agent, exe, prompt):
    if agent == "claude":
        return [exe, "-p", prompt, "--output-format", "stream-json", "--verbose",
                "--allowedTools", "Skill Bash Read Glob Grep"]
    if agent == "opencode":
        return [exe, "run", "--format", "json", "--auto", prompt]
    raise ValueError("未知 agent：%s" % agent)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="触发评测运行器（无头 Agent）")
    parser.add_argument("--agent", required=True, choices=("claude", "opencode"))
    parser.add_argument("--skill", required=True)
    parser.add_argument("--out", required=True, help="输出目录（逐例 .jsonl）")
    parser.add_argument("--only", help="只跑指定用例（逗号分隔，如 p01,n02）")
    parser.add_argument("--timeout", type=int, default=300, help="每例超时秒数（默认 300）")
    args = parser.parse_args(argv)

    exe = shutil.which(args.agent)
    if not exe:
        print("找不到命令：%s" % args.agent)
        return 1
    out_dir = os.path.abspath(args.out)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    work_dir = tempfile.mkdtemp(prefix="etk-trigger-")
    cases = load_cases(args.skill)
    if args.only:
        wanted = {item.strip() for item in args.only.split(",") if item.strip()}
        cases = [case for case in cases if case[0] in wanted]
    print("agent=%s skill=%s 用例=%d 输出=%s 工作目录=%s" % (
        args.agent, args.skill, len(cases), out_dir, work_dir))
    failures = 0
    for case_id, expect, prompt in cases:
        out_path = os.path.join(out_dir, "%s.jsonl" % case_id)
        err_path = os.path.join(out_dir, "%s.error.txt" % case_id)
        cmd = build_command(args.agent, exe, prompt)
        start = time.time()
        status = "ok"
        try:
            with open(out_path, "wb") as fh:
                proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE,
                                      cwd=work_dir, timeout=args.timeout)
            if proc.returncode != 0:
                status = "rc=%d" % proc.returncode
                with open(err_path, "wb") as fh:
                    fh.write(proc.stderr or b"")
        except subprocess.TimeoutExpired:
            status = "timeout"
            failures += 1
        except Exception as exc:  # 兜底：记录并继续
            status = "error"
            with open(err_path, "w", encoding="utf-8") as fh:
                fh.write(repr(exc))
            failures += 1
        size = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
        if status.startswith("rc="):
            failures += 1
        print("%s %-9s %6.1fs %8dB %s" % (case_id, expect, time.time() - start, size, status))
        sys.stdout.flush()
    print("完成：%d 例，失败 %d 例（失败文件 <id>.error.txt 可查）" % (len(cases), failures))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
