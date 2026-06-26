#!/usr/bin/env python3
"""wf_watchdog — детект зависших workflow-прогонов и спасение частичного результата.

Зачем: длинные workflow (особенно Claude deep-research) иногда замолкают —
агент висит, journal перестаёт писаться. Раньше выход был один: убить и потерять
весь прогресс. Этот сторож даёт два мягких варианта вместо kill-с-нуля:

  1. STALL-детект — по времени последней записи в journal.jsonl прогона.
     Тихо дольше --idle минут → прогон считается зависшим, печатается команда
     возобновления (resumeFromRunId) — завершённые агенты вернутся из кэша,
     заново побежит только застрявший.

  2. SALVAGE — выдрать последние осмысленные ответы агентов из их транскриптов
     (agent-*.jsonl), чтобы частичные находки не пропали, даже если прогон не
     возобновляется.

Использование:
  python3 funnel/wf_watchdog.py --list [--session <dir>]
  python3 funnel/wf_watchdog.py --check <runId|wf-dir> [--idle 8]
  python3 funnel/wf_watchdog.py --salvage <runId|wf-dir> [--out FILE]

runId — это «wf_xxchunk» (имя папки прогона). По умолчанию ищем в текущей сессии
Claude Code: $CLAUDE_PROJECT_DIR/.../subagents/workflows/ или через --session.
"""
import argparse
import glob
import json
import os
import sys
import time

WF_GLOB = "**/subagents/workflows/wf_*"


def _now() -> float:
    return time.time()


def find_workflow_dirs(session: str | None) -> list[str]:
    roots = []
    if session:
        roots.append(session)
    # типичный корень транскриптов Claude Code
    home = os.path.expanduser("~/.claude/projects")
    if os.path.isdir(home):
        roots.append(home)
    seen, out = set(), []
    for root in roots:
        for d in glob.glob(os.path.join(root, WF_GLOB), recursive=True):
            if os.path.isdir(d) and d not in seen:
                seen.add(d)
                out.append(d)
    return out


def resolve_dir(token: str, session: str | None) -> str | None:
    if os.path.isdir(token):
        return token
    # токен — это runId (имя папки wf_*); ищем папку с таким хвостом
    for d in find_workflow_dirs(session):
        if os.path.basename(d) == token or os.path.basename(d).startswith(token):
            return d
    return None


def last_activity(wf_dir: str) -> tuple[float, str]:
    """Возвращает (эпоха последней записи, имя файла) по journal+агентам."""
    candidates = []
    j = os.path.join(wf_dir, "journal.jsonl")
    if os.path.exists(j):
        candidates.append(j)
    candidates += glob.glob(os.path.join(wf_dir, "agent-*.jsonl"))
    if not candidates:
        return (0.0, "")
    newest = max(candidates, key=lambda p: os.path.getmtime(p))
    return (os.path.getmtime(newest), os.path.basename(newest))


def run_id(wf_dir: str) -> str:
    return os.path.basename(wf_dir)


def cmd_list(args):
    dirs = find_workflow_dirs(args.session)
    if not dirs:
        print("workflow-прогонов не найдено")
        return 0
    dirs.sort(key=lambda d: last_activity(d)[0], reverse=True)
    print(f"{'runId':<28} {'тихо, мин':>9}  последняя запись")
    for d in dirs:
        ts, fname = last_activity(d)
        idle_min = (_now() - ts) / 60 if ts else -1
        print(f"{run_id(d):<28} {idle_min:>9.1f}  {fname}")
    return 0


def cmd_check(args):
    wf = resolve_dir(args.target, args.session)
    if not wf:
        print(f"✗ прогон не найден: {args.target}", file=sys.stderr)
        return 2
    ts, fname = last_activity(wf)
    idle_min = (_now() - ts) / 60 if ts else 1e9
    rid = run_id(wf)
    if idle_min <= args.idle:
        print(f"✓ {rid}: жив — тихо {idle_min:.1f} мин (порог {args.idle}); последняя запись {fname}")
        return 0
    print(f"⚠ {rid}: ЗАВИС — тихо {idle_min:.1f} мин (> порога {args.idle})")
    print("  НЕ убивай. Останови и возобнови — завершённые агенты вернутся из кэша:")
    print(f"    1) TaskStop по task_id этого прогона")
    print(f'    2) Workflow({{scriptPath:"<тот же скрипт>", args:<те же args>, resumeFromRunId:"{rid}"}})')
    print(f"  Или спасти частичное: python3 funnel/wf_watchdog.py --salvage {rid}")
    return 1


def _iter_assistant_texts(agent_file: str):
    """Достаёт текстовые ответы ассистента и structured-output из транскрипта агента."""
    try:
        with open(agent_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                msg = rec.get("message", {})
                for block in msg.get("content", []) or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text" and block.get("text", "").strip():
                        yield ("text", block["text"].strip())
                    elif block.get("type") == "tool_use":
                        name = block.get("name", "")
                        inp = block.get("input", {})
                        # structured output / финальные сводки агентов несут самое ценное
                        if name and inp:
                            yield ("tool:" + name, json.dumps(inp, ensure_ascii=False)[:4000])
    except OSError:
        return


def cmd_salvage(args):
    wf = resolve_dir(args.target, args.session)
    if not wf:
        print(f"✗ прогон не найден: {args.target}", file=sys.stderr)
        return 2
    agents = sorted(glob.glob(os.path.join(wf, "agent-*.jsonl")), key=os.path.getmtime)
    if not agents:
        print(f"✗ транскриптов агентов нет в {wf}", file=sys.stderr)
        return 2
    out_lines = [f"# Спасённый частичный результат прогона {run_id(wf)}", ""]
    for af in agents:
        chunks = list(_iter_assistant_texts(af))
        if not chunks:
            continue
        out_lines.append(f"## {os.path.basename(af)}")
        # берём последние ~6 осмысленных кусков — там обычно итог агента
        for kind, txt in chunks[-6:]:
            out_lines.append(f"### [{kind}]")
            out_lines.append(txt)
            out_lines.append("")
    text = "\n".join(out_lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"✓ спасено в {args.out} ({len(agents)} агентов просмотрено)")
    else:
        print(text)
    return 0


def main():
    p = argparse.ArgumentParser(description="Сторож зависших workflow-прогонов")
    p.add_argument("--session", help="корень субагентских транскриптов (по умолчанию ~/.claude/projects)")
    p.add_argument("--idle", type=float, default=8.0, help="порог тишины в минутах (по умолч. 8)")
    p.add_argument("--list", action="store_true", help="перечислить прогоны и их простой")
    p.add_argument("--check", dest="target_check", metavar="RUNID", help="проверить один прогон на зависание")
    p.add_argument("--salvage", dest="target_salvage", metavar="RUNID", help="вытащить частичный результат из транскриптов")
    p.add_argument("--out", help="файл для --salvage (по умолч. в stdout)")
    args = p.parse_args()

    if args.list:
        return cmd_list(args)
    if args.target_check:
        args.target = args.target_check
        return cmd_check(args)
    if args.target_salvage:
        args.target = args.target_salvage
        return cmd_salvage(args)
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
