# cc-janitor

Наводит порядок в окружении Claude Code — сессии, права, контекст, хуки,
расписание, Auto Dream.

Единый TUI/CLI: чистка сессий, прополка прав, инспекция CLAUDE.md и
memory-файлов, отладчик хуков, планировщик задач, сеть страховки для
Auto Dream — всё, что больше никто не автоматизирует, в одном инструменте.

**Языки:** English / Русский (F2 в TUI, `--lang ru` в CLI)

## Стек

- **Язык:** Python 3.11+
- **TUI:** [Textual](https://textual.textualize.io/)
- **CLI:** [Typer](https://typer.tiangolo.com/)
- **Оценка токенов:** OpenAI `tiktoken` (cl100k_base, погрешность ~5% для Claude)
- **Тесты:** pytest + pytest-asyncio + pytest-textual-snapshot
- **Дистрибуция:** PyPI через `uv tool` / `pipx`

## Возможности

### Сессии
- Список, поиск и предпросмотр сессий из `~/.claude/projects/`
- Мягкое удаление в `~/.cc-janitor/.trash/`; возврат через `cc-janitor trash restore`
- Просмотр compact-summaries и markdown-сводок индексатора

### Права
- Обнаружение правил во всех 5 слоях settings.json + `~/.claude.json` approvedTools
- Маркировка устаревших (без совпадений за 90 дней) по реальным транскриптам
- Дедупликация и прополка — с бэкапом перед каждой записью

### Контекст
- Обход иерархии CLAUDE.md, список memory, список включённых скиллов
- Стоимость в байтах/токенах + суммарно на запрос, оценка $ по Opus

### Память (Phase 2)
- Парсинг frontmatter, классификация типа (user/feedback/project/reference)
- Поиск кросс-файловых дублей, архив, смена типа, открытие в `$EDITOR`
- TUI-таб с превью; reinject-маркер для следующего вызова инструмента

### Хуки (Phase 2)
- Discovery во всех слоях, валидация схемы, симуляция с реалистичным stdin
- Обратимый logging-wrapper; toggle из TUI идёт через ConfirmModal

### Планировщик (Phase 2)
- Cron / schtasks через единый `Scheduler` ABC
- 6 шаблонов: perms-prune, trash-cleanup, session-prune, context-audit,
  backup-rotate, dream-tar-compact
- Первый прогон после `add` — всегда `--dry-run`; `promote` переводит в live

### Монорепо + watcher + stats (Phase 3)
- Обход `.claude/` под произвольным корнем, классификация real/nested/junk
- Фоновый watcher для авто-reinject (опт-ин, `psutil` экстра)
- Дашборд с историей: `cc-janitor stats [--since 30d]`, ASCII-sparklines в TUI
- Экспорт/импорт конфиг-бандла с SHA-256 манифестом

### Сеть страховки Auto Dream (Phase 4)
- Снимок memory-каталога до каждого цикла Auto Dream, диф после, откат при
  необходимости. Закрывает upstream-issues #47959, #50694, #38493, #38461.
- `dream history` / `dream diff` / `dream doctor` (10 проверок) / `dream
  rollback --apply`
- Tar-сжатие старых пар (`backups tar-compact`); диф и откат на tar-парах
  работают прозрачно через временное извлечение.
- `stats sleep-hygiene` — размер MEMORY.md, плотность относительных дат,
  кросс-файловые дубли, противоречия в feedback-памяти
- Откат `dream rollback` обратим через `cc-janitor undo`

## Установка

```bash
# Из PyPI (рекомендуется)
uv tool install cc-janitor
# или
pipx install cc-janitor

# Опциональный watcher-экстра (фоновый dream-snapshot демон)
uv tool install "cc-janitor[watcher]"

# Из исходников для разработки
git clone https://github.com/CreatmanCEO/cc-janitor && cd cc-janitor
uv sync --all-extras
uv run cc-janitor
```

## Быстрый старт

```bash
# TUI
cc-janitor

# Список сессий
cc-janitor session list

# Аудит правил доступа
cc-janitor perms audit

# Стоимость контекста на запрос
cc-janitor context cost

# Сеть страховки Auto Dream
CC_JANITOR_USER_CONFIRMED=1 cc-janitor watch start --dream
cc-janitor dream history
cc-janitor dream doctor

# Скаффолд пользовательского конфига
cc-janitor config init
```

Изменяющие команды требуют `CC_JANITOR_USER_CONFIRMED=1`. Read-only
команды (list, show, audit, cost, history, diff, doctor) — без ограничений.

## Безопасность

- **Шлюз `CC_JANITOR_USER_CONFIRMED=1`** на каждой мутирующей команде.
- **Мягкое удаление** в `~/.cc-janitor/.trash/<timestamp>/` на 30 дней.
- **Бэкап перед записью** settings.json в `~/.cc-janitor/backups/<sha>/`.
- **Журнал аудита** JSONL в `~/.cc-janitor/audit.log` (ротация при 10 МБ).
- **`cc-janitor undo`** разворачивает последнюю обратимую операцию из
  журнала — session delete, perms remove/prune/dedupe, memory archive,
  dream rollback.

## Дорожная карта

- [x] **Phase 1** — сессии / права / контекст / CLI / TUI / примитивы безопасности
- [x] **Phase 2** — память, reinject, отладчик хуков, планировщик
- [x] **Phase 3** — монорепо, watcher, stats, экспорт/импорт конфига
- [x] **Phase 4** — Auto Dream safety net, sleep-hygiene, settings audit hook
- [ ] **Phase 5** — кроссплатформенные fix-up для хуков, `dream fix-stale-lock`, мутирующие действия в Dream-табе

## Контрибьюторам

Issues и PR приветствуются. См. [docs/architecture.md](docs/architecture.md).

## Лицензия

MIT — см. [LICENSE](LICENSE).
