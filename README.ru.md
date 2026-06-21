# Lead Enrichment Outreach

![Preview](assets/preview.svg)

English version: [README.md](README.md)

Основной рабочий путь для проекта:

`/home/clawd/.openclaw/workspace/github/repos/lead-enrichment-outreach`

Этот репозиторий показывает reviewable AI-assisted B2B outreach workflow:

**company/domain -> dossier -> trust review -> draft -> human decision**

Здесь уже есть локальный review UI и HTTP-слой. Локально его можно гонять как single-operator demo, а для публичной демки теперь есть shared-token auth; реальной отправки писем всё ещё нет.

Старые соседние проекты вроде `b2b-outreach-editor` и `startup-ai-outreach-copilot` считаются архивными и не должны восприниматься как основной код.

## Сначала демо

Если нужен самый короткий путь к "покажи продукт", используй так:

```bash
make demo-quick
make demo
make demo-ui
make batch-demo
make ready-export-demo
```

Что это показывает:
- `make demo` выводит 3 trust-статуса: `ready`, `review_required`, `blocked`
- `make demo-ui` открывает review UI на `http://127.0.0.1:8095` с заранее загруженными demo review и demo batch
- `make batch-demo` и `make ready-export-demo` показывают deterministic handoff flow для батча

Документы для презентации:
- `docs/demo/README.md` — walkthrough на 2 минуты
- `docs/demo/SCRIPT.md` — готовый talk track
- `docs/demo/PUBLIC_DEMO.md` — как быстро поднять публичную демку
- `docs/demo/DEPLOY.md` — deploy через systemd/nginx

## Что уже есть в v1

- enrichment лида в dossier JSON
- trust-gating со статусами `ready` / `review_required` / `blocked`
- restrained draft generation
- локальный review UI для:
  - summary по компании
  - review status, reasons, warnings, sources
  - ranked contacts
  - редактирования subject/body
  - операторского решения: `approved` / `rejected` / `needs_review`
- воспроизводимая локальная демка

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest discover -s tests -q
```

Если тесты проходят, проект можно запускать локально.

## Что делать в первые 3 минуты

### 1) Сформулировать story

```bash
make demo-quick
make demo-story
```

Это даёт короткий narrative:

`company/domain -> dossier -> trust gate -> draft -> human decision -> ops-ready export`

### 2) Посмотреть поведение без чтения кода

```bash
make demo
```

Это покажет 3 исхода:
- `ready` -> можно безопасно переходить к draft
- `review_required` -> лид правдоподобный, но нужен человек
- `blocked` -> недостаточно доверия, дальше идти нельзя

### 3) Открыть браузерную демку

```bash
make demo-ui
```

Потом открыть:

```text
http://127.0.0.1:8095
```

Что там есть:
- demo-first hero и 90-second walkthrough
- guided demo блок с подсказкой следующего presenter step
- one-click переходы между `ready`, `review_required`, `blocked`
- dossier компании с source-backed summary
- trust verdict и причины
- ranked contact candidates
- editable outreach draft
- явные human decision controls
- presenter guide
- batch-инструменты для загрузки CSV/JSON, экспорта ready leads и handoff bundle

Рекомендуемый порядок:
- нажать `Start 90-second demo`
- при желании жать `Advance guided step`, чтобы UI сам вёл по сценарию
- сначала показать `ready`
- потом `review_required` и `blocked`
- вернуться к approved handoff / export

### 4) Показать batch handoff

```bash
make batch-demo
make ready-export-demo
```

Это закрывает story:
- demo batch пересобирается детерминированно из `examples/demo/index.json`
- структура батча повторяет ту же логику `ready / review_required / blocked`
- ready-only export даёт чистый handoff вниз по цепочке

## Основные entrypoints

### Enrichment

Для воспроизводимого локального прогона лучше передавать известный домен:

```bash
python3 skill/scripts/enrich_lead.py --company "DeepL" --domain deepl.com
```

На выходе dossier JSON с:
- `search_results` из нескольких HTML search sources
- `primary_site_url`, `site_candidates`, `alternative_candidates`, `why_chosen`
- summary, contact sources, addresses/region hints, confidence, warnings, review verdict
- optional `browser_fallback`, если сайт JS-gated или первый static fetch не сработал

### Генерация draft

```bash
python3 skill/scripts/generate_outreach.py examples/demo/ready/deepl-dossier.json \
  --offer "AI-assisted lead enrichment and outreach"
```

Слабые dossiers по умолчанию блокируются:

```bash
python3 skill/scripts/generate_outreach.py examples/demo/review_required/mistral-ai-dossier.json \
  --offer "AI-assisted lead enrichment and outreach"
```

Override допустим только после явного human review:

```bash
python3 skill/scripts/generate_outreach.py examples/demo/review_required/mistral-ai-dossier.json \
  --offer "AI-assisted lead enrichment and outreach" \
  --allow-review-required
```

### Unified workflow artifact

```bash
python3 skill/scripts/workflow.py \
  --company "DeepL" \
  --domain deepl.com \
  --offer "AI-assisted lead enrichment and outreach"
```

Если не передавать `--domain`, workflow уйдёт в live web search и станет менее воспроизводимым.

### Batch workflow для CSV

```bash
python3 skill/scripts/batch_workflow_csv.py \
  examples/demo-leads.csv \
  --offer "AI-assisted lead enrichment and outreach"
```

На выходе batch JSON artifact с:
- итоговыми counts по `ready`, `review_required`, `blocked`
- workflow artifact по каждому лиду
- понятной видимостью, для скольких лидов реально появился draft

## Позиционирование репозитория

Этот репозиторий лучше воспринимать как:

`reviewable AI-assisted lead enrichment and outreach workflow demo`

А не как полностью production-ready scraping/sending platform.

Главная ценность здесь:
- explainable trust gate
- source-backed dossier
- human-in-the-loop review
- demo-friendly UI и handoff flow
