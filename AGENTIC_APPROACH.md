# Agentic Approach

## 1. Роль агента

Агент — оркестратор отчётности, не вычислительный движок. Его работа:

1. Прогнать детерминированный пайплайн: данные → метрики → валидация.
2. Пропустить результат через валидационный гейт.
3. Если данные чистые — вызвать LLM, чтобы таблица метрик превратилась в бизнес-нарратив.
4. Если данные битые — выдать warning и не выдавать метрики как достоверные.

Все цифры — из Python-кода. LLM только читает их и пишет прозу.

## 2. Устройство агента

Четыре tool'а в `tools.py`:

- `generate_data(...)` — синтетическая панель, пишет `data/users.csv`.
- `compute_metrics(...)` — агрегация, пишет `reports/metrics.csv`, возвращает markdown-таблицу.
- `run_validation(...)` — hard invariants + soft anomalies.
- `lookup_metric(month, name)` — точечный доступ к значению метрики.

Поток в `agent.py` / `cli.py`:

1. CLI вызывает `generate_data`, `compute_metrics`, `run_validation` последовательно. Чистый код, без ключа, воспроизводимо.
2. Если `validation.passed == False` — отчёт начинается с warning, CLI завершается с кодом 2.
3. Если `passed == True` и нет `--no-llm`, модель OpenAI получает таблицу метрик, инварианты, аномалии. Может вызвать `lookup_metric` до 8 раз (лимит tool-loop).
4. После tool-loop — финальный structured-output call с JSON schema. Модель возвращает объект с 6 секциями и массивом `cited_numbers`.
5. Guardrail: `verify_report_numbers` извлекает все числа из текста отчёта и сверяет с `metrics.csv` + raw data. Несовпадение → exit code 3, отчёт не выпускается.
6. `--no-llm` — `report.py` строит тот же JSON детерминированно, затем рендерит в markdown.
7. На каждый прогон пишется `run_manifest.json` с seed, моделью, хэшами, `system_fingerprint`.

## 3. Где обычные расчёты и почему именно код

- **Генерация (`data_generation.py`)** — симуляция когорты с hazard-кривыми и инъекцией аномалии. Только код гарантирует, что один seed даёт побитово идентичный DataFrame.
- **Метрики (`metrics.py`)** — groupby-агрегации на панели. Churn rate, ARPU, MRR, cohort retention, NRR, revenue churn считаются из raw data, не из внутреннего состояния генератора. Это делает тесты осмысленными: они проверяют, что метрики совпадают с данными, а не что данные совпадают с моделью.
- **Валидация (`validation.py`)** — hard invariants (схема, row count, реконсиляция выручки, монотонность, замыкание оттока) и soft anomalies (MoM-drop выручки, spike churn, spike failed-платежей). Чистая логика; LLM был бы медленнее, дороже и менее надёжен на edge cases.

Pydantic-схемы в `schemas.py` — контракт строки, но основная валидация идёт через pandas на 12000 строках.

## 4. Prompts

### System prompt

```
You are a senior subscription and fintech analyst writing a monthly churn and revenue report.

Hard rules:
- Use ONLY numbers available via the provided metrics table and the lookup_metric tool. Never invent, estimate, average, or extrapolate any figure. If something is not derivable from the data, state that the data does not support it.
- Reference specific months and exact values. Connect churn to revenue causally only where the data supports it.
- Output exactly six markdown sections in order, with the headers provided below.
- No filler, no hedging boilerplate, no emojis. Tight prose.
- If validation reports any hard-invariant failure, open with a data-quality warning and explicitly state the metrics are not trustworthy.

Output structure (exact headers):
1. Executive summary
2. Monthly revenue trend
3. Churn trend
4. ARPU trend
5. Data quality checks
6. Business interpretation
```

### Task prompt

```
Generate the churn and revenue report based on the following data.

Context: 1000 users, 12-month closed cohort, subscription fintech product.

Metrics table:
{metrics_table}

Validation invariants:
{invariants}

Detected anomalies:
{anomalies}

Instructions:
- Write exactly six sections with the headers specified in your system prompt.
- Use the lookup_metric tool if you need exact values for specific months.
- In section 3 (Churn trend), note that month 1 churn rate is N/A because there is no previous month.
- In section 6 (Business interpretation), cover: revenue changes, high/low churn months, causal link between month 8 and month 9 (payment failure spike -> churn spike), anomalies, and 2-3 concrete actionable business takeaways with exact numbers.
- Keep each section concise and specific. Avoid generic advice.
```

### Structured output prompt

После tool-loop агент добавляет:

