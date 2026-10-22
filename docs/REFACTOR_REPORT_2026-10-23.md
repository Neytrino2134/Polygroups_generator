# Результат первой серии рефакторинга

## Что проверено

Инвентаризация и разбор синтаксиса всех 331 текущих Python-файлов (74 304
строки, включая тесты и вспомогательные скрипты). Полный список размеров и
числа top-level определений: `refactor_inventory.json`. Это структурный аудит,
а не подтверждение корректности каждого алгоритма аддона.

## Выполненные блоки

1. `properties.py`: 3314 → 178 строк. 15 RNA-классов перенесены в
   `settings/preparation.py`, `seams.py`, `finalization.py`, `render.py`,
   `baking.py`, `ai.py`. Общие callbacks и enum-константы находятся в
   `settings/callbacks.py`. Самый большой новый файл — 880 строк.
   Исходный модуль сохраняет импорты классов и порядок register/unregister.
2. `operators/object_seam_cutter.py`: 4310 → 3793 строки. Выделены
   `cutter_screen.py` (picking, axis locks, arc/section geometry) и
   `cutter_overlay.py` (четыре GPU preview). Зависимость однонаправленная:
   operator → overlay → screen. Старые имена доступны из operator-модуля.

Коммиты: план `140a104`, настройки `72637bb`, резаки `dc6a0e4`.

## Проверки

- `scripts/check_refactor.py`: синтаксис всех Python-файлов; 188 функций и
  классов совпадают по AST с исходным коммитом `140a104`; значения констант
  настроек и упорядоченный CLASSES также совпадают. Допустимое отличие —
  уровень относительных импортов после переноса callbacks в подпакет.
- `git diff --check`: без ошибок whitespace.
- Blender 5.2.2 LTS, отдельный factory-startup процесс для каждого теста.
  Успешны 12 проверок: panel_defaults, panel_visibility_stages,
  remesh_defaults, render_resolution_presets, cutter_draw_stabilize,
  object_seam_cutter, cutter_autofix, cutter_backup, mirror_cutter_transforms,
  local_ring_fit, local_contour_cutter_apply, refactor_settings_lifecycle.
- Lifecycle: два цикла unregister/register, идентичность экспортируемых
  классов и сохранение/повторное чтение трёх групп настроек через `.blend`.
- `test_import_queue.py` падает на строке 59, ожидая LOW для
  batch_stage_4_remesh_preset. `scripts/check_import_queue_baseline.py`
  воспроизвёл тот же сбой в отдельной временной копии исходного коммита.
  Тест останавливается на этом assertion: последующая часть очереди этим
  запуском не проверена. Значения настроек в рамках переноса не изменялись.

## Воспроизведение

Запустить `python scripts/check_refactor.py`, затем
`python scripts/validate_refactor_blender.py <путь-к-blender.exe>`.
Последняя команда ожидаемо вернёт ненулевой код, пока прежнее расхождение
test_import_queue не будет устранено отдельной правкой. Каждый Blender-лог
сохраняется в игнорируемый `refactor_test_*.log` в корне аддона.

## Следующая очередь и границы

UI (4894 строки), оставшиеся cutter operations (3793), baking (2350) и
import_queue (2008) остаются кандидатами. Последовательность дальнейшего
разделения и необходимые проверки указаны в плане. Общие mutable state и
modal/timer lifecycle требуют самостоятельных этапов.

GPU previews перенесены без изменения AST; визуальная отрисовка в
интерактивном окне Blender не проверялась. Полный набор тестов аддона не
запускался. Изменения закоммичены локально; отправка в remote не выполнялась.

## Серия 2: UI и Baking

Коммиты: UI `673c407`, Baking `b221644`.

- `ui.py`: 4894 → 869 строк. 13 workflow-панелей перенесены в шесть
  предметных модулей `ui_panels/`, 33 общих определения — в `common.py`
  (1024 строки). Главная панель, меню и регистрация остаются в `ui.py`.
- Девять transient-флагов объединены в `ui_state.DrawState`. Custom UI и
  тесты обращаются к единому `ui.state`; приватные `_SEARCH_*` и подобные
  переменные модуля заменены полями объекта. Публичные классы и функции
  доступны через исходный модуль `ui`.
- Обнаружение сворачиваемых групп и static inventory теперь учитывают
  новые файлы панелей. Тестовые UI-артефакты сохраняются во временный каталог,
  поэтому запуск теста не перезаписывает отслеживаемый control_inventory.json.
- `scripts/compare_ui_capture.py` сравнил фактические деревья элементов,
  значения и привязки с отдельной копией `6c502bf`: идентичны **39 captures**
  (13 панелей × Object/Edit/Sculpt) и **1094 static UI calls**. Результат:
  `refactor_ui_equivalence.json`.
- `operators/baking.py`: 2350 → 1106 строк. Выделены `bake_constants.py`,
  `bake_cage.py`, `bake_images.py`, `bake_geometry.py`, `bake_merge.py`.
  Самый большой новый модуль — 660 строк. Modal task, cursor и orchestration
  с cleanup остались в исходном модуле. Импорты прежних helper-имён сохранены.
