# PR-0 architecture note: local X-validation layer

## Scope

PR-0 добавляет локальный bootstrap-слой для ранней проверки токенов через OpenClaw + X.

## Ключевые правила

- OpenClaw/X запускаются **только локально**.
- Codespaces не используется как browser runtime.
- Ручной login в X обязателен для инициализации сессии.

## Degrade strategy

- X-layer не является single point of failure.
- Если X недоступен, pipeline переходит в `degraded` mode.
- Ошибки smoke-проверки фиксируются как артефакты, а не как необработанные исключения.

## Что будет в PR-3

- Top-K validation.
- Cache и TTL-политики.
- Concurrency limits и устойчивый parsing снапшотов.
