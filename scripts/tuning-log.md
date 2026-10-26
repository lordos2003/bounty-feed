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

### 2026-10-22
Здоровье: ОК (14 плановых запусков success, без skipped, 403 — 14 строк secondary limit, запуск 1854 с при дедлайне 42 мин, лента свежая; not enriched: limit 148 — упирается в max_enrich=700, не менял).
Добавлено в exclude_title_regex:
- `^\[(?:find opt-out|opt-out check)\]` — lizTheDeveloper/privacy-the-game: 78 однотипных issue «[find opt-out] <брокер>» / «[opt-out check] ...», массово заведены владельцем 19.10, без суммы награды, занимали 72 из топ-100.
- `^\[(?:new research|stronger source)\]` — тот же репозиторий, те же шаблонные исследовательские задачи (метка bounty: medium, суммы нет; «$300» в #333 — цитата из текста).
Репозиторий целиком не исключён: остальные его issue (если появятся с реальной суммой) пройдут.

### 2026-10-26
Здоровье: ОК (16 запусков success за 8 суток, без skipped и not enriched, 403 — 13 строк secondary limit, лента свежая; утренний запуск 26.10 ещё не прошёл на момент проверки).
Добавлено в exclude_repos:
- alfrexo95/bounty-bot — бот переписывает чужие bounty в свои issue «Bounty Seguro» (4 строки топа, вложенные дубли).
- up2itnow0822/ClawPowers-Skills — ежедневные автоотчёты «Daily Review».
- Nish916/revenue-command-runner — бот-дашборд, сумма $1,000,000 из служебного текста.
- immanueltella-web/quantum-media-os. — бот-копия «Bounty Alert» с чужого сканера.
Добавлено в exclude_owners:
- doomsday-network — 7 строк топа: награды в токене DOOM/wDOOM, «Star repos», обмен на Steam-карту; не деньги.
Добавлено в exclude_title_regex:
- `^Daily Review\b` — шаблон автоотчётов.
Реплей: убирает 29 записей, защищённых и OWNER/MEMBER живых проектов среди них нет (WebFetch был недоступен, решение по телам issue из ленты).
Не тронуто (не проверено): SPLURT-Station/S.P.L.U.R.T-tg (игровые suggestion-issue с меткой bounty), NEXAITECHAU/algora-demo-1.
