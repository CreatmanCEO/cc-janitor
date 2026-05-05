# cc-janitor

Наводит порядок в окружении Claude Code — сессии, права, контекст, хуки.

Первый единый TUI/CLI-инструмент, объединяющий очистку сессий, прополку
прав доступа, инспекцию CLAUDE.md/памяти, отладку хуков (Phase 2) и
плановое обслуживание (Phase 2) — все рутинные операции, которые никто
больше не автоматизирует, собраны в одном месте.

**Языки:** English / Русский (переключение F2 в TUI, `--lang ru` в CLI)

## Стек

- **Язык:** Python 3.11+
- **TUI:** [Textual](https://textual.textualize.io/) (терминальный UI-фреймворк)
- **CLI:** [Typer](https://typer.tiangolo.com/)
- **Оценка токенов:** OpenAI `tiktoken` (cl100k_base, погрешность ~5% для Claude)
- **Тесты:** pytest + pytest-asyncio + pytest-textual-snapshot
- **Дистрибуция:** PyPI через `uv tool` / `pipx`

## Возможности (Phase 1 MVP)

### Сессии
- Список, поиск и предпросмотр сессий Claude Code в `~/.claude/projects/`
- Мягкое удаление в восстановимую корзину; возврат через `cc-janitor trash restore`
- Просмотр compact-summaries и собственных markdown-сводок индексатора

### Права доступа
- Обнаружение правил во всех 5 слоях settings.json + `~/.claude.json` approvedTools
- Маркировка устаревших правил (без совпадений за 90 дней) по транскриптам
- Дедупликация (subsumed/exact) и прополка (stale) — с бэкапами перед записью

### Инспектор контекста
- Обход иерархии CLAUDE.md, список memory-файлов, список включённых скиллов
- Расчёт стоимости в байтах/токенах по каждому файлу + суммарно на запрос
- Оценка $ по входной ставке Opus

## Установка

> ⚠️ **v0.1.x ещё не опубликована на PyPI.** Пока устанавливайте из исходников:

```bash
# Рекомендуется — uv tool из исходников
uv tool install git+https://github.com/CreatmanCEO/cc-janitor

# Или pipx из исходников
pipx install git+https://github.com/CreatmanCEO/cc-janitor

# Из локального клона для разработки
git clone https://github.com/CreatmanCEO/cc-janitor && cd cc-janitor
uv sync --all-extras
uv run cc-janitor
```

Публикация на PyPI появится после настройки Trusted Publisher на pypi.org. Отслеживайте в [issue #1](https://github.com/CreatmanCEO/cc-janitor/issues), когда он будет создан.

## Быстрый старт

```bash
# Запуск TUI
cc-janitor

# CLI: список сессий
cc-janitor session list

# Аудит правил доступа
cc-janitor perms audit

# Стоимость контекста на каждый запрос
cc-janitor context cost

# Изменяющие команды требуют явного подтверждения:
CC_JANITOR_USER_CONFIRMED=1 cc-janitor session prune --older-than 90d
```

## Безопасность

cc-janitor никогда не уничтожает данные молча:

- **Шлюз `CC_JANITOR_USER_CONFIRMED=1`:** каждая изменяющая команда отказывается запускаться без этой переменной. Read-only команды (list, show, audit, cost) свободны от ограничений.
- **Мягкое удаление:** удалённые сессии переезжают в `~/.cc-janitor/.trash/<timestamp>/` на 30 дней. Восстановление: `cc-janitor trash restore <id>`.
- **Бэкап перед записью:** каждое изменение settings.json создаёт timestamped-бэкап в `~/.cc-janitor/backups/<sha-of-path>/`.
- **Журнал аудита:** каждое мутирующее действие пишется JSONL-записью в `~/.cc-janitor/audit.log` (ротация при 10 МБ).

> **Пользователям Windows:** `cc-janitor install-hooks` записывает POSIX-shell сниппет (`test -f`, `&&`). На нативной Windows без Git Bash / WSL хук будет молча падать. Кроссплатформенная поддержка PowerShell появится в 0.2.0 (Phase 2). Пока используйте Git Bash или WSL.

## Использование изнутри Claude Code

cc-janitor задуман так, чтобы его вызывали и пользователь (TUI / CLI), и сам Claude Code (CLI), но только по явному запросу. См. [docs/CC_USAGE.md](docs/CC_USAGE.md) — справку, которую Claude Code читает, чтобы решить, безопасно ли вызывать конкретный subcommand.

## Дорожная карта

- [x] **Phase 1** (текущий релиз): сессии / права / инспектор контекста / CLI / TUI / примитивы безопасности
- [ ] **Phase 2**: редактор памяти, reinject-хук, отладчик хуков с симуляцией, планировщик (cron / Task Scheduler)
- [ ] **Phase 3**: вложенные `.claude/` в монорепо, авто-reinject watcher, дашборд статистики, экспорт/импорт конфига

## Контрибьюторам

Issues и PR приветствуются. См. [docs/architecture.md](docs/architecture.md) — обзор кодовой базы.

## Лицензия

MIT — см. [LICENSE](LICENSE).
