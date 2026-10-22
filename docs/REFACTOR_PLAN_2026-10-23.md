# План рефакторинга для ИИ агента

## Контракт

Сохранять bl_idname, имена RNA-свойств, значения по умолчанию, порядок
регистрации, пути импорта публичных классов и поведение операций.
Переносить исходный код без переписывания алгоритмов. Не смешивать исправления
поведения с переносами. Рабочее дерево перед началом чистое.

## Приоритеты по инвентаризации исходников

| Файл | Строк | Разделение | Риск |
| --- | ---: | --- | --- |
| ui.py | 4894 | инфраструктура поиска/сворачивания; панели по областям; меню | высокий: общие изменяемые флаги draw/capture/search |
| operators/object_seam_cutter.py | 4310 | геометрия экрана; GPU preview; создание объектов; применение; modal операторы | высокий: зависимости между функциями и modal состоянием |
| properties.py | 3314 | callbacks/constants; группы настроек по областям; фасад регистрации | умеренный: порядок RNA-регистрации и callbacks |
| operators/baking.py | 2350 | выбор источников; подготовка материалов; bake execution; экспорт карт | высокий: восстановление временного состояния сцены |
| operators/import_queue.py | 2008 | сохранение коллекций; этапы обработки; lifecycle очереди; операторы | высокий: singleton, timer, cancel, recovery |
| localization.py | 1924 | словари по языкам и lookup | низкий при проверке полного равенства словарей |

Остальные файлы существенно меньше порога 2000 строк. Размер сам по себе не
основание дробить связный алгоритм или таблицу данных.

## Исполняемая последовательность

0. Инвентаризировать все Python-файлы: синтаксис, размеры, top-level определения.
   Зафиксировать план отдельным коммитом.
1. Одним блоком выделить settings/: общие callbacks и группы preparation,
   seams, finalization, render, baking, AI. Оставить properties.py фасадом
   с явными импортами и исходным register/unregister. Сравнить AST всех
   перемещённых определений с HEAD до переноса; проверить Blender регистрацию,
   defaults, visibility и callbacks. Коммит этапа.
2. Одним блоком выделить экранную геометрию и GPU previews резаков.
   Использовать явные импорты, сохранить старые имена через фасад.
   Избегать циклических импортов, exec, globals().update и proxy модулей.
   Проверить AST и существующие cutter тесты в Blender. Коммит этапа.
3. Сводная проверка: синтаксис всех исходников, git diff --check,
   повторная регистрация/снятие регистрации, связанные Blender regression tests.
   Зафиксировать результаты и границы проверки отдельным коммитом.

## Следующая очередь (отдельные функциональные блоки)

- UI: сначала отделить состояние draw/search/capture в явный объект; затем
  переносить панели. Проверки: panel_search, custom_ui, detached groups, narrow UI.
- Baking: сначала выделить source resolution и подготовку карт; сохранить
  finally-восстановление материалов/selection. Проверки: bake_auto_source,
  bake_alpha_merge, bake_mask_export, bake_artifact_fill.
- Import queue: выделить CollectionStorage и явный job state, затем шаги
  pipeline; сохранить timer/cancel/recovery. Проверки: import_queue,
  batch_order_recovery, batch_separate_idle_state, batch_smart_finalization.
- Не выполнять эти рискованные изменения заодно с первыми двумя переносами.

## Условие приёмки

AST перенесённых определений совпадает (кроме уровня относительных импортов),
регистрация работает в Blender 5.2, выбранные regression tests проходят.
Background проверки не подтверждают визуальную отрисовку GPU в интерактивном окне.

## Продолжение: серия 2

4. UI: перенести девять transient-флагов в ui_state.DrawState; явно обновить
   Custom UI adapters и тесты доступа к состоянию. Выделить 13 панелей по
   областям и общие draw/search helpers, сохранить ui.py как фасад и реестр.
   Обновить сканеры исходников (fold discovery, static inventory).
   Сравнить все 39 runtime captures и набор UI-вызовов с коммитом 6c502bf;
   проверить поиск, отдельные группы, N-panel и lifecycle. Отдельный коммит.
5. Baking: выделить константы, auto cage, материалы/изображения, merge и
   geometric diagnostics по однонаправленным зависимостям. Оставить cursor,
   modal task и orchestration со scene cleanup в baking.py. Проверить AST
   относительно исходного коммита и реальные bake/image regression tests.
   Отдельный коммит, затем обновить общий отчёт.

## Продолжение: серия 3

6. ImportQueue: вынести collection storage в queue_storage.py, связные
   методы обработки в QueueProcessingMixin, redo backup/recovery — в
   QueueRedoMixin. Сохранить очередь, timer, singleton и dispatch в прежнем
   модуле. При проверке AST собрать класс из собственных и унаследованных
   методов, запретить потерю/дублирование методов и изменение их тел.
   Актуализировать только устаревшие test fixtures и места fault injection.
   Отдельно воспроизвести оставшиеся baseline failures до переноса.
7. Cutters: выделить constants, path data, object creation/selection,
   mesh operations и draw modal operators с однонаправленными импортами.
   Сохранить публичные имена, регистрацию и apply session в исходном модуле.
   Проверить AST, cutter/grid/mirror/backup/contour и связанные queue tests.
   Коммит каждого блока после проверок; финальный отчёт отдельным коммитом.
