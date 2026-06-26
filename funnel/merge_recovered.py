#!/usr/bin/env python3
"""DHA-127: влить восстановленные ре-поиском факты в пул отчёта.

Вход: judge_claims/pool/topic{N}_resourced.json (результат resource.js).
Действие: каждый факт с found=true и классом A/B превращаем в запись пула
(judge_claims/pool/topic{N}.json) и дописываем, помечая note «восстановлено DHA-127».
Секцию определяем по ключевым словам. Дубли по тексту не добавляем.
"""
import json
import sys
import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent  # корень репозитория (скрипт в funnel/)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths as P

SECTION_RULES = [
    (r"whoop|hrv|recovery|sleep need|полисомнограф|каппа|трекер|эффективн\w* сна|консистентн", "Whoop и метрики"),
    (r"сон|сна|swс|sws|rem|циркадн|мелатонин|кофеин|экран|спальн|ритуал|бессонниц|cbt", "Сон"),
    (r"дефицит|похуд|потер\w* вес|tdee|калори|mifflin|темп", "Дефицит и темп похудения"),
    (r"белк|белок|жир|углевод|макронутриент|г/кг|порци|приём пищи|питани", "Питание и белок"),
    (r"тренировк|подход|повторен|1пм|гипертроф|кардио|hiit|аэробн|силов|full-body|объём", "Тренировки"),
    (r"рекомпозиц|мышечн\w* масс|ffm|состав тела|жиров\w* масс|процент жир", "Состав тела и рекомпозиция"),
]


def section_of(text):
    low = text.lower()
    for pat, sec in SECTION_RULES:
        if re.search(pat, low):
            return sec
    return "Прочее"


def merge(topic):
    pool = json.load(open(P.pool(topic)))
    res = json.load(open(P.pool_resourced(topic)))

    existing = {f["text"].strip()[:60] for f in pool["facts"]}
    added = 0
    for r in res["results"]:
        if not (r.get("found") and r.get("source") and r.get("source_class") in ("A", "B")):
            continue
        text = r["fact"].strip()  # полная исходная формулировка, не обрывок corrected_value
        if text[:60] in existing:
            continue
        existing.add(text[:60])
        corrected = (r.get("corrected_value") or "").strip()
        note = "восстановлено ре-поиском (DHA-127)"
        if corrected:
            note += f"; уточнение по источнику: {corrected}"
        if r.get("note"):
            note += f"; {r['note']}"
        pool["facts"].append({
            "text": text,
            "section": section_of(text),  # секция по сути факта, а не по числу-уточнению
            "provenance": [{
                "engine": "re-search",
                "source": r["source"],
                "class": r["source_class"],
                "label": "PARTIAL" if corrected else "SUPPORTED",
                "quote": r.get("quote"),
            }],
            "best_source": r["source"],
            "best_class": r["source_class"],
            "engines_count": 1,
            "confidence": r.get("confidence", "medium"),
            "needs_review": bool(corrected) or r.get("confidence") != "high",
            "corrected_value": corrected or None,
            "note": note,
        })
        added += 1

    json.dump(pool, open(P.pool(topic), "w"),
              ensure_ascii=False, indent=2)
    print(f"влито в пул: +{added} (всего фактов {len(pool['facts'])})")


if __name__ == "__main__":
    merge(sys.argv[1] if len(sys.argv) > 1 else "topic1")
