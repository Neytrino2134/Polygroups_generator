# Start Phase 2

The coordinator owns one queue and advances the existing Restore, LOD preparation,
prepared export, blend export, ZBrush and Auto Render implementations in that order.
Each selected pass has a queue entry, state and progress. Failures stop admission of
later passes. Completed output is retained. Progress and Queue shows either Phase 1
or Phase 2; the Phase 2 queue is also drawn under Start Phase 2 and in the viewport.

Restore automatically scans first. Its mode controls import-only, rebake or rebake
plus stage-01 resculpting; MID remesh is independent. Preparation uses one engine
for both LOD preparation and rename. Existing detailed export/render settings remain
in effect. The coordinator temporarily delays Generated cleanup until exports finish.

Pause finishes the current collection/file/render image before waiting. Resume keeps
the same iterator. Stop After Stage finishes the current pass and admits no next pass.
Stop Now permanently ends this run at the next safe host boundary; an active Blender
bake/render is allowed to return before input data or visibility is changed. A new
Start builds a new run, rather than replaying partially finished work automatically.

ZBrush completion requires the exact manifest job ID, a finished result with every
asset successful and each output ZTL nonempty. Missing/stale results wait without
cleanup. Error results stop the run, preserving inputs. ZBrush confirmation dialogs
can still block ZBrush; the coordinator never treats a blocked process as success.

Blender must stay open. Loading a file, Undo, Redo or disabling the addon terminates
the coordinator. Work is not resumed automatically after restart. Phase 1 integration
uses the common queue display; Start Import chaining is reserved for a later change.

Overall progress gives each enabled pass one equal share; it is a completion metric,
not an estimated remaining time. Restore collection timing starts when that collection
begins processing, excluding a pause before its admission. Total/pass timers are wall
clock time, including pauses. All completed collection durations remain in runtime
queue state; the panel displays the most recent four.

Native file export, mesh preparation and auxiliary texture/freestyle image operations
are synchronous Blender calls; progress advances when those calls return. Main scene
renders run asynchronously in the GUI, with per-image progress and sample statistics
when supplied by the render engine. Output settings and original visibility are
restored through the existing stage implementations. The coordinator does not save
or overwrite the working blend automatically on completion.

Validation: native two-collection restore -> LOD/rename -> GLB + FBX + Blend + OBJ ->
verified synthetic ZBrush result -> cleanup -> transparent/scene PNG chain, controls,
wrong/incomplete/failed ZBrush result rejection. A separate GUI Blender test exercises
real asynchronous rendering, pause after the current image and resume. Full ZBrush
execution itself is not part of the automated coordinator tests.

Pause/Resume/Stop are also written to a job-ID-scoped control file for ZBrush.
The ZBrush job reads it between complete ZTL assets, so it never interrupts an
in-progress import/projection/save. Stop Now ends the Blender coordinator immediately
when its own host is safe and requests ZBrush to stop after its current asset.
A modal confirmation already blocking ZBrush still requires manual confirmation;
control messages do not dismiss dialogs or terminate the application process.

Start Phase 2 process settings include **Load from File**, using the same filename
parser as Unity Rename. It fills Asset Name, Name Index and Version Index for
the selected FAB/Unity pipeline. Existing Unity Rename buttons retain their
original Unity-only behavior.

**Export ZBrush ZTL → Run at End** (RU: **Делать в конце**) defaults off.
When enabled, the queue runs rendering before ZBrush, then performs cleanup.
Cleanup is deferred because it deletes Generated collections needed for ZBrush.
With rendering disabled, ZBrush follows the other enabled passes. With ZBrush
disabled, the option does not change queue ordering. The queue order is fixed
when the process starts. Automated validation includes actual rendering before
the simulated ZBrush launch, with Generated sources retained until cleanup.
## ReBake: исправление, упаковка и стабильность Multires

Нажатие **ReBake Final Mesh** в Phase 2 или Baking открывает окно проверки.
Оно показывает фактический режим запуска: выбранный MID с источником highpoly
либо полный список Queue, а также ошибки предварительной проверки и включённые
дополнительные операции. Текстуры и экспорт могут быть перезаписаны — это указано
в окне. До нажатия **Запустить** меши не исправляются, highpoly не импортируется,
файлы не записываются. Закрытие/отмена окна не запускает ReBake.
Перед запуском список и источники проверяются повторно; изменение выбранной пары
или очереди требует заново открыть окно. Программный `EXEC_DEFAULT` сохраняет
прямой запуск для внутренних сценариев и автоматизированных тестов.

