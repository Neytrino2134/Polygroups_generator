"""Rounded native clipping regions for the borderless Windows UI."""
import sys


def round_widget(widget, radius=8, *, window=False):
    if sys.platform != 'win32':
        return
    import ctypes
    from ctypes import wintypes

    user = ctypes.WinDLL('user32', use_last_error=True)
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
    gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
    gdi.CreateRoundRectRgn.restype = wintypes.HANDLE
    gdi.DeleteObject.argtypes = [wintypes.HANDLE]
    previous = None

    def update(event=None):
        nonlocal previous
        if event is not None and event.widget is not widget:
            return
        if not widget.winfo_exists():
            return
        handle = widget.winfo_id()
        if window:
            handle = user.GetAncestor(handle, 2)  # Tk's native top-level wrapper.
        rect = wintypes.RECT()
        if not user.GetWindowRect(handle, ctypes.byref(rect)):
            return
        width, height = rect.right-rect.left, rect.bottom-rect.top
        if width < 2 or height < 2 or previous == (handle, width, height):
            return
        diameter = min(radius * 2, width, height)
        region = gdi.CreateRoundRectRgn(0, 0, width+1, height+1, diameter, diameter)
        if not region:
            return
        # Windows takes ownership after a successful SetWindowRgn.
        if user.SetWindowRgn(handle, region, True):
            previous = (handle, width, height)
        else:
            gdi.DeleteObject(region)

    widget.bind('<Configure>', update, add='+')
    widget.bind('<Map>', update, add='+')
