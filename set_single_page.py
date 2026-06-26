#!/usr/bin/env python3
"""set_single_page.py — прописать /PageLayout /SinglePage в каталог PDF.

Chrome print-to-pdf не задаёт PageLayout, поэтому macOS Preview открывает отчёт
разворотом по две страницы. Этот шаг через qpdf разворачивает PDF в текстовый QDF,
вставляет /PageLayout /SinglePage в объект-каталог и собирает обратно — Preview
открывает по одной странице.

ВАЖНО: всё чтение/запись QDF — в БИНАРНОМ режиме. Текстовый режим транслирует
переносы строк и рушит бинарные потоки встроенных шрифтов (симптом — выпадают
буквы u/v: «Justia» → «J stia»). Поэтому только bytes, без перекодировок.

Запуск: python3 set_single_page.py reports/REPORT-...-paged.pdf
Идемпотентно: если PageLayout уже есть, не дублирует.
"""
import os
import re
import subprocess
import sys


def main():
    pdf = sys.argv[1] if len(sys.argv) > 1 else None
    if not pdf or not os.path.exists(pdf):
        print(f"нет файла: {pdf}", file=sys.stderr)
        return 2
    qdf = pdf + ".qdf"

    # qpdf код 3 = предупреждения при валидном выводе (Chrome-PDF их часто даёт) — не ошибка
    def qpdf(args):
        r = subprocess.run(["qpdf", *args])
        if r.returncode not in (0, 3):
            raise subprocess.CalledProcessError(r.returncode, ["qpdf", *args])

    # 1) развернуть в редактируемый QDF (несжатые объекты)
    qpdf(["--qdf", "--object-streams=disable", pdf, qdf])

    data = open(qdf, "rb").read()                       # БИНАРНО — не трогаем потоки шрифтов
    if b"/PageLayout" in data:
        os.remove(qdf)
        print("PageLayout уже задан — пропуск")
        return 0
    # 2) номер объекта-каталога — из /Root трейлера
    rootm = re.search(rb"/Root\s+(\d+)\s+0\s+R", data)
    if not rootm:
        os.remove(qdf)
        print("/Root не найден в трейлере", file=sys.stderr)
        return 1
    root_n = rootm.group(1)
    # тело объекта-каталога: «N 0 obj << ... >> endobj» — вставляем перед его >> endobj
    objm = re.search(rb"(\n" + root_n + rb"\s+0\s+obj\b.*?)(>>\s*\nendobj)", data, re.DOTALL)
    if not objm:
        os.remove(qdf)
        print(f"объект-каталог {root_n.decode()} не найден", file=sys.stderr)
        return 1
    data = data[:objm.start()] + objm.group(1) + b"  /PageLayout /SinglePage\n" + objm.group(2) + data[objm.end():]
    open(qdf, "wb").write(data)                          # БИНАРНО

    # 3) собрать обратно нормальный PDF поверх исходного
    qpdf([qdf, pdf])
    os.remove(qdf)
    print(f"✓ /PageLayout /SinglePage прописан → {pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