Источник highpoly выбирается по ступеням:

1. Выделены highpoly и активный финальный `SM_..._NN_MID`: использовать выбранный
   highpoly с любым именем. При таком выборе автоматический поиск не выполняется.
2. Выделен только MID: найти `Generated.N` в текущей сцене, в том числе в скрытых
   вложенных коллекциях. Внутри неё сначала искать `Highpoly_Generated.N`, затем
   `Resculpting_01_Highpoly_Generated.N`.
3. Если такой коллекции в сцене нет, временно импортировать `!Blend/Generated.N.blend`
   и искать меши в его `Generated.N` в том же порядке. Если рабочий файл уже
   находится в `!Blend`, искать рядом с ним. После работы удаляются только
   временно импортированные данные.

`N` берётся из последнего числового индекса MID; `.1`, `.01`, `.001` сопоставляются
по числу. Меши вне нужной коллекции не участвуют в автоматическом поиске.
Если коллекция существует, но в ней нет подходящего highpoly, запуск выдаёт
понятную ошибку; неоднозначные источники не выбираются случайным образом.
В очереди каждый MID использует автоматический поиск независимо от выделения
других MID. Явная пара highpoly + активный MID имеет приоритет над очередью;
выделенные самой процедурой экспорта LOD не считаются такой парой при запуске очереди.
Для автоматического поиска после экспорта нужно снова выделить только MID.

Порядок подготовки ReBake Final Mesh: **Repair Mesh → Repack UV → ReBake**.
Исправление выполняется при включённом Repair Mesh; упаковка — при включённом
Repack UV If Repair Changed UV, если исправление изменило UV или число UV-углов. Оба шага
завершаются до подготовки материалов, запекания и создания диагностического
снимка. Повторный запуск после неудачной упаковки сохраняет требование упаковки,
даже если Repair Mesh уже выключен. Неудачная упаковка останавливает ReBake.

Для highpoly с Multires один раз создаётся временный evaluated-меш на уровне
Render. Все проходы BaseColor, Normal и диагностики используют его поверхность
и UV. Это устраняет ложное `Evaluated geometry/UVs changed during diagnostics`:
при смене диагностических материалов Blender может слегка пересчитать UV
Multires без редактирования исходного меша. По завершении, отмене или ошибке
восстанавливаются исходный mesh datablock и настройки модификаторов;
временный меш удаляется. Исходный highpoly не применяется и не сохраняется.

Проверка настоящих изменений остаётся строгой: ошибка содержит имя объекта
и изменившиеся компоненты, например `UV`, `vertices` или `topology`.
Подготовка Unreal LOD допускает служебные плашки BaseColor/Normal с меткой
`polygroups_texture_plane` внутри коллекции ассета: они остаются на месте,
не переименовываются и не входят в набор LOD. Посторонние объекты по-прежнему
блокируют подготовку; сообщение теперь перечисляет их имена.
Регрессия `test_rebake_preparation_order_blender.py` проверяет порядок операций,
повтор упаковки, реальные Cycles-проходы и восстановление исходных данных.
`check_container_rebake_multires_blender.py` проверяет Containers на 32×32
с выводом во временную папку и контролем хешей исходных текстур.

## ReLOD и статус Start Phase 2

Внутри **Start Phase 2** подсекция **Status and Statistics** содержит статус
пайплайна, общую и текущую шкалы прогресса, статистику этапов/времени,
статус обработки, ReBake, ReLOD и Rename. Её можно свернуть целиком.

Непосредственно над ней расположена **ReLOD**:

- **Re-create LODs** обрабатывает все меши текущей сцены с суффиксами `_MID`
  и `_HIGH`, включая скрытые. Если у ассета есть оба источника, используется MID.
- **Delete Current LODs** разрешает замену старых LOD и их подписей. По умолчанию
  выключено: если LOD уже существуют, запуск останавливается до изменения сцены.
- **Decimate Method** по умолчанию **UV Preserve**; начальный режим швов — Lock.
  Метод и режим швов ReLOD независимы от настроек других запусков.