- AST-аудит: 346 Python-файлов; эквивалентны 340 определений, константы и
  регистрационные списки. Для UI разрешена только проверяемая подстановка
  global name → соответствующее поле DrawState и удаление его global statement.

В Blender 5.2.2 прошли **18 различных тестов**: 12 UI/lifecycle проверок и
6 bake/cage проверок. Последние включают реальные bake/save, Alpha Merge,
Artifact Mask, экспорт масок и восстановление после намеренной ошибки записи
изображения. Запуск:

`python scripts/validate_refactor_blender.py <blender.exe> --suite ui-bake`

Базовый сбой import_queue из первой серии в этом блоке не исправлялся.
Оставшиеся крупные кандидаты: object_seam_cutter.py (3793 строки),
import_queue.py (2008 строк). Визуальная GPU-отрисовка в окне не проверялась;
runtime capture проверяет структуру и привязки, но не итоговые пиксели.

## Серия 3: очередь и оставшийся код резаков

Коммиты: fixtures `9bffec0`, ImportQueue `c07ad39`, Cutters `df14666`.

`operators/import_queue.py`: 2008 → 1255 строк. В `queue_storage.py`
перенесены 11 функций сохранения/восстановления коллекций и idle snapshot.
`QueueProcessingMixin` содержит 21 связный метод подготовки и обработки;
`QueueRedoMixin` — три метода backup/recovery. Singleton ACTIVE_QUEUE, timer,
step/advance/finish и классы операторов остаются в исходном модуле.
Все прежние методы доступны через ImportQueue.

`operators/object_seam_cutter.py`: 3793 → 1117 строк. Добавлены:

| Модуль | Назначение | Строк |
| --- | --- | ---: |
| cutter_constants.py | метаданные и ограничения | 38 |
| cutter_paths.py | данные кривых, координаты, tilt | 308 |
| cutter_objects.py | создание, выбор и объединение объектов | 608 |
| cutter_mesh.py | применение резаков и исправление геометрии | 937 |
| cutter_draw.py | интерактивные инструменты рисования | 1061 |

Зависимости: constants → paths → objects → mesh; draw использует constants,
paths, objects и ранее выделенные screen/overlay. Обратных импортов в фасад
object_seam_cutter нет. Публичные имена сохранены через явные импорты.

### Проверки серии 3

- Синтаксис всех 356 Python-файлов; 360 эквивалентных исходных определений.
  Для ImportQueue аудитор объединяет методы класса и двух mixin-классов,
  проверяет отсутствие потерь/дублирования и сравнивает каждое тело, сигнатуру
  и декораторы. Константы и регистрационные списки сохранены.
- Дополнительно symtable проверяет отсутствие необъявленных глобальных
  зависимостей в выделенных settings/UI/bake/queue/cutter модулях.
- Сводный `--suite queue-cutter`: **20 PASS / 1 FAIL**. Успешны redo,
  recovery, отдельные blend-файлы, idle-state после успешной/неудачной записи,
  autobake, geometry repair, smart finalization, режимы импорта, cutters,
  mirror, backup, grid, local ring/contour/sketch и регистрация.
- Новый boundary test проверяет сохранение ownership вновь созданных IDs
  после исключения и восстановление Object Mode после ошибки Smart Relax,
  включая изоляцию shared mesh data.
- `scripts/validate_cutter_ui.py`: **2/2 PASS** в отдельных оконных процессах
  Blender 5.2.2 с event simulation. Проверены все этапы Apply Cutter Seams,
  прогресс/backup/cursor draw и интерактивный Grid preview с очисткой callback
  после отмены. Скрипт проверяет свежий success marker, а не только exit code.
  Визуальное сравнение пикселей вручную не выполнялось.
- `git diff --check`: без ошибок.

### Оставшееся расхождение большого теста очереди

Fixtures приведены к уже существовавшим defaults MID/Auto Bake=True;
LOW и отключённый autobake заданы явно для старых сценариев. В искусственные
launcher objects добавлен действующий флаг do_selected. Настройки аддона
не менялись. Fault injection обновлён на модули, владеющие реализациями.

После этого `test_import_queue.py` доходит до строки 345 и падает на
`assert set(bpy.data.objects) == existing | {unrelated}` после rollback.
Та же ошибка воспроизведена в отдельном checkout `9bffec0`, где production
код ещё не подвергался серии 3. Это прежнее расхождение теста с поведением;
оно не исправлялось в рамках структурных переносов. Часть этого большого
теста после строки 345 не выполнена. Воспроизведение baseline:

`python scripts/check_import_queue_baseline.py <blender.exe> --baseline 9bffec0 --expected "assert set(bpy.data.objects)"`

### Общий результат трёх серий

| Исходный файл | До | Сейчас |
| --- | ---: | ---: |
| ui.py | 4894 | 869 |
| operators/object_seam_cutter.py | 4310 | 1117 |
| properties.py | 3314 | 178 |
| operators/baking.py | 2350 | 1106 |
| operators/import_queue.py | 2008 | 1255 |

Python-файлов от 2000 строк больше нет. Самый большой — localization.py
(1924 строки, преимущественно словарь), далее render_queue.py (1739).
Размер сам по себе не требует дальнейшего дробления. Полный тестовый набор
аддона не запускался; проверенные границы перечислены выше.
