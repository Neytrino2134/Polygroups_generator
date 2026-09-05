"""Run with a Python installation with Tkinter, after the Blender schema test."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import tkinter as tk
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from standalone_ui.client import PanelApp, DEFAULT_STYLE, DarkDropdown, DarkScrollbar

def run():
    root = tk.Tk()
    connection, peer = socket.socketpair()
    with tempfile.TemporaryDirectory() as config:
        app = PanelApp(root, connection, config)
        errors = []
        root.report_callback_exception = lambda *args: errors.append(args)
        schemas = json.loads((Path(tempfile.gettempdir())/'airetopo_schemas.json').read_text(encoding='utf8'))
        for index, schema in enumerate(schemas):
            model = dict(type='model', **schema['group'], items=schema['items'], revision=str(index), context='EDIT_MESH · Cube')
            app.render(model)
            root.update()
            app.render(model)
            root.update()
        assert not errors, errors
        # Return/Apply sends a typed value, not executable Python.
        app.render(dict(type='model', **schemas[5]['group'], items=schemas[5]['items'], revision='demo', context='OBJECT · Cube'))
        root.update()
        shell = app.body
        geometry = root.geometry()
        config_path = app.config_path()
        target_schema = schemas[4]
        app.select(target_schema['group'])
        root.update()
        assert app.pending_group == target_schema['group']['group']
        assert root.geometry() == geometry and app.body is shell
        app.render(dict(type='model', **target_schema['group'], items=target_schema['items'],
                        revision='switched', context='OBJECT · Cube'))
        root.update()
        assert app.loaded_group == target_schema['group']['group'] and app.pending_group is None
        assert root.geometry() == geometry and app.body is shell and app.config_path() == config_path
        assert app.tab_widgets[app.loaded_group].cget('background') == DEFAULT_STYLE['background']
        # Tabs have close controls; inactive removal stays in place, active removal selects a neighbor.
        tab_snapshot = list(app.tabs)
        app.tabs = [schemas[index]['group'] for index in (3, 4, 5)]
        app.draw_tabs(app.loaded_group)
        inactive_count = len(app.tabs)
        app.close_tab(app.tabs[0])
        assert len(app.tabs) == inactive_count - 1 and app.loaded_group == target_schema['group']['group']
        active = next(tab for tab in app.tabs if tab['group'] == app.loaded_group)
        app.close_tab(active)
        assert len(app.tabs) == 1 and app.pending_group == app.tabs[0]['group']
        neighbor = schemas[5]
        app.render(dict(type='model', **neighbor['group'], items=neighbor['items'],
                        revision='neighbor', context='OBJECT · Cube'))
        root.update()
        assert root.geometry() == geometry and app.body is shell
        app.tabs = tab_snapshot
        app.render(dict(type='model', **schemas[5]['group'], items=schemas[5]['items'], revision='demo', context='OBJECT · Cube'))
        root.update()
        item = next(i for i in app.model['items'] if i.get('type')=='FLOAT')
        widget, variable = app.fields[item['id']]
        variable.set('0.25')
        app.property_value(item, variable)
        assert json.loads(app.outgoing.splitlines()[-1])['value'] == .25
        app.save()
        assert 'style' not in json.loads(app.config_path().read_text())
        assert root.overrideredirect()
        assert isinstance(app.scroll, DarkScrollbar)
        saved = json.loads(app.config_path().read_text())
        saved.update(style={'accent':'#ffffff'}, hidden=['obsolete'], order=['obsolete'])
        app.config_path().write_text(json.dumps(saved))
        group = app.loaded_group
        app.loaded_group = None
        app.load(group)
        assert app.style == DEFAULT_STYLE and not app.hidden and not app.order
        enum_item = next(i for i in app.model['items'] if i.get('type') == 'ENUM')
        enum_widget, enum_variable = app.fields[enum_item['id']]
        assert isinstance(enum_widget, DarkDropdown)
        enum_widget.value_button.invoke()
        root.after(300, root.quit)
        root.mainloop()
        assert enum_widget.popup is not None and enum_widget.popup.overrideredirect()
        assert enum_widget.popup.grab_current() is enum_widget.popup
        listing = next(widget for widget in enum_widget.popup.winfo_children()[0].winfo_children()
                       if isinstance(widget, tk.Listbox))
        listing.selection_clear(0, 'end')
        listing.selection_set(min(1, listing.size() - 1))
        enum_widget.choose(listing)
        assert enum_widget.popup is None
        enum_message = json.loads(app.outgoing.splitlines()[-1])
        assert enum_message['type'] == 'action' and enum_message['value'] in dict(enum_item['options'])
        # Model refresh updates disabled controls without rebuilding focused fields.
        item['enabled'] = False
        app.render(app.model)
        assert str(app.fields[item['id']][0]['state']) == 'disabled'
        assert str(app.buttons[item['id']]['state']) == 'disabled'
        item['enabled'] = True
        app.render(app.model)
        app.pin()
        assert not root.attributes('-topmost')
        app.pin()
        assert root.attributes('-topmost')
        app.collapse()
        root.update()
        assert not app.body.winfo_ismapped()
        app.collapse()
        root.update()
        assert app.body.winfo_ismapped()
        width, height = root.winfo_width(), root.winfo_height()
        app.start_resize(SimpleNamespace(x_root=100, y_root=100))
        app.resize(SimpleNamespace(x_root=140, y_root=130))
        root.update()
        assert root.winfo_width()==width+40 and root.winfo_height()==height+30
        # Schema sweep adds tabs; test scrolling with a normal single-tab window.
        app.tabs = []
        app.render(app.model)
        tk.Frame(app.content, height=4000).pack(fill='x')
        root.update()
        app.scroll.press(SimpleNamespace(y=app.scroll.winfo_height()//2))
        root.update()
        assert app.canvas.yview()[0] > 0
        real_close = app.close
        closed = []
        app.close = lambda: closed.append(True)
        app.tabs = [schemas[5]['group']]
        app.loaded_group = app.tabs[0]['group']
        app.close_tab(app.tabs[0])
        assert closed and not app.tabs
        app.close = real_close
        assert not errors, errors
        app.close()
    peer.close()
    print(f'PASSED: {len(schemas)} groups, closable in-place tabs, geometry persistence, editing, custom dropdown, borderless window, resize, dark scroll, pin, collapse')

if __name__=='__main__':
    run()
