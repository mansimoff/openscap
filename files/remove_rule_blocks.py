#!/usr/bin/env python3
"""
remove_rule_blocks.py — вырезает из bash-remediation-скрипта OpenSCAP
(генерируется командой `oscap xccdf generate fix --fix-type bash`) блоки
отдельных правил по их XCCDF Rule ID.

Формат блока в исходном скрипте:

    ###############################################################################
    # BEGIN fix (N / TOTAL) for 'xccdf_org.ssgproject.content_rule_XXX'
    ###############################################################################
    (>&2 echo "..."); (
        ...
    ) # END fix for 'xccdf_org.ssgproject.content_rule_XXX'

Скрипт вырезает такой блок целиком (включая обрамляющие строки-разделители
из решёток) для каждого указанного через --exclude Rule ID.
"""
import argparse
import re
import sys

BLOCK_RE_TEMPLATE = (
    r"###+\n"
    r"# BEGIN fix \(\d+ / \d+\) for '{rule_id}'\n"
    r"###+\n"
    r".*?"
    r"\) # END fix for '{rule_id}'\n?"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="исходный fix-скрипт (fixes_only_failed.sh)")
    parser.add_argument("output", help="куда записать очищенный скрипт")
    parser.add_argument(
        "--exclude",
        nargs="+",
        required=True,
        metavar="RULE_ID",
        help="один или несколько Rule ID, чьи блоки нужно вырезать",
    )
    parser.add_argument(
        "--log",
        required=True,
        metavar="PATH",
        help="файл, куда пишется отчёт о том, что было вырезано / не найдено",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        content = f.read()

    original_lines = content.count("\n")
    removed: list[str] = []
    not_found: list[str] = []

    for rule_id in args.exclude:
        pattern = re.compile(
            BLOCK_RE_TEMPLATE.format(rule_id=re.escape(rule_id)),
            re.DOTALL,
        )
        new_content, count = pattern.subn("", content)
        if count > 0:
            content = new_content
            removed.append(rule_id)
        else:
            # Правило не найдено в скрипте — это не ошибка: значит, при
            # сканировании оно либо не провалилось (уже compliant), либо
            # неприменимо на этой версии ОС/профиле. Просто фиксируем факт.
            not_found.append(rule_id)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(content)

    new_lines = content.count("\n")

    with open(args.log, "w", encoding="utf-8") as f:
        f.write(f"Исходный скрипт: {original_lines} строк\n")
        f.write(f"Очищенный скрипт: {new_lines} строк\n\n")
        f.write("Вырезаны блоки правил (найдены и удалены):\n")
        for r in removed:
            f.write(f"  - {r}\n")
        if not removed:
            f.write("  (ничего не вырезано)\n")
        f.write(
            "\nНе найдены в скрипте (правило не проваливалось при "
            "сканировании либо неприменимо на этой системе):\n"
        )
        for r in not_found:
            f.write(f"  - {r}\n")
        if not not_found:
            f.write("  (все правила из списка исключений были найдены)\n")

    print(f"removed={len(removed)} not_found={len(not_found)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
