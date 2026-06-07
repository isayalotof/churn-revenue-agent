# Churn & Revenue Agent

CLI-агент, который генерирует синтетические subscription-данные, считает метрики, валидирует их и выдаёт отчёт. Вся математика — в Python. LLM только читает цифры и пишет прозу.

## Зачем такое устройство

- **Цифры считает код, не модель.** Генерация когорты, агрегация, валидация — детерминированный Python с фиксированным seed. LLM получает готовую таблицу и пишет narrative.
- **Деньги в центах.** `monthly_price`, `amount_paid`, `monthly_revenue` — целые числа (cents). Доллары появляются только на границе вывода (CSV/отчёт), делением на 100. Float-дрейф исключён, реконсиляция выручки — точная, без epsilon.
- **MRR — contract value активных подписок, не collected revenue.** Когда платёж фейлится, подписка остаётся активной, и MRR не падает. Collected revenue падает. Это различие критично для финтеха: сбой биллинга ≠ contraction.
- **Fail-closed.** Если hard-инварианты падают, пайплайн завершается с ненулевым кодом и выдаёт warning-отчёт. Нормальный narrative на битых данных не строится.
- **Воспроизводимость.** Один и тот же seed дают идентичные `users.csv` и `metrics.csv`. Режим `--no-llm` работает без ключа и гарантирует битовую идентичность.

## Assumptions

- **Closed cohort.** 1000 юзеров пришли в месяц 1. Новых привлечений в месяцы 2-12 нет.
- **Без реактивации.** Ушедший в churn не возвращается. `active_users` монотонно не растёт.
- **Полный grid.** 1000 юзеров × 12 месяцев = 12000 строк. После churn `payment_status = "churned"`, `amount_paid = 0`.
- **Active ≠ paid.** Юзер с failed-платежом остаётся active (grace period), но не генерирует revenue. `paid_users ⊂ active_users`.
- **Failed → churn отдельно.** Failed-платёж ≠ churn. Базовый отток — через monthly hazard. Сверху — involuntary churn: 40% юзеров с failed в месяце m уходят в m+1.
- **ARPU на active base.** `ARPU = collected_revenue / active_users`, включая grace-период. Это занижает ARPU в месяцы сбоев — и это корректно.
- **Монетарные поля в центах.** Внутри пайплайна всё — int cents. Доллары только при выводе.
- **Язык отчёта.** English по умолчанию (Executive summary, ARPU, churn — родные термины).
- **Артефакты.** `data/users.csv` и `reports/*` — сгенерированные файлы. Закоммичены для видимости, но код гарантирует идентичную регенерацию из того же seed.

## Установка

Python 3.11+ и `uv`.

```bash
uv sync --extra dev
```

Или через Make:

```bash
make install
```

## Запуск

С LLM (нужен `OPENAI_API_KEY`):

```bash
make report
# или явно
uv run python -m churn_agent run
```

Без LLM — deterministic template, ключ не нужен:

```bash
uv run python -m churn_agent run --no-llm
```

Только генерация данных:

```bash
uv run python -m churn_agent generate
```

Кастомные параметры:

```bash
uv run python -m churn_agent run --seed 123 --n-users 500 --months 6 --no-anomaly --no-llm
```

## Воспроизводимость

Генератор использует `numpy.random.default_rng(seed)`. Один seed → идентичные `users.csv` и `metrics.csv`. Дефолт — 42. Флаг `--seed` задаёт его явно.

LLM-output — best-effort reproducible (`temperature=0`, seed передаётся в OpenAI), но OpenAI не гарантирует битовую идентичность текста. Жёсткую воспроизводимость обеспечивает детерминированное ядро и `--no-llm`.

## Окружение

Скопируй `.env.example` в `.env` и вставь ключ:

```bash
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini
```

`python-dotenv` подхватывает `.env` автоматически при запуске.

## Структура

```
churn-revenue-agent/
├── README.md
├── AGENTIC_APPROACH.md
├── pyproject.toml
├── uv.lock
├── Makefile
├── .env.example
├── .gitignore
├── src/
│   └── churn_agent/
│       ├── __init__.py
│       ├── __main__.py
│       ├── config.py
│       ├── schemas.py
│       ├── data_generation.py
│       ├── metrics.py
│       ├── validation.py
│       ├── tools.py
│       ├── prompts.py
│       ├── agent.py
│       ├── report.py
│       └── cli.py
├── tests/
│   ├── test_data_generation.py
│   ├── test_metrics.py
│   └── test_validation.py
├── data/
│   ├── users.csv
│   └── .generation_meta.json
└── reports/
    ├── metrics.csv
    ├── report.md
    └── run_manifest.json
```

## Тесты

```bash
make test
```

20 тестов, API-ключ не нужен.

## Линт

```bash
make lint
```

## Архитектура

Подробности — в [AGENTIC_APPROACH.md](AGENTIC_APPROACH.md). Там же: trade-offs, почему не мульти-агентность, и честное описание границ скоупа.

## Безопасность и PII

- Секреты только из env. Не в коде, не в логах.
- `.env` в `.gitignore`, в репо — только `.env.example`.
- LLM получает агрегированную таблицу метрик, не row-level данные. На реальных данных — агрегируй или анонимизируй перед отправкой во внешний API.
- `user_id` — синтетический surrogate, без связи с реальными PII.