```
Now generate the final structured report in JSON using the exact schema provided. List every numeric value you used in the cited_numbers array.
```

JSON-schema с `strict: true` и шестью обязательными строковыми полями + `cited_numbers: number[]`.

## 5. Guardrails

1. **LLM не производит числа.** Все цифры — из tools/метрик. Structured output требует `cited_numbers`, который сверяется программно.
2. **Валидационный гейт.** Провал hard-инвариантов блокирует нормальный нарратив. CLI завершается с кодом 2.
3. **Детерминизм ядра.** Фиксированный seed, идентичные артефакты. Покрыто тестом `test_determinism`.
4. **Temperature = 0.** Стабилизирует рассуждения LLM.
5. **Pydantic row schemas.** Типобезопасность на границах generation/metrics/validation.
6. **Guardrail на числа.** `verify_report_numbers` извлекает все числа из текста отчёта (не только self-reported `cited_numbers`) и сверяет с `metrics.csv`. Несовпадение → отчёт блокируется.
7. **Лимит tool-loop.** Max 8 итераций — защита от runaway.
8. **Сеть только к OpenAI API.** Больше внешних вызовов нет.
9. **Fallback `--no-llm`.** Решение работает и проверяется без ключа.

## 6. Почему такой подход

Задание явно просит простоту как сигнал зрелости. Один агент с четырьмя tools — достаточно, потому что проблема чётко определена: данные → метрики → валидация → нарратив. Разбиение на мульти-агентную систему добавило бы coordination overhead без ценности.

LLM хорош в языке и интерпретации, плох в точной арифметике на структурированных таблицах. Закрыв все расчёты в протестированных Python-функциях, мы получаем:

- Воспроизводимость (один seed → один CSV).
- Верифицируемость (pytest покрывает метрики и валидацию).
- Контроль стоимости (нет LLM-токенов на математику; один основной вызов на отчёт).
- Аудируемость (каждая цифра трассируется к pandas groupby).

LLM добавляет ценность только там, где он действительно полезен: превращает таблицу в связный бизнес-рассказ с causal framing'ом — при условии, что guardrails не дают ему врать.

## Hard invariants vs soft anomalies

**Hard invariants** — математические истины, которые должны выполняться для внутренней согласованности данных. Если `active_users` растёт месяц к месяцу, или `amount_paid` отличается от `monthly_price` для paid-строки — данные сломаны. Это не статистические странности, а логические ошибки. Пайплайн трактует их как блокеры.

**Soft anomalies** — статистически необычные, но валидные паттерны. Падение выручки на 25% MoM, churn rate вдвое выше медианы, или failed-payment share 22% — всё это реальные события. Они маркируют возможности для расследования, не баги. Отчёт использует их как narrative anchors (сбой платежей в месяце 8 и всплеск churn в месяце 9), но они никогда не блокируют пайплайн.

Разделение этих уровней показывает, что система понимает разницу между «данные сломаны» и «данные говорят что-то важное».

## Деньги в центах

Все монетарные значения внутри пайплайна — целые числа, центы. `Basic = 999`, `Pro = 1999`, `Premium = 3999`. `amount_paid` либо равен price, либо 0. Revenue суммируется как `int`, реконсиляция — точная, без epsilon-допуска.

Долларовое форматирование происходит только на границе вывода (CSV, отчёт): `/ 100.0` с двумя знаками. Это убирает классический финтех-баг, где `0.1 + 0.2 != 0.3` ломает реконсиляцию.

## Trade-offs и границы скоупа

**Что сознательно не построено:**

- **Мульти-агентность.** Задача просит одного агента, не рой. Добавление planner / executor / critic агентов — over-engineering для 12000 строк.
- **База данных или очередь.** pandas в памяти достаточно. PostgreSQL или Redis добавили бы операционную сложность без выгоды на этом масштабе.
- **Docker как обязательный.** `uv` + `pyproject.toml` уже гарантирует воспроизводимые зависимости. Docker — опционально.
- **CI pipeline.** Не требуется для CLI-утилиты, запускаемой по требованию.
- **Фронтенд или дашборд.** Вне скоупа. Выход — CSV и markdown.

**Что было бы следующим при масштабировании:**

- Batch reporting: цикл по нескольким когортам, переиспользование того же детерминированного ядра.
- Кэширование промптов: system prompt и schema статичны; prompt caching OpenAI снижает стоимость.
- Сегментация hazard по планам: на реальных данных дорогие планы могут уходить чаще. Это разведёт `logo_churn_rate` и `revenue_churn` — и тогда сегментация по планам станет обязательной.
