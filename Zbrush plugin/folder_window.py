"""Native Windows dialog. ZBrush commands always run on the calling UI thread."""
import ctypes as C
from ctypes import wintypes as W
import traceback
import threading
import queue as queues

U = C.WinDLL('user32', use_last_error=True)
K = C.WinDLL('kernel32', use_last_error=True)
S = C.WinDLL('shell32', use_last_error=True)
OLE = C.WinDLL('ole32', use_last_error=True)
LRESULT = C.c_ssize_t
PROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)


def bind(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = result, args
    return fn


create = bind(U, 'CreateWindowExW', W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
              C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p)
default = bind(U, 'DefWindowProcW', LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
send = bind(U, 'SendMessageW', LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
set_text = bind(U, 'SetWindowTextW', W.BOOL, W.HWND, W.LPCWSTR)
get_text = bind(U, 'GetWindowTextW', C.c_int, W.HWND, W.LPWSTR, C.c_int)
get_length = bind(U, 'GetWindowTextLengthW', C.c_int, W.HWND)
enable = bind(U, 'EnableWindow', W.BOOL, W.HWND, W.BOOL)
destroy = bind(U, 'DestroyWindow', W.BOOL, W.HWND)
show = bind(U, 'ShowWindow', W.BOOL, W.HWND, C.c_int)
foreground = bind(U, 'GetActiveWindow', W.HWND)
is_window = bind(U, 'IsWindow', W.BOOL, W.HWND)
instance = bind(K, 'GetModuleHandleW', W.HINSTANCE, W.LPCWSTR)(None)
get_message = bind(U, 'GetMessageW', C.c_int, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT)
peek = bind(U, 'PeekMessageW', W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT)
translate = bind(U, 'TranslateMessage', W.BOOL, C.POINTER(W.MSG))
dispatch = bind(U, 'DispatchMessageW', LRESULT, C.POINTER(W.MSG))
dialog_message = bind(U, 'IsDialogMessageW', W.BOOL, W.HWND, C.POINTER(W.MSG))


class WindowClass(C.Structure):
    _fields_ = [('style', W.UINT), ('proc', PROC), ('cls_extra', C.c_int), ('win_extra', C.c_int),
                ('instance', W.HINSTANCE), ('icon', W.HICON), ('cursor', W.HANDLE),
                ('background', W.HBRUSH), ('menu', W.LPCWSTR), ('name', W.LPCWSTR)]


class BrowseInfo(C.Structure):
    _fields_ = [('owner', W.HWND), ('root', C.c_void_p), ('display', W.LPWSTR),
                ('title', W.LPCWSTR), ('flags', W.UINT), ('callback', C.c_void_p),
                ('param', W.LPARAM), ('image', C.c_int)]


def clipboard_text(owner):
    open_clipboard = bind(U, 'OpenClipboard', W.BOOL, W.HWND)
    close_clipboard = bind(U, 'CloseClipboard', W.BOOL)
    get_clipboard = bind(U, 'GetClipboardData', W.HANDLE, W.UINT)
    lock = bind(K, 'GlobalLock', C.c_void_p, W.HANDLE)
    unlock = bind(K, 'GlobalUnlock', W.BOOL, W.HANDLE)
    if not open_clipboard(owner):
        raise RuntimeError('Clipboard is busy. Try again.')
    try:
        handle = get_clipboard(13)  # CF_UNICODETEXT
        if not handle:
            raise ValueError('Clipboard does not contain text.')
        pointer = lock(handle)
        if not pointer:
            raise C.WinError(C.get_last_error())
        try:
            return C.wstring_at(pointer)
        finally:
            unlock(handle)
    finally:
        close_clipboard()


def browse_folder(owner):
    initialize = bind(OLE, 'CoInitializeEx', C.c_long, C.c_void_p, W.DWORD)
    uninitialize = bind(OLE, 'CoUninitialize', None)
    release = bind(OLE, 'CoTaskMemFree', None, C.c_void_p)
    browse = bind(S, 'SHBrowseForFolderW', C.c_void_p, C.POINTER(BrowseInfo))
    path_from_id = bind(S, 'SHGetPathFromIDListW', W.BOOL, C.c_void_p, W.LPWSTR)
    hr = initialize(None, 2)
    try:
        display = C.create_unicode_buffer(32768)
        info = BrowseInfo(owner=owner, display=C.cast(display, W.LPWSTR),
                          title='Choose exported Mesh or !ZBrush folder', flags=0x41)
        pointer = browse(C.byref(info))
        if not pointer:
            return ''
        try:
            path = C.create_unicode_buffer(32768)
            if not path_from_id(pointer, path):
                raise ValueError('Select a filesystem folder.')
            return path.value
        finally:
            release(pointer)
    finally:
        if hr >= 0:
            uninitialize()


class FolderWindow:
    def __init__(self, converter, zbc, settings, save_settings, overwrite=False, submit=None):
        self.converter, self.zbc = converter, zbc
        self.settings, self.save_settings = settings, save_settings
        self.busy = self.stop = False
        self.submit = submit
        self.events = queues.SimpleQueue()
        self.controls = {}
        self.proc = PROC(self.window_proc)
        # Each loaded script owns its class/callback lifetime; unregister on close.
        self.class_name = 'MeshToZTL_' + str(id(self))
        self.wc = WindowClass(proc=self.proc, instance=instance, background=6, name=self.class_name)
        register = bind(U, 'RegisterClassW', W.ATOM, C.POINTER(WindowClass))
        if not register(C.byref(self.wc)):
            raise C.WinError(C.get_last_error())
        self.hwnd = create(0x10000, self.class_name, 'Mesh to ZTL - Folder and conversion',
                           0x00CA0000, 150, 150, 820, 430, None, None, instance, None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        self.add('STATIC', 'Mesh folder, export folder or job.json:', 0, 18, 14, 770, 22)
        self.add('EDIT', settings['folder'], 10, 18, 40, 770, 28, 0x50810080)
        self.add('BUTTON', 'Browse...', 11, 18, 80, 130, 30)
        self.add('BUTTON', 'Paste (replace)', 12, 158, 80, 150, 30)
        self.add('BUTTON', 'Clear path', 13, 318, 80, 130, 30)
        self.add('BUTTON', 'Apply / Check', 14, 458, 80, 150, 30)
        self.add('STATIC', 'Build mode:', 0, 18, 128, 100, 24)
        self.add('COMBOBOX', '', 15, 122, 123, 170, 160, 0x50210003)
        for mode in ('AUTO', 'RECONSTRUCT', 'PROJECT'):
            text = C.c_wchar_p(mode)
            send(self.controls[15], 0x143, 0, C.cast(text, C.c_void_p).value)
        send(self.controls[15], 0x14E, ('AUTO', 'RECONSTRUCT', 'PROJECT').index(settings['mode']), 0)
        self.add('BUTTON', 'Overwrite existing ZTL', 16, 320, 123, 240, 28, 0x50010003)
        send(self.controls[16], 0xF1, int(overwrite), 0)
        self.add('STATIC', 'Status:', 0, 18, 165, 100, 22)
        self.add('EDIT', 'Choose a folder, then Apply / Check or Start.', 17, 18, 190, 770, 115, 0x50A00844)
        self.add('BUTTON', 'Start / Resume', 18, 18, 325, 180, 36)
        self.add('BUTTON', 'Stop after mesh', 19, 208, 325, 170, 36)
        self.add('BUTTON', 'Open Logs Folder', 21, 388, 325, 180, 36)
        self.add('BUTTON', 'Close', 20, 658, 325, 130, 36)
        enable(self.controls[19], False)

    def add(self, kind, text, ident, x, y, width, height, style=0x50010000):
        handle = create(0, kind, text, style, x, y, width, height,
                        self.hwnd, ident, instance, None)
        if not handle:
            raise C.WinError(C.get_last_error())
        font = bind(C.WinDLL('gdi32'), 'GetStockObject', W.HANDLE, C.c_int)(17)
        send(handle, 0x30, font, 1)
        if ident:
            self.controls[ident] = handle
        return handle

    def text(self, ident):
        text = C.create_unicode_buffer(get_length(self.controls[ident]) + 1)
        get_text(self.controls[ident], text, len(text))
        return text.value

    def status(self, text):
        set_text(self.controls[17], text.replace('\n', '\r\n'))
        bind(U, 'UpdateWindow', W.BOOL, W.HWND)(self.controls[17])

    def pump(self):
        message = W.MSG()
        # Only this window's messages: never dispatch other ZBrush plugin actions mid-job.
        while peek(C.byref(message), self.hwnd, 0, 0, 1):
            if not dialog_message(self.hwnd, C.byref(message)):
                translate(C.byref(message))
                dispatch(C.byref(message))

    def apply(self):
        folder = self.text(10).strip().strip('"')
        if not folder:
            raise ValueError('Enter or browse to an export folder.')
        index = send(self.controls[15], 0x147, 0, 0)
        mode = ('AUTO', 'RECONSTRUCT', 'PROJECT')[max(0, index)]
        self.status('Checking exported meshes...')
        queue = self.converter.Queue(folder, mode)
        self.settings.update(folder=str(queue.root), mode=mode)
        self.save_settings()
        counts = dict(done=0, existing=0, pending=0)
        for asset in queue.manifest['assets']:
            counts[queue.status(asset)] += 1
        self.status(f"Ready: {len(queue.manifest['assets'])} meshes | Mode: {mode}\n"
                    f"Complete: {counts['done']} | Existing (unverified): {counts['existing']} | Pending: {counts['pending']}\n"
                    f"Folder: {queue.root}\nSave your current Tool before starting.")
        return queue

    def start(self):
        queue = self.apply()
        self.busy, self.stop = True, False
        for ident in (10, 11, 12, 13, 14, 15, 16, 18):
            enable(self.controls[ident], False)
        enable(self.controls[19], True)
        overwrite = bool(send(self.controls[16], 0xF0, 0, 0))
        def work():
            try:
                result = queue.run(self.zbc, overwrite=overwrite,
                                   progress=lambda message: self.notify('status', message),
                                   should_stop=lambda: self.stop)
                self.notify('status', f"{'Stopped' if self.stop else 'Finished'}. Converted: {result['converted']} | "
                            f"Skipped: {result['skipped']} | Failed: {result['failed']}\n"
                            f"Logs: {queue.root}\\standalone_commands.log\nProgress saved. Start / Resume continues the queue.")
            except Exception:
                self.notify('status', 'Error:\n' + traceback.format_exc())
            finally:
                self.notify('finished', '')
        if self.submit:
            self.status('Queued on ZBrush main thread. Command log: standalone_commands.log')
            self.submit(work)
        else:
            # Test harness only: production always installs the main-thread dispatcher.
            work()
            self.receive()

    def notify(self, kind, text):
        self.events.put((kind, text))
        bind(U, 'PostMessageW', W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)(self.hwnd, 0x8002, 0, 0)

    def receive(self):
        while not self.events.empty():
            kind, text = self.events.get()
            if kind == 'status':
                self.status(text)
            elif kind == 'finished':
                self.busy = False
                for ident in (10, 11, 12, 13, 14, 15, 16, 18):
                    enable(self.controls[ident], True)
                enable(self.controls[19], False)

    def command(self, ident):
        if ident == 21:
            import os
            from pathlib import Path
            folder = Path(self.settings['folder'])
            if folder.name.lower() == 'mesh' or folder.is_file():
                folder = folder.parent
            os.startfile(str(folder))
        elif ident == 20:
            if self.busy:
                self.stop = True
                self.status('Stopping after current mesh. Close again when conversion stops.')
            else:
                destroy(self.hwnd)
        elif ident == 19:
            self.stop = True
            self.status('Stopping after current mesh...')
        elif not self.busy:
            if ident == 11:
                folder = browse_folder(self.hwnd)
                if folder:
                    set_text(self.controls[10], folder)
                    self.apply()
            elif ident == 12:
                set_text(self.controls[10], clipboard_text(self.hwnd).strip().strip('"'))
                self.status('Path replaced from clipboard. Apply / Check or Start.')
            elif ident == 13:
                set_text(self.controls[10], '')
                self.status('Path cleared. Paste, type or browse to a folder.')
            elif ident == 14:
                self.apply()
            elif ident == 18:
                self.start()

    def window_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == 0x8004:
                show(hwnd, 9)
                position = bind(U, 'SetWindowPos', W.BOOL, W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT)
                position(hwnd, W.HWND(-1), 0, 0, 0, 0, 3)
                bind(U, 'SetForegroundWindow', W.BOOL, W.HWND)(hwnd)
                position(hwnd, W.HWND(-2), 0, 0, 0, 0, 3)
                return 0
            if message == 0x8002:
                self.receive()
                return 0
            if message == 0x10:  # WM_CLOSE
                self.command(20)
                return 0
            if message == 0x111 and (int(wparam) >> 16) == 0:  # WM_COMMAND, BN_CLICKED
                self.command(int(wparam) & 0xFFFF)
                return 0
        except Exception as error:
            print(traceback.format_exc())
            self.status('Error: ' + str(error))
            return 0
        return default(hwnd, message, wparam, lparam)

    def run(self):
        show(self.hwnd, 5)
        message = W.MSG()
        try:
            # Do not post WM_QUIT: this is ZBrush's process, not a standalone app.
            while is_window(self.hwnd):
                result = get_message(C.byref(message), None, 0, 0)
                if result <= 0:
                    if result == 0:
                        bind(U, 'PostQuitMessage', None, C.c_int)(int(message.wParam))
                    break
                if not dialog_message(self.hwnd, C.byref(message)):
                    translate(C.byref(message))
                    dispatch(C.byref(message))
        finally:
            if is_window(self.hwnd):
                destroy(self.hwnd)
            bind(U, 'UnregisterClassW', W.BOOL, W.LPCWSTR, W.HINSTANCE)(self.class_name, instance)


class ModelessController:
    """An independent UI thread; a message-only dispatcher belongs to ZBrush's main thread."""
    def __init__(self, converter, zbc, settings, save_settings, overwrite):
        self.main_ident = threading.get_ident()
        self.tasks = queues.SimpleQueue()
        self.window = None
        self.error = None
        self.ready = threading.Event()
        self.proc = PROC(self.dispatch)
        self.class_name = 'MeshToZTL_dispatch_' + str(id(self))
        self.wc = WindowClass(proc=self.proc, instance=instance, name=self.class_name)
        if not bind(U, 'RegisterClassW', W.ATOM, C.POINTER(WindowClass))(C.byref(self.wc)):
            raise C.WinError(C.get_last_error())
        self.hwnd = create(0, self.class_name, '', 0, 0, 0, 0, 0, W.HWND(-3), None, instance, None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        self.thread = threading.Thread(target=self.ui, args=(converter, zbc, settings, save_settings, overwrite),
                                       name='MeshToZTL-window', daemon=True)

    def run(self):
        self.startup_log('Starting window thread')
        self.thread.start()
        # Release the embedded interpreter's GIL until the window is really shown.
        if not self.ready.wait(timeout=5):
            raise RuntimeError('Folder window did not start in 5 seconds. See standalone_ui_startup.log beside MeshToZTL.py.')
        if self.error:
            raise RuntimeError('Cannot open folder window:\n' + self.error)
        self.activate()

    def startup_log(self, message):
        import datetime
        import os
        from pathlib import Path
        try:
            with Path(__file__).with_name('standalone_ui_startup.log').open('a', encoding='utf-8') as handle:
                handle.write(f'{datetime.datetime.now().isoformat()} tid={threading.get_ident()} {message}\n')
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            pass

    def activate(self):
        if self.window and is_window(self.window.hwnd):
            bind(U, 'PostMessageW', W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)(self.window.hwnd, 0x8004, 0, 0)
            self.startup_log('Requested window activation')
        elif self.error:
            raise RuntimeError(self.error)

    def submit(self, work):
        self.tasks.put(work)
        bind(U, 'PostMessageW', W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)(self.hwnd, 0x8001, 0, 0)

    def dispatch(self, hwnd, message, wparam, lparam):
        if message == 0x8001:
            try:
                if threading.get_ident() != self.main_ident:
                    raise RuntimeError('ZBrush conversion must execute on its original thread')
                if not self.tasks.empty():
                    self.tasks.get()()
            except Exception:
                self.error = traceback.format_exc()
                if self.window:
                    self.window.notify('status', self.error)
                    self.window.notify('finished', '')
            return 0
        if message == 0x8003:
            destroy(hwnd)
            return 0
        return default(hwnd, message, wparam, lparam)

    def ui(self, converter, zbc, settings, save_settings, overwrite):
        try:
            self.startup_log('Window thread entered')
            self.window = FolderWindow(converter, zbc, settings, save_settings, overwrite, submit=self.submit)
            show(self.window.hwnd, 5)
            self.startup_log(f'Window shown hwnd={self.window.hwnd}')
            self.ready.set()
            self.window.run()
        except Exception:
            self.error = traceback.format_exc()
            self.startup_log(self.error)
            self.ready.set()
            from pathlib import Path
            path = Path(__file__).with_name('standalone_ui_error.log')
            path.write_text(self.error, encoding='utf-8')
        finally:
            bind(U, 'PostMessageW', W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)(self.hwnd, 0x8003, 0, 0)
