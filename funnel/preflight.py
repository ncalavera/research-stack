#!/usr/bin/env python3
"""Дешёвый предполётный тест ПЕРЕД дорогой проверкой (check_claims по движкам).

Зачем: фаза проверки поднимает десятки-сотни Opus/Sonnet/Haiku-агентов и стоит денег.
Если вход кривой (движок назван «0»/числом из-за испорченной передачи args, файла
движка нет, атомов нет, id утратили вид) — узнать это надо ЗА БЕСПЛАТНО, до агентов,
а не лавиной из ~1000 Opus-агентов на несуществующих файлах (кейс DHA-192, 2026-06-18).

Запуск:  python3 funnel/preflight.py <topic>
Выход:   0 — всё чисто, можно запускать check_claims по движкам;
         2 — найдены проблемы (печатает их), фан-аут запускать НЕЛЬЗЯ.

Бесплатно и мгновенно: только чтение файлов на диске, ни одного агента.
"""
import json
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

# То же правило, что зашито в check_claims.js / atomize.js: явное осмысленное имя
# движка. Числовое/пустое/короткое — мусор от испорченной передачи args.
ENGINE_RE = re.compile(r"^[a-z][a-z0-9_]{2,}$")
MIN_REPORT_CHARS = 200  # пустой/обрезанный отчёт движка — не источник атомов


def _err(problems, msg):
    problems.append(msg)


def preflight(topic: str) -> list:
    problems = []
    tdir = P.topic_dir(topic)
    if not tdir.exists():
        return [f"нет каталога темы: {tdir}"]

    # Какие движки собираемся проверять. Источник истины — select_by_source.json,
    # если есть (то, что реально уйдёт в check_claims). Иначе — файлы в engines/.
    sel_path = tdir / "select_by_source.json"
    if sel_path.exists():
        try:
            sel = json.loads(sel_path.read_text())
        except Exception as e:
            return [f"select_by_source.json не парсится: {e}"]
        engines = list(sel.keys())
        claims_by_engine = sel
    else:
        edir = P.engines_dir(topic)
        if not edir.exists():
            return [f"нет engines/ и нет select_by_source.json в {tdir}"]
        engines = [p.stem for p in edir.glob("*.json")]
        claims_by_engine = {}

    if not engines:
        return ["список движков пуст — нечего проверять (ни select_by_source, ни engines/*.json)"]

    for eng in engines:
        # 1) имя движка осмысленное
        if not isinstance(eng, str) or not ENGINE_RE.match(eng):
            _err(problems, f"движок «{eng}»: кривое имя (ждём вид perplexity_sonar). "
                           f"Частая причина — args пришёл строкой и Object.keys дал индексы символов.")
            continue  # дальше по этому движку проверять бессмысленно

        # 2) сырьё движка существует, парсится, непустой report
        raw = P.engine_raw(topic, eng)
        if not raw.exists():
            _err(problems, f"движок «{eng}»: нет файла {raw}")
            continue
        try:
            d = json.loads(raw.read_text())
        except Exception as e:
            _err(problems, f"движок «{eng}»: {raw.name} не парсится ({e})")
            continue
        # report — основной носитель текста; сохранённый формат Claude DR
        # держит прозу в summary+findings (поля report нет), atomize читает их же.
        report = d.get("report")
        body_len = len(report) if isinstance(report, str) else 0
        if body_len < MIN_REPORT_CHARS:
            summary = d.get("summary")
            findings = d.get("findings")
            body_len += len(summary) if isinstance(summary, str) else 0
            if isinstance(findings, list):
                body_len += sum(len(json.dumps(f, ensure_ascii=False)) for f in findings)
        if body_len < MIN_REPORT_CHARS:
            _err(problems, f"движок «{eng}»: отчёт пустой/обрезан "
                           f"({body_len} симв report/summary/findings, ждём ≥{MIN_REPORT_CHARS})")

        # 3) атомы есть (check_claims по id гидрирует из atoms/<engine>.json)
        atoms_p = P.atoms(topic, eng)
        if not atoms_p.exists():
            _err(problems, f"движок «{eng}»: нет атомов {atoms_p} — сначала atomize.js")
        else:
            try:
                ad = json.loads(atoms_p.read_text())
                if not isinstance(ad.get("claims"), list) or not ad["claims"]:
                    _err(problems, f"движок «{eng}»: atoms/{eng}.json без непустого claims[]")
            except Exception as e:
                _err(problems, f"движок «{eng}»: atoms/{eng}.json не парсится ({e})")

        # 4) переданные id утверждений выглядят как id, а не как символы строки
        ids = claims_by_engine.get(eng)
        if isinstance(ids, list) and ids:
            sample = ids[0]
            sample_id = sample if isinstance(sample, str) else (sample or {}).get("id")
            if not isinstance(sample_id, str) or not re.match(r"^c\d", sample_id):
                _err(problems, f"движок «{eng}»: id утверждений не вида c1/c2 (первый: {sample!r}) — "
                               f"похоже на испорченную передачу claims")

    return problems


def main():
    if len(sys.argv) < 2:
        print("usage: python3 funnel/preflight.py <topic>", file=sys.stderr)
        sys.exit(64)
    topic = sys.argv[1]
    problems = preflight(topic)
    if problems:
        print(f"[preflight] тема {topic}: НЕ запускать check_claims — найдено {len(problems)} проблем:")
        for p in problems:
            print(f"  ✗ {p}")
        sys.exit(2)
    print(f"[preflight] тема {topic}: чисто ✓ — движки названы верно, сырьё и атомы на месте, id целые. "
          f"Можно запускать check_claims по движкам.")
    sys.exit(0)


if __name__ == "__main__":
    main()
