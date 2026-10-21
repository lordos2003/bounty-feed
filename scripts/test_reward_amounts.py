"""Проверка, что суммы засчитываются как награда только в контексте награды.
Запуск: python scripts/test_reward_amounts.py (без сети и токена)."""
import os
import sys

os.environ.setdefault("GH_TOKEN", "test")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import search  # noqa: E402

CASES = [
    # (описание, текст, ожидаемые суммы-награды)
    ("garage-rent#2: цена гаража в приёмке, не награда",
     "labels: P0 | ui\nСверстать экран поиска на моках\n## Что должно получиться\nЧеловек открывает "
     "приложение и видит поиск: рисунок карты, метки с ценой за час, список карточек.\n## Приёмка\n"
     "- После `delay(800ms)` видны метки и список. В списке есть «Теплый гараж с ямой» и 350 ₽.",
     []),
    ("marina#1: пример цены продукта в плане",
     "Платный продукт публикуется после настройки тарифа. Исходные диапазоны цен и предложенные 790 ₽ "
     "служили примерами. Они не становятся начальными production-тарифами.",
     []),
    ("marina#1: число в задаче E03 без контекста",
     "GREEN/приёмка: контрольные семейные примеры утверждены; сумма равна сумме строк; "
     "нет скрытого фиксированного курса или числа 790.",
     []),
    ("useagent#113: сумма в метке и в разделе Payment",
     "labels: hacktoberfest | bounty: $5\nCoding with an agent\n## Payment\n- $5 per task, to the first person",
     ["$5"]),
    ("homelab-stack#14: [BOUNTY $280] в заголовке",
     "[BOUNTY $200] Testing\n## 赏金金额\n**$280 USDT** (或等值法币)",
     ["$200", "$280"]),
    ("sybil#223: Pays $50",
     "labels: bounty | bounty: $50\n**Pays $50** when a PR adds a tested recipe",
     ["$50"]),
    ("нулевая награда",
     "labels: good first issue | bounty\nReward: 0 USD for this one",
     []),
    ("бюджет рекламы, а не оплата работы",
     "Получать больше обращений. Не увеличивать бюджет ради просмотров. Рекламный бюджет в месяц 50 000 ₽.",
     []),
    ("RU-заказ с явной оплатой",
     "Нужно доработать парсер.\nОплата: 3 000 ₽ после приёмки.",
     ["3 000 ₽"]),
    ("RU-заказ с бюджетом задачи",
     "Сделать скрипт выгрузки.\nБюджет: 5000 ₽",
     ["5000 ₽"]),
    ("Algora-бот",
     "💎 $20 bounty created by cal",
     ["$20"]),
    ("цена подписки рядом со словом bounty",
     "Bounty for the pricing page: show the plan price $9.99 per month and the $99 yearly price",
     []),
    ("награда рядом, а цена API далеко",
     "Our tool is priced per call at 0.001 USDC.\n\n" + "x" * 120 + "\nBounty: 50 USDC for the fix",
     ["50 USDC"]),
]


def main():
    failed = 0
    for name, text, expected in CASES:
        got, other = search.reward_amounts(text)
        ok = sorted(got) == sorted(expected)
        failed += not ok
        print(f"{'OK  ' if ok else 'FAIL'} {name}: got={got} other={other}"
              + ("" if ok else f" expected={expected}"))
    # отсев «не денежных» наград через exclude_text_regex
    item = {"repository_url": "https://api.github.com/repos/a/b", "title": "Pool",
            "body": "Recompensa comunitaria: hasta 30 Harbor Points no monetarios. "
                    "No es un bounty en efectivo. 1,938 sats", "labels": []}
    ok = search.exclusion_reason(item) == "text"
    failed += not ok
    print(f"{'OK  ' if ok else 'FAIL'} не денежная награда исключается: {search.exclusion_reason(item)}")
    print(f"\n{len(CASES) + 1 - failed}/{len(CASES) + 1} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