- Количество LOD, лимиты треугольников, расположение и подписи берутся из Smart LODs.
  Имена сохраняют основу источника: `<основа>_LOD0`, `<основа>_LOD1`, …
- **Re-export FBX / Blend** по умолчанию выключено. При включении после успешной
  генерации каждого ассета заменяет FBX и его Blend тем же механизмом, что ReBake
  Final Mesh: исходные MID/HIGH и новые LOD, без плашек текстур. Имена LOD ReLOD
  остаются в формате Unreal/FAB; FBX использует настройки сортировки Phase 2,
  Blend сохраняется в `!Blend` рядом с рабочим файлом. Рабочий файл должен быть
  сохранён, а источник — принадлежать одной однозначной коллекции ассета.
  Рабочая сцена не пересохраняется; видимость и выделение восстанавливаются.
  Если генерация не удалась, экспорт не начинается. Если экспорт не удался,
  уже созданные LOD сохраняются в сцене, очередь останавливается со статусом ошибки.
- **Export / Update JSON** — отдельная опция, по умолчанию выключена; работает
  и без Re-export FBX / Blend. После успешного завершения всего ReLOD записывает
  общий `!Unreal/MeshInfo.json` со всеми пересозданными ассетами, текущими LOD,
  числом вершин/треугольников и общей статистикой. Старые уровни, которых больше
  нет, удаляются из списка JSON. При включённом FBX ссылки на существующие файлы
  сохраняются в `files`; JSON не ограничивается последним обработанным ассетом.
  Если есть FAB Media JSON (Text или сохранённый файл), обновляются его измеряемые
  поля: имена файлов, количество ассетов, средние и предельные поликаунты.
  Заголовки и описания сохраняются. Невалидный существующий FAB JSON блокирует
  запуск до изменения LOD. При остановке/ошибке генерации общий JSON не заменяется.
- ReLOD не запускает ReBake или переименование исходных MID/HIGH.
  Исходная геометрия, UV, трансформации и ограничения видимости сохраняются.
- **Stop ReLOD** находится в Status and Statistics. Незавершённый текущий набор
  откатывается; ранее завершённые ассеты остаются. Ошибка генерации также
  восстанавливает старые LOD и подписи текущего ассета. Reset State поддерживает ReLOD.

Регрессии: `tests/test_relod_blender.py` — реальная UV Preserve генерация,
замена, отказ при конфликте имён, остановка/ошибка с откатом и вложенность UI.
Проверка `Containers_01_01.blend` без сохранения исходника пересоздала пять LOD:
2878 / 1490 / 1000 / 498 / 148 треугольников; MID и его UV остались неизменными.


## Start Phase 2 presets, shared settings and confirmation

- `Process Settings` (and Import Processing stage 13) show the same live settings as Restore and Processing,
  Batch Finalization and Auto Render. Pairs are mirrored in both directions by update callbacks in
  `settings/preparation.py` (`phase2_run_mid` <-> `phase2_mid_remesh`, resculpt options, cleanup, transparent,
  restore mode <-> `phase2_auto_bake`, pipeline engine, prepare). Mirroring pauses while the pipeline runs,
  because the pipeline overrides the manual values temporarily.
- Presets `Unreal Export` and `Unreal Export + ZBrush` (`operators/phase2_start_dialog.py`). Unreal Export
  keeps MID remesh, rebake, FBX, Blend and render, and switches off Retopo_01 resculpting, ZBrush and cleanup.
  Unreal Export + ZBrush enables the whole pipeline. `Return to Blender and Cleanup` belongs to Export ZBrush
  and only runs together with it.
- `Include Retopo_01 if No Resculpting` keeps Retopo_01 next to Highpoly_Generated.N in the Generated.N blend
  when Resculpting_01 is not made or not found (`keep_retopo01_for_blend`).
- `Start Phase 2 Process` and the Phase 1-2 import buttons (stage 13 on) open a confirmation dialog with the
  asset name (translate and Load from File buttons), indices, pipeline and GLB/FBX before starting.
- Defaults: Autosave Completed Collections, FBX export, Export Generated.N with highpoly and Retopo_01,
  ZBrush Return to Blender and Cleanup, Skip Renders with Scene.
