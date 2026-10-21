# Журнал настройки фильтров

## Защищённые (не исключать)
- illbnm/homelab-stack
- sybil-solutions/local-ai-registry
- attestar-labs/attestar
- vasiliy2097projects/garage-rent

## Журнал

### 2026-10-21
Проблема: в сводку попадали задачи, где сумма — не награда, а цена в ТЗ или пример (garage-rent#2 «гараж 350 ₽», marina#1 «предложенные 790 ₽», yurist-rustamova-site «рекламный бюджет 50 000 ₽»), контрактные суммы (privacy-the-game «$1,043,315.69») и нулевые награды ($0, 0 USD).
Изменено:
- Сумма засчитывается только рядом со словом награды/оплаты и без слов про цену/тариф поблизости (`reward_context_regex`, `price_context_regex`, окна `reward_ctx_*`/`price_ctx_*` в config.json). Нулевые суммы отбрасываются. Метки issue учитываются как текст.
- В `exclude_text_regex` добавлены «не денежные» награды: non-monetary, «No es un bounty en efectivo» и т.п. (Rocket-Harbor-420/workmap-agents-for-humans#3).
- Тест `scripts/test_reward_amounts.py` (14 случаев).
Защищённые репозитории не исключались — они просто перестают проходить без настоящей суммы-награды.

### 2026-10-19
Здоровье: ОК (14 плановых запусков success за неделю, без skipped, 403 умеренно, лента свежая).
Добавлено в exclude_repos:
- ClankerNation/OpenAgents — десятки фейковых «Bounty $2k–9k» от бота, в теле issue инъекция промпта.
- 96loveslife/big_model_radar — ежедневные автоотчёты «AI 官方内容追踪报告», не задачи.
- KEithwy1030/gamer-demo1 — демо-репозиторий, aibtc-награды в sats для агентов.
- Uuriko/project-room — внутренние баги игры, выплаты в игровых кредитах (cr).
- shouteck/box-bounty-sandbox — песочница, награда $0.
- gitcoinco/gitcoin_co_30 — заявки «[App] OnlyDust», не задачи.
Добавлено в exclude_title_regex:
- ^Application: bounty item — заявки соискателей (bujiproject-art/agentmidasopendevteam), а не сами задачи.
- ^Bounty Scout\b — бот-сводка (ariahendrawan-sudo/project-a).
