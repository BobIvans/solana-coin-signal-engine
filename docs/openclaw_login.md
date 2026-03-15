# OpenClaw + X manual login (PR-0)

## Где запускать

- Запускайте OpenClaw **только на локальной машине**.
- Не используйте Codespaces как browser runtime для X.

## Шаги

1. Подготовьте окружение:
   ```bash
   python scripts/print_env_check.py
   python scripts/setup_openclaw.py
   ```
2. Откройте браузер через OpenClaw с профилем `OPENCLAW_PROFILE_PATH`.
3. Вручную залогиньтесь в X (twitter.com/x.com).
4. Закройте браузер без очистки профиля.
5. Запустите smoke-проверку:
   ```bash
   python scripts/smoke_openclaw_x.py
   ```

## Проверка, что сессия жива

- Smoke-скрипт должен вернуть `status = ok` или `status = degraded`.
- Файл `data/smoke/x_snapshot_example.json` должен быть создан всегда.

## CAPTCHA / soft-ban

- Если X вернул CAPTCHA или сессия недействительна, это не fatal.
- PR-0 обязан перейти в `degraded` режим без hard-crash.
- Повторите ручной вход в том же профиле и перезапустите smoke-тест.
