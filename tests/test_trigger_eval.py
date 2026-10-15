"""tools/trigger_eval.py 的单元测试：用合成输出样本验证信号判定与容错。"""

import json
import os
import sys

from helpers import ROOT

TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import trigger_eval  # noqa: E402

SKILL = "embedded-register-lookup"


def _write(tmp_path, name, lines):
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_claude_launch_marker_counts_as_triggered(tmp_path):
    line = json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "content": "Launching skill: " + SKILL}]}}, ensure_ascii=False)
    path = _write(tmp_path, "p01.jsonl", [line])
    signals, hit = trigger_eval.detect_claude(path, SKILL, "lookup.py")
    assert hit
    assert signals["launch"]


def test_claude_slash_commands_pollution_is_not_a_trigger(tmp_path):
    init = {"type": "system", "subtype": "init", "slash_commands": [SKILL, "keil"], "model": "x"}
    path = _write(tmp_path, "n01.jsonl", [json.dumps(init, ensure_ascii=False)])
    _, hit = trigger_eval.detect_claude(path, SKILL, "lookup.py")
    assert not hit


def test_claude_script_run_with_subcommand_counts(tmp_path):
    line = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash",
         "input": {"command": "python \"C:/Users/x/.claude/skills/embedded-register-lookup/scripts/lookup.py\" lookup GPIOA.CRL --chip STM32F103C8"}}]}},
        ensure_ascii=False)
    path = _write(tmp_path, "p02.jsonl", [line])
    signals, hit = trigger_eval.detect_claude(path, SKILL, "lookup.py")
    assert hit
    assert signals["script"]


def test_claude_doc_example_text_is_not_a_run(tmp_path):
    doc = ("```bash\npython scripts/lookup.py lookup USART1.CR1.UE --chip STM32G431\n"
           "python scripts/lookup.py addr 0x4001380C --chip STM32G431\n```")
    line = json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "content": doc}]}}, ensure_ascii=False)
    path = _write(tmp_path, "n04.jsonl", [line])
    _, hit = trigger_eval.detect_claude(path, SKILL, "lookup.py")
    assert not hit


def test_claude_bare_filename_in_listing_is_not_a_run(tmp_path):
    line = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls scripts/"}}], },
        "note": "lookup.py\n__init__.py\n"}, ensure_ascii=False)
    path = _write(tmp_path, "n02.jsonl", [line])
    _, hit = trigger_eval.detect_claude(path, SKILL, "lookup.py")
    assert not hit


def test_opencode_skill_load_and_run(tmp_path):
    events = [
        {"type": "step_start"},
        {"type": "tool_use", "part": {"type": "tool", "tool": "skill",
         "state": {"input": {"name": SKILL}, "output": "..."}}},
        {"type": "tool_use", "part": {"type": "tool", "tool": "bash",
         "state": {"input": {"command": "python \"C:/x/skills/embedded-register-lookup/scripts/lookup.py\" lookup TIM2.CR1 --chip STM32F103C8"}}}},
        {"type": "text", "part": {"type": "text", "text": "答案"}},
    ]
    path = _write(tmp_path, "p03.jsonl", [json.dumps(e, ensure_ascii=False) for e in events])
    signals, hit = trigger_eval.detect_opencode(path, SKILL, "lookup.py")
    assert hit
    assert signals["skill_loads"] == 1
    assert signals["script_runs"] == 1


def test_opencode_output_mention_is_not_a_trigger(tmp_path):
    events = [
        {"type": "tool_use", "part": {"type": "tool", "tool": "bash",
         "state": {"input": {"command": "ls ~/.agents/skills"},
                   "output": SKILL + "\nother-skill"}}},
        {"type": "text", "part": {"type": "text", "text": "没有用到该技能"}},
    ]
    path = _write(tmp_path, "n03.jsonl", [json.dumps(e, ensure_ascii=False) for e in events])
    _, hit = trigger_eval.detect_opencode(path, SKILL, "lookup.py")
    assert not hit


def test_opencode_tolerates_control_characters_bom_and_broken_lines(tmp_path):
    good = ('{"type":"tool_use","part":{"type":"tool","tool":"bash","state":'
            '{"input":{"command":"python x/lookup.py decode RCC.CR 0x1"},'
            '"output":"ok' + chr(27) + '[1Gdone"}}}')
    path = tmp_path / "p04.jsonl"
    path.write_text("\ufeff" + good + "\n---broken---\n", encoding="utf-8")
    signals, hit = trigger_eval.detect_opencode(str(path), SKILL, "lookup.py")
    assert hit
    assert signals["script_runs"] == 1


def test_evaluate_and_summarize(tmp_path):
    _write(tmp_path, "p01.jsonl", [json.dumps({"type": "tool_use", "part": {
        "type": "tool", "tool": "skill", "state": {"input": {"name": SKILL}}}}, ensure_ascii=False)])
    _write(tmp_path, "n01.jsonl", [json.dumps({"type": "text", "part": {
        "type": "text", "text": "普通回答"}}, ensure_ascii=False)])
    rows = trigger_eval.evaluate(str(tmp_path), "opencode", SKILL, "lookup.py")
    s = trigger_eval.summarize(rows)
    assert s["total"] == 2
    assert s["correct"] == 2
    assert s["accuracy"] == 1.0
