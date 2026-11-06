# Правила и профили требований

**Профиль** — это набор требований к конкретному типу документа.
Описывается в YAML в папке [`profiles/`](../profiles/). Профиль может наследоваться от другого
(`extends`), чтобы методичка вуза переопределяла только отличия от ГОСТа.

## Источники требований (собрать в первую очередь)

| Документ | Что регулирует |
|---|---|
| Правила документирования и управления документацией РК (adilet.zan.kz) | Госдокументы и документы организаций: реквизиты, бланки, заявления, письма, приказы |
| Официальные образцы заявлений (egov.kz, сайты госорганов) | Шаблоны, поля которых должны быть заполнены |
| ГОСТ 7.32-2017 | Отчёт о НИР — основа для курсовых и дипломов (проверить действие в РК) |
| ГОСТ 2.105 | Общие требования к текстовым документам (проверить действие в РК и редакцию) |
| ГОСТ 7.1-2003 | Библиографическая запись (список литературы) (проверить действие в РК) |
| ГОСТ 7.0.5-2008 | Библиографическая ссылка (проверить действие в РК) |
| СТ РК (национальные стандарты) | если есть СТ РК на тему — он важнее межгосударственного ГОСТ |
| Методички вузов РК | Отличия от ГОСТа — у каждого вуза свои |

> Проект только для Казахстана: российские стандарты (ГОСТ Р …) не используем.

> ⚠️ Перед тем как кодировать правило, **сверить его с актуальной редакцией стандарта**
> и в YAML указать источник (`source`). Нельзя писать правила «по памяти».

## Формат профиля

Схема — `src/normocontrol/profiles/schema.py` (Pydantic, неизвестные ключи запрещены — опечатка
даёт понятную ошибку). Раздел, которого нет в профиле, не проверяется. У каждого раздела есть
`severity` (`error` / `warning` / `info`) и `source` — пункт официального документа.

```yaml
id: kru-mi-049-2026
title: "КРУ им. А. Байтұрсынұлы — курсовые и дипломные работы (МИ 049-2026)"
status: active            # draft — в отчёте предупреждение «профиль-черновик»
extends: null             # id базового профиля (глубокое слияние, списки заменяются)
doc_types: [coursework, thesis]
languages: [ru, kk]

page:                     # формат, ориентация, поля, нумерация страниц
  size: A4                # или список [A4, A5]
  margins_cm: {left: 3.0, right: 1.0, top: 2.0, bottom: 2.0}
  margins_mode: exact     # exact (± tolerance_cm) | min («не менее» — Правила № 236)
  numbering: {required: true, position: bottom-center, title_page_numbered: false}
  source: "МИ 049-2026, п. 47 (с. 13–14)"
body_text:                # основной текст (без титула, оглавления, таблиц, подписей)
  font_family: ["Times New Roman"]
  font_size_pt: 14        # или {min: 12, max: 14, recommended: 14}
  line_spacing: 1.0
  first_line_indent_cm: 1.25
  alignment: justify      # null — не проверять
text:                     # чистота текста
  forbid_dash_paragraphs: true
  forbid_placeholders: true
  max_consecutive_empty_paragraphs: 2
headings:                 # section — «1 …», subsection — «1.1 …», structural — «Введение»…
  structural: {case: sentence, bold: true, alignment: center, new_page: true, trailing_dot: false}
structure:
  required_sections:
    - {name: "Титульный лист", kind: title_page}
    - {name: "Содержание", aliases: ["Мазмұны"]}
    - {name: "Основная часть", any_heading: true}
  check_order: true
  toc_matches_headings: true
figures:  {caption_pattern: "...", caption_position: below, caption_alignment: center, numbering: continuous, require_reference: true}
tables:   {caption_pattern: "...", caption_position: above, caption_alignment: left, caption_indent: none}
bibliography: {checker: llm, require_citation_in_text: true, order: appearance, entry_number_trailing_dot: false}
requisites:               # реквизиты служебных документов
  items:
    - {id: order_prikazyvayu, name: "ПРИКАЗЫВАЮ", pattern: "ПРИКАЗЫВАЮ\\s*:?$", required: true, uppercase: true, bold: true}
dates: {formats: [numeric, verbal]}
rag_sources:              # из каких источников RAG берёт пункты (priority 1 важнее 2)
  - {source: "МИ 049-2026", priority: 1}
```

