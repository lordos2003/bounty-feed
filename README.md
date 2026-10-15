# bounty-feed

Репозиторий ежедневно (через GitHub Actions, два раза в сутки) ищет открытые GitHub issues с вознаграждением (bounty), отфильтровывает занятые и спамовые, оценивает их и сохраняет результат в файлы.

## Результаты

- `results/latest.json` — полный список с оценкой (`score`), суммами, PR, заявками; поля `generated_at`, `count`, `new_today`.
- `results/latest.md` — таблица топ-150 задач со ссылками.
- `results/seen.json` — служебный файл: когда каждая задача была замечена впервые.

Прямая ссылка на JSON: https://raw.githubusercontent.com/lordos2003/bounty-feed/main/results/latest.json

## Как это работает

- Workflow: `.github/workflows/bounty-search.yml` (cron `17 2 * * *` и `17 14 * * *` UTC, а также ручной запуск через `workflow_dispatch`).
- Скрипт: `scripts/search.py` (только стандартная библиотека Python).
- Запросы и фильтры (исключаемые владельцы, репозитории, заголовки): `scripts/config.json`.
- Порядок запросов в `queries` — это приоритет: узкие (RU, Python/JS/TS, 💎 Bounty) идут первыми, шумные широкие — в конце и по 1 странице (`{"q": ..., "pages": 1}`). Если бюджет поиска (`search_budget_min`) кончается, в логе перечисляются пропущенные запросы.
- Обогащение (PR, claims, комментарии) идёт в порядке дешёвой предварительной оценки `pre_score`, лимит `max_enrich`.
- Поле `testnet_hint`: в issue или комментариях есть признаки тестовой сети (`testnet_regex`: testnet, signet, sepolia, «test coins», «no real money»…) — такие награды ничего не стоят, score снижается на 8.
