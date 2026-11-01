# AITemplate 2

Переносимые правила Codex/Claude, документация и Second Brain с исполняемыми проверками.
Корневой `AGENTS.md` содержит основные ограничения и маршрут к контексту; подробные правила загружаются по задаче.
Факты, знания и команды конкретного проекта заполняются отдельно.

## Установка и обновление

Из этого чистого шаблона, в существующий каталог другого проекта:

```powershell
python Scripts/install_template.py "D:\Projects\NewProject" --dry-run
python Scripts/install_template.py "D:\Projects\NewProject"
```

Установщик переносит перечисленные в `template.json` файлы, включая `Scripts/agent.py`, `.agent/`, `.agents/skills`, `.claude/` и `.obsidian/`.
Корневые README, `.gitignore`, исходный manifest и команды выпуска шаблона остаются здесь; README существующего проекта не заменяется.
При конфликте первоначальной установки запись не начинается.
В проекте сохраняется `.agent/template-lock.json` с версией и исходными хешами.

Обновление из более новой версии чистого шаблона:

```powershell
python Scripts/install_template.py "D:\Projects\NewProject" --update --dry-run
python Scripts/install_template.py "D:\Projects\NewProject" --update
```

Проектные настройки, память, glossary, перечень документов и содержимое продукта имеют политику `seed` и сохраняются.
Общие инструменты и правила обновляются только при отсутствии конфликта с локальной правкой.
Локально удалённые и исключённые из новой версии файлы автоматически не восстанавливаются/не удаляются.
После ручного объединения конфликтующего файла его можно явно принять через `--accept-merged "AGENTS.md"` вместе с `--update`.
Автоматического слияния текста нет; сначала изучи план, затем подтверди конкретные ручные объединения.
У проектов первой версии без receipt нет достоверной базы обновления: первоначальное объединение выполняется вручную.

## После переноса

Из корня нового проекта, Python 3.10+:

```powershell
python -m pip install -r Docs/_brain/requirements.txt
python Scripts/agent.py doctor
python Scripts/agent.py sync
python Scripts/agent.py verify fast
```

Заполни [паспорт проекта](Docs/agent-rules/PROJECT.md), [.agent/project.json](.agent/project.json) и [brain.yaml](Docs/_brain/brain.yaml).
Пока команды приложения не заданы, `verify` возвращает код 2 и прямо сообщает, что продукт не проверен.
Сборка индекса не означает успешной компиляции игры.
Переносимая инструкция: [SETUP](Docs/agent-rules/SETUP.md); полный справочник команд: [OPERATIONS](Docs/agent-rules/OPERATIONS.md).

## Что включено

| Элемент | Назначение |
|---|---|
| [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md) | Единый набор основных правил и подключение Claude |
| [WORKFLOW](Docs/agent-rules/WORKFLOW.md), [C#](Docs/agent-rules/CSHARP.md), [Unity](Docs/agent-rules/UNITY.md) | Подробные предпочтения по задаче |
| [INDEX](Docs/INDEX.md), [Second Brain](Docs/_brain/README.md) | Документы, реестры, карта символов, относительные ссылки |
| [Memory](Docs/Memory/) | Долговременные решения и незавершённая работа |
| [agent.py](Scripts/agent.py) | Doctor, проверки проекта, sync, актуальность и подтверждение сверки |
| [.agent/workflows](.agent/workflows/) | Три общие процедуры для skills Codex и Claude |
| [.agent/evals](.agent/evals/) | Шесть контрольных задач для оценки поведения агента |
| [.claude/settings.json](.claude/settings.json) | Проверка документации при Stop, без записи в проект |
| [.obsidian](.obsidian/) | Vault в корне проекта, относительные Markdown-ссылки |
| [MIGRATION](Docs/agent-rules/MIGRATION.md) | Что сохранено и исключено из исходных настроек |

## Проверка и развитие самого шаблона

```powershell
python Scripts/refresh_manifest.py --version 2.0.0
python Scripts/agent.py verify full
```

Manifest выпускается после изменения исходного payload; установленный проект с receipt не может неявно стать новым чистым шаблоном.
Проверки охватывают перенос, обновление, конфликты, hook, воспроизводимость и диагностику.
Они не доказывают улучшение поведения LLM; для этого предусмотрены [контрольные прогоны](Docs/agent-rules/EVALUATION.md).
Вызовы модели не выполняются автоматически и не входят в Python-тесты.

Механизмы подключения проверены по [официальной документации OpenAI](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [skills Codex](https://learn.chatgpt.com/docs/build-skills), [skills Claude](https://code.claude.com/docs/en/skills) и [hooks Claude](https://code.claude.com/docs/en/hooks).
Само наличие файлов не подтверждает загрузку в установленном агенте: проверь skills, `/context` и `/hooks` в его интерфейсе.
