"""Load this file via ZScript > Python Scripting > Load in ZBrush 2027+."""
import importlib.util
import json
import os
from pathlib import Path
import zbrush.commands as zbc

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('_mesh_to_ztl_converter', HERE / 'converter.py')
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)
PANEL = 'ZPlugin:Mesh to ZTL'
CONFIG = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'MeshToZTL' / 'settings.json'
DEFAULT = r'D:\Work\3D Stocks\3D Asset Packs\!NewAssetPack\06_Crystals_Pack_40_Pieces_In_Revision\Crystals_Pack_02\!ZBrush\Mesh'
settings = dict(folder=DEFAULT, mode='AUTO')
overwrite_existing = False
if CONFIG.exists():
    try:
        settings.update(json.loads(CONFIG.read_text(encoding='utf-8')))
    except (ValueError, OSError):
        pass


def guarded(fn):
    def callback(sender, *args):
        try:
            fn(sender, *args)
        except Exception as error:
            zbc.message_ok(str(error), 'Mesh to ZTL - Error')
    return callback


def save_settings():
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    converter.save_json(CONFIG, settings)


@guarded
def choose_folder(sender):
    global _folder_dialog
    existing = globals().get('_folder_dialog')
    if existing is not None and existing.thread.is_alive():
        existing.activate()
        return
    window_spec = importlib.util.spec_from_file_location('_mesh_to_ztl_window', HERE / 'folder_window.py')
    window_module = importlib.util.module_from_spec(window_spec)
    window_spec.loader.exec_module(window_module)
    _folder_dialog = window_module.ModelessController(converter, zbc, settings, save_settings,
                                               overwrite_existing)
    _folder_dialog.run()


@guarded
def cycle_mode(sender):
    modes = ['AUTO', 'RECONSTRUCT', 'PROJECT']
    settings['mode'] = modes[(modes.index(settings['mode']) + 1) % len(modes)]
    save_settings()
    zbc.message_ok(settings['mode'], 'Build mode')


@guarded
def show_status(sender):
    queue = converter.Queue(settings['folder'], settings['mode'])
    counts = dict(done=0, existing=0, pending=0)
    for asset in queue.manifest['assets']:
        counts[queue.status(asset)] += 1
    zbc.message_ok(f"Folder: {queue.root}\nMode: {settings['mode']}\n"
                   f"Verified complete: {counts['done']}\nExisting (unverified): {counts['existing']}\n"
                   f"Pending: {counts['pending']}\nResults: targets from job.json (default ZTL/)\n"
                   'Conversion selects imported tools. Save your current tool before starting.', 'Mesh to ZTL')


@guarded
def toggle_overwrite(sender, value=None):
    # Some ZBrush builds raise SystemError when get() queries Python-created switches.
    # The switch is registered off; each user click changes its state once.
    global overwrite_existing
    overwrite_existing = not overwrite_existing if value is None else bool(value)


@guarded
def convert(sender):
    controller = globals().get('_folder_dialog')
    if controller and controller.window and controller.window.busy:
        raise RuntimeError('Conversion is already running. Use the folder window to stop after the current mesh.')
    queue = converter.Queue(settings['folder'], settings['mode'])
    result = queue.run(zbc, overwrite=overwrite_existing,
                       limit=1 if sender.endswith('Convert Next') else None)
    zbc.message_ok(f"Converted: {result['converted']}\nSkipped: {result['skipped']}\nFailed: {result['failed']}\n"
                   f"Log: {queue.root / 'standalone_log.txt'}", 'Mesh to ZTL')


def register():
    global overwrite_existing
    overwrite_existing = False
    if zbc.exists(PANEL):
        zbc.delete_interface_item(PANEL)
    zbc.add_subpalette(PANEL, title_mode=0)
    zbc.add_button(PANEL + ':Choose Folder', 'Folder browser, clipboard, conversion and status', choose_folder, width=1.0)
    zbc.add_button(PANEL + ':Cycle Build Mode', 'AUTO > RECONSTRUCT > PROJECT; Status shows selection', cycle_mode, width=1.0)
    zbc.add_button(PANEL + ':Status', 'Show folder, mode and saved progress', show_status, width=1.0)
    zbc.add_switch(PANEL + ':Overwrite existing', False,
                   'Replace unverified/stale ZTLs; verified completed assets are skipped', toggle_overwrite)
    zbc.add_button(PANEL + ':Convert Next', 'Convert one pending asset, then return control to ZBrush', convert, width=1.0)
    zbc.add_button(PANEL + ':Convert All - Resume', 'Continue queue, skipping completed assets. ZBrush stays open.', convert, width=1.0)


if __name__ == '__main__':
    register()