Проверить все профили: `normocontrol profiles validate`; итоговый профиль с учётом `extends`:
`normocontrol profiles show <id>`.

## Каталог правил

| rule_id | Что проверяет | checker | Раздел профиля |
|---|---|---|---|
| `page.size` | формат листа | rule | `page.size` |
| `page.orientation` | ориентация (альбомный раздел с таблицами — совет) | rule | `page.orientation` |
| `page.margins` | поля (точно или «не менее») | rule | `page.margins_cm` |
| `page.numbering` | наличие, положение, нет номера на первой странице | rule | `page.numbering` |
| `font.family` | гарнитура основного текста (с учётом наследования стилей и темы) | rule | `body_text.font_family` |
| `font.size` | кегль (min / max / рекомендуемый — совет) | rule | `body_text.font_size_pt` |
| `paragraph.line_spacing` | межстрочный интервал | rule | `body_text.line_spacing` |
| `paragraph.first_line_indent` | абзацный отступ, в т. ч. «отступ пробелами» | rule | `body_text.first_line_indent_cm` |
| `paragraph.alignment` | выравнивание | rule | `body_text.alignment` |
| `text.dash_paragraphs` | абзацы с дефисами / маркерами | rule | `text` |
| `text.double_spaces`, `text.empty_paragraphs` | двойные пробелы, пустые абзацы вместо интервалов | rule | `text` |
| `text.placeholders` | незаполненные поля шаблона: `<ФИО>`, `[дата]`, `ХХХХ` | rule | `text` |
| `heading.case`, `heading.trailing_dot`, `heading.bold`, `heading.underline`, `heading.alignment`, `heading.indent`, `heading.number_format`, `heading.new_page` | оформление заголовков | rule | `headings` |
| `structure.required_sections`, `structure.section_title` | обязательные разделы (нечёткое сравнение, рус/каз) | structure | `structure` |
| `structure.order` | порядок разделов | structure | `structure.check_order` |
| `structure.toc_matches` | содержание повторяет заголовки | structure | `structure.toc_matches_headings` |
| `figures.caption_format` / `tables.caption_format` | подпись по образцу | structure | `figures` / `tables` |
| `figures.caption_position` / `tables.caption_position` / `*.caption_missing` | подпись под рисунком / над таблицей, подписи нет | structure | — " — |
| `figures.caption_alignment` / `tables.caption_alignment` | выравнивание и отступ подписи | structure | — " — |
| `figures.numbering` / `tables.numbering` | сквозная или по разделам | structure | — " — |
| `figures.referenced` / `tables.referenced` | на каждый рисунок / таблицу есть ссылка | structure | — " — |
| `bibliography.cited`, `bibliography.unknown_citation` | на каждый источник есть ссылка `[N]`, ссылки ведут к источникам | structure | `bibliography` |
| `bibliography.order` | порядок появления ссылок / алфавит | structure | `bibliography.order` |
| `bibliography.numbering` | «1 Иванов…» без точки (или с точкой) | structure | `bibliography.entry_number_trailing_dot` |
| `bibliography.format` | каждая запись — по правилам и образцам из RAG | llm | `bibliography.checker: llm` |
| `requisites.<id>` | наличие и оформление реквизита | rule | `requisites.items` |
| `dates.format` | ДД.ММ.ГГГГ или словесно-цифровой | rule | `dates` |

Однотипные нарушения группируются: «Шрифт Arial в 47 абзацах (стр. 5–19)» — одна ошибка.

## Как добавить правило

1. Функция в модуле `src/normocontrol/rules/` или `structure/` с декоратором
   `@rule("<id>", category=..., applies=lambda profile: ...)` — движок менять не нужно.
2. Параметры — в схему профиля (`profiles/schema.py`) и в YAML с `source`.
3. Мутация в `src/normocontrol/dataset/mutations.py`, которая вносит эту ошибку: тест
   `tests/rules/test_mutations_e2e.py` проверит, что правило её ловит и не даёт ложных срабатываний.
4. `make eval` — замер precision / recall.

## Как добавить новый профиль

1. Скопировать `profiles/gost-7.32-2017.yaml`.
2. Указать `extends: gost-7.32-2017` и переопределить только отличия.
3. Если документ нового типа — научить генератор (`dataset/builders.py`) собирать правильный образец.
4. Прогнать `make check` и `make eval`.
