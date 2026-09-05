"""Independent themed tool window. Standard-library Tk; never imports bpy."""
import hashlib
import json
import os
from pathlib import Path
import socket
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, colorchooser, filedialog

if __package__:
    from .rounded import attach_to_owner, round_widget
else:
    from rounded import attach_to_owner, round_widget

DEFAULT_STYLE = dict(background='#171b24', surface='#232a37', foreground='#e5eaf3',
                     accent='#65c7b7', font_size=11, compact=False)


class DarkScrollbar(tk.Canvas):
    """Theme-independent scrollbar: no native Windows elements."""
    def __init__(self, parent, target, style):
        super().__init__(parent, width=9, bg=style['background'], highlightthickness=0, bd=0)
        self.target = target
        self.first, self.last = 0.0, 1.0
        self.thumb = self.create_rectangle(2, 0, 7, 0, fill=style['surface'], outline='')
        self.bind('<Configure>', lambda e:self.redraw())
        self.bind('<Enter>', lambda e:self.itemconfigure(self.thumb, fill=style['accent']))
        self.bind('<Leave>', lambda e:self.itemconfigure(self.thumb, fill=style['surface']))
        self.bind('<Button-1>', self.press)
        self.bind('<B1-Motion>', self.move)

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self.redraw()

    def redraw(self):
        height = max(1, self.winfo_height())
        self.thumb_height = min(height, max(24, height*(self.last-self.first)))
        travel = height-self.thumb_height
        self.thumb_top = travel*self.first/max(1e-9, 1-(self.last-self.first))
        self.coords(self.thumb, 2, self.thumb_top, 7, self.thumb_top+self.thumb_height)
        self.itemconfigure(self.thumb, state='hidden' if self.last-self.first >= .999 else 'normal')

    def press(self, event):
        if self.thumb_top <= event.y <= self.thumb_top+self.thumb_height:
            self.offset = event.y-self.thumb_top
        else:
            self.offset = self.thumb_height/2
            self.move(event)

    def move(self, event):
        travel = max(1, self.winfo_height()-self.thumb_height)
        position = (event.y-self.offset)/travel * (1-(self.last-self.first))
        self.target.yview_moveto(max(0, position))


class DarkDropdown(tk.Frame):
    """Borderless enum selector with an entirely themed popup list."""
    def __init__(self, parent, variable, values, command, style):
        super().__init__(parent, bg=style['surface'], highlightthickness=1,
                         highlightbackground=style['surface'])
        round_widget(self, 7)
        self.variable = variable
        self.values = list(values)
        self.command = command
        self.style = style
        self.popup = None
        self.state = 'normal'
        self.value_button = tk.Button(
            self, textvariable=variable, command=self.open, anchor='w', relief='flat', bd=0,
            bg=style['surface'], fg=style['foreground'], activebackground=style['surface'],
            activeforeground=style['accent'], disabledforeground='#777e8e', cursor='hand2',
            font=('Segoe UI', style['font_size']), padx=7, pady=4,
        )
        self.value_button.pack(side='left', fill='both', expand=True)
        self.arrow = tk.Button(
            self, text='▾', command=self.open, width=2, relief='flat', bd=0,
            bg=style['surface'], fg=style['accent'], activebackground=style['surface'],
            activeforeground=style['foreground'], disabledforeground='#777e8e', cursor='hand2',
            font=('Segoe UI', style['font_size']), padx=2, pady=4,
        )
        self.arrow.pack(side='right', fill='y')
        self.bind('<Destroy>', lambda event: self.close() if event.widget is self else None)

    def configure(self, cnf=None, **kwargs):
        state = kwargs.pop('state', None)
        if state is not None:
            self.state = state
            self.value_button.configure(state=state)
            self.arrow.configure(state=state)
            if state == 'disabled':
                self.close()
        return super().configure(cnf, **kwargs)

    config = configure

    def open(self):
        if self.state == 'disabled':
            return
        if self.popup is not None:
            self.close()
            return
        self.update_idletasks()
        style = self.style
        popup = tk.Toplevel(self)
        self.popup = popup
        popup.overrideredirect(True)
        round_widget(popup, 9, window=True)
        popup.configure(bg=style['accent'])
        popup.attributes('-topmost', bool(self.winfo_toplevel().attributes('-topmost')))
        popup.transient(self.winfo_toplevel())
        visible_rows = max(1, min(9, len(self.values)))
        line_height = max(24, style['font_size'] + 13)
        font = tkfont.Font(family='Segoe UI', size=style['font_size'])
        width = max(self.winfo_width(), max((font.measure(value) for value in self.values), default=80) + 35)
        height = visible_rows * line_height + 2
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        x = min(self.winfo_rootx(), max(0, screen_width - width))
        below = self.winfo_rooty() + self.winfo_height()
        y = below if below + height <= screen_height else max(0, self.winfo_rooty() - height)
        popup.geometry(
            f'{max(width, 120)}x{height}+{x}+{y}'
        )
        shell = tk.Frame(popup, bg=style['surface'], padx=1, pady=1)
        shell.pack(fill='both', expand=True, padx=1, pady=1)
        listing = tk.Listbox(
            shell, listvariable=tk.StringVar(value=self.values), exportselection=False,
            relief='flat', bd=0, highlightthickness=0, activestyle='none',
            bg=style['surface'], fg=style['foreground'],
            selectbackground=style['accent'], selectforeground=style['background'],
            font=('Segoe UI', style['font_size']), cursor='hand2',
        )
        scroll = DarkScrollbar(shell, listing, style)
        listing.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        listing.pack(side='left', fill='both', expand=True)
        try:
            index = self.values.index(self.variable.get())
            listing.selection_set(index)
            listing.see(index)
        except ValueError:
            pass
        listing.bind('<ButtonRelease-1>', lambda event: self.choose(listing))
        listing.bind('<Motion>', lambda event: self.highlight(listing, event.y))
        listing.bind('<Return>', lambda event: self.choose(listing))
        listing.bind('<Escape>', lambda event: self.close())
        listing.bind('<MouseWheel>', lambda event: listing.yview_scroll(-int(event.delta / 120), 'units'))
        popup.bind('<ButtonPress-1>', self.popup_pointer, add='+')
        popup.update_idletasks()
        popup.deiconify()
        popup.lift()
        popup.grab_set()
        listing.focus_force()
        # A borderless Toplevel emits a transient FocusOut while Windows assigns
        # focus. Arming later prevents the menu from closing on the opening click.
        popup.after(180, self.arm_focus_close)

    def arm_focus_close(self):
        if self.popup is not None:
            self.popup.bind('<FocusOut>', self.focus_out)

    def popup_pointer(self, event):
        popup = self.popup
        if popup is None:
            return None
        inside = (
            popup.winfo_rootx() <= event.x_root < popup.winfo_rootx() + popup.winfo_width()
            and popup.winfo_rooty() <= event.y_root < popup.winfo_rooty() + popup.winfo_height()
        )
        if not inside:
            self.close()
            return 'break'
        return None

    @staticmethod
    def highlight(listing, y):
        if listing.size():
            listing.selection_clear(0, 'end')
            listing.selection_set(listing.nearest(y))

    def focus_out(self, _event):
        if self.popup is not None:
            self.after_idle(self.close_if_unfocused)

    def close_if_unfocused(self):
        if self.popup is None:
            return
        focused = self.popup.focus_get()
        if focused is None or focused.winfo_toplevel() is not self.popup:
            self.close()

    def choose(self, listing):
        selected = listing.curselection()
        if not selected:
            return
        self.variable.set(self.values[selected[0]])
        self.command(self.variable.get())
        self.close()

    def close(self):
        popup, self.popup = self.popup, None
        if popup is not None:
            try:
                if popup.grab_current() is popup:
                    popup.grab_release()
                popup.destroy()
            except tk.TclError:
                pass


class PanelApp:
    def __init__(self, root, connection, config_dir, owner=0):
        self.root, self.connection = root, connection
        self.connection.setblocking(False)
        self.incoming, self.outgoing = b'', b''
        self.config_dir = Path(config_dir)
        self.model = None
        self.catalog, self.tabs, self.fields = [], [], {}
        self.buttons = {}
        self.tab_widgets = {}
        self.style = dict(DEFAULT_STYLE)
        self.hidden, self.order = [], []
        self.window_key = None
        self.loaded_group = None
        self.pending_group = None
        self.scroll_positions = {}
        self.collapsed, self.pinned = False, False
        self.last_signature = None
        self.connected = True
        root.title('AI Retopo · Tools')
        root.geometry('420x650')
        root.overrideredirect(True)
        round_widget(root, 16, window=True)
        root.minsize(300, 180)
        root.attributes('-topmost', False)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.build_shell()
        self.root.update_idletasks()
        self.attached_to_blender = attach_to_owner(self.root, owner)
        root.after(30, self.poll)

    def send(self, message):
        self.outgoing += (json.dumps(message, ensure_ascii=False) + '\n').encode('utf8')

    def button(self, parent, text, command, accent=False):
        button = tk.Button(parent, text=text, command=command, relief='flat', bd=0,
                         bg=self.style['accent'] if accent else self.style['surface'],
                         fg=self.style['background'] if accent else self.style['foreground'],
                         activebackground=self.style['accent'], cursor='hand2',
                         font=('Segoe UI', self.style['font_size']), padx=9, pady=5,
                         disabledforeground='#777e8e')
        round_widget(button, 8)
        return button

    def build_shell(self):
        for child in self.root.winfo_children():
            child.destroy()
        s = self.style
        self.root.configure(bg=s['background'])
        ttk_style = ttk.Style(self.root)
        ttk_style.theme_use('clam')
        ttk_style.configure('TProgressbar', background=s['accent'], troughcolor=s['surface'])
        ttk_style.configure('Vertical.TScrollbar', background=s['surface'], troughcolor=s['background'],
                            arrowcolor=s['foreground'], bordercolor=s['background'])
        self.header = tk.Frame(self.root, bg=s['surface'], padx=8, pady=4)
        self.header.pack(fill='x')
        self.caption = tk.Label(self.header, text='AI RETOPO', anchor='w', bg=s['surface'],
                                fg=s['accent'], font=('Segoe UI', s['font_size'], 'bold'))
        self.caption.pack(side='left', fill='x', expand=True)
        self.caption.bind('<ButtonPress-1>', self.start_drag)
        self.caption.bind('<B1-Motion>', self.drag)
        self.button(self.header, '−', self.collapse).pack(side='left')
        self.pin_button = self.button(self.header, '◆' if self.pinned else '◇', self.pin)
        self.pin_button.pack(side='left')
        self.button(self.header, '×', self.close).pack(side='left')
        self.body = tk.Frame(self.root, bg=s['background'])
        self.body.pack(fill='both', expand=True)
        self.tabbar = tk.Frame(self.body, bg=s['surface'], height=37)
        self.tabbar.pack(fill='x', padx=8, pady=(8, 0))
        self.tabbar.pack_propagate(False)
        self.tabs_canvas = tk.Canvas(self.tabbar, height=35, bg=s['surface'], highlightthickness=0, bd=0)
        self.tabs_canvas.pack(side='left', fill='both', expand=True)
        self.tabs_host = tk.Frame(self.tabs_canvas, bg=s['surface'])
        self.tabs_window = self.tabs_canvas.create_window((0, 0), window=self.tabs_host, anchor='nw')
        self.tabs_host.bind('<Configure>', lambda event: self.tabs_canvas.configure(scrollregion=self.tabs_canvas.bbox('all')))
        self.tabs_canvas.bind('<MouseWheel>', lambda event: self.tabs_canvas.xview_scroll(-int(event.delta / 120), 'units'))
        add_tab = tk.Label(self.tabbar, text='+', width=3, bg=s['surface'], fg=s['accent'],
                           font=('Segoe UI', s['font_size'] + 2, 'bold'), cursor='hand2')
        add_tab.pack(side='right', fill='y')
        add_tab.bind('<Button-1>', lambda event: self.add_group())
        self.context_label = tk.Label(self.body, text='Connecting to Blender…', anchor='w',
                                      bg=s['background'], fg=s['accent'], padx=12, pady=8)
        self.context_label.pack(fill='x')
        viewport = tk.Frame(self.body, bg=s['background'])
        viewport.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(viewport, bg=s['background'], highlightthickness=0)
        self.scroll = DarkScrollbar(viewport, self.canvas, s)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        self.content = tk.Frame(self.canvas, bg=s['background'])
        self.content_id = self.canvas.create_window((0, 0), window=self.content, anchor='nw')
        self.content.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.content_id, width=e.width))
        self.root.bind('<MouseWheel>', self.wheel)
        self.status = tk.Label(self.body, text='Ready', anchor='w', wraplength=370,
                               bg=s['surface'], fg=s['foreground'], padx=10, pady=7)
        self.status.pack(fill='x')
        grip = tk.Label(self.body, text='◢', bg=s['surface'], fg=s['accent'], cursor='size_nw_se')
        grip.place(relx=1, rely=1, anchor='se')
        grip.bind('<Button-1>', self.start_resize)
        grip.bind('<B1-Motion>', self.resize)
        self.fields = {}
        self.last_signature = None
        if self.model:
            self.render(self.model)

    def start_drag(self, event):
        self.drag_offset = (event.x_root-self.root.winfo_x(), event.y_root-self.root.winfo_y())

    def start_resize(self, event):
        self.resize_origin = (event.x_root, event.y_root, self.root.winfo_width(), self.root.winfo_height())

    def resize(self, event):
        x, y, width, height = self.resize_origin
        self.root.geometry(f'{max(300,width+event.x_root-x)}x{max(180,height+event.y_root-y)}')

    def drag(self, event):
        x, y = self.drag_offset
        self.root.geometry(f'{event.x_root-x:+d}{event.y_root-y:+d}')

    def wheel(self, event):
        if event.widget.winfo_toplevel() == self.root:
            self.canvas.yview_scroll(-int(event.delta/120), 'units')

    def pin(self):
        self.pinned = not self.pinned
        self.root.attributes('-topmost', self.pinned)
        self.pin_button.configure(text='◆' if self.pinned else '◇')

    def collapse(self):
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.expanded_geometry = self.root.geometry()
            self.body.pack_forget()
            self.root.minsize(300, 40)
            self.root.geometry(f'{self.root.winfo_width()}x44')
        else:
            self.body.pack(fill='both', expand=True)
            self.root.minsize(300, 180)
            self.root.geometry(self.expanded_geometry)

    def config_path(self):
        key = hashlib.sha256((self.window_key or self.loaded_group or 'default').encode()).hexdigest()[:16]
        return self.config_dir / (key + '.json')

    def save(self):
        if not self.loaded_group:
            return
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            path = self.config_path()
            temporary = path.with_suffix(f'.{os.getpid()}.tmp')
            temporary.write_text(json.dumps(dict(z_order_version=2, tabs=self.tabs, pinned=self.pinned,
                geometry=self.expanded_geometry if self.collapsed else self.root.geometry())), encoding='utf8')
            temporary.replace(path)
        except OSError as error:
            self.status.configure(text=f'Cannot save appearance: {error}')

    def load(self, group):
        self.save()
        if self.window_key is None:
            self.window_key = group
        self.loaded_group = group
        try:
            config = json.loads(self.config_path().read_text(encoding='utf8'))
        except (OSError, ValueError):
            config = {}
        self.style = dict(DEFAULT_STYLE)
        self.hidden, self.order = [], []
        if not self.tabs:
            self.tabs = config.get('tabs', [])
            self.pinned = bool(config.get('pinned', False)) if config.get('z_order_version') == 2 else False
            self.root.attributes('-topmost', self.pinned)
        self.build_shell()
        if config.get('geometry') and not self.collapsed:
            self.root.geometry(config['geometry'])

    @staticmethod
    def control_key(item):
        return item.get('key', item['kind'] + ':' + item.get('text', '') + ':' + item['id'])

    def action(self, item, value=None):
        if self.connected and self.model:
            self.send(dict(type='action', id=item['id'], value=value, revision=self.model['revision']))
            self.status.configure(text='Applying…')

    def property_value(self, item, variable):
        try:
            value = variable.get()
            if item.get('subtype') in {'COLOR', 'COLOR_GAMMA'}:
                raw = value.lstrip('#')
                if len(raw) not in (6, 8):
                    raise ValueError('Use #RRGGBB or #RRGGBBAA')
                value = [int(raw[i:i+2],16)/255 for i in range(0,len(raw),2)]
                if len(item['value'])==4 and len(value)==3:
                    value.append(item['value'][3])
                value = value[:len(item['value'])]
            elif isinstance(item['value'], list):
                value = json.loads(value)
            elif item['type'] == 'INT':
                value = int(value)
            elif item['type'] == 'FLOAT':
                value = float(value)
            if item['type'] in {'INT', 'FLOAT'} and not isinstance(value, list):
                value = max(item['min'], min(item['max'], value))
            self.action(item, value)
            self.root.focus_set()
        except (ValueError, TypeError, tk.TclError) as error:
            self.status.configure(text=f'Invalid value: {error}')

    def render(self, model):
        self.model = model
        if self.loaded_group is None:
            self.load(model['group'])
            return
        switched = self.loaded_group != model['group']
        if switched:
            self.loaded_group = model['group']
            self.pending_group = None
            self.last_signature = None
        self.root.title('AI Retopo · ' + model['title'])
        self.caption.configure(text=model['title'])
        self.context_label.configure(text=model['context'])
        if not any(t['group'] == model['group'] for t in self.tabs):
            self.tabs.append({k:model[k] for k in ('section', 'group', 'title')})
        self.draw_tabs(model['group'])
        signature = (model['revision'], tuple(self.hidden), tuple(self.order))
        if signature == self.last_signature:
            for item in model['items']:
                if item['id'] in self.buttons:
                    self.buttons[item['id']].configure(state='normal' if item['enabled'] else 'disabled')
                field = self.fields.get(item['id'])
                if field:
                    widget, variable = field
                    if widget != self.root.focus_get():
                        value = item.get('value')
                        if item['type'] == 'ENUM' and not item.get('enum_flag'):
                            value = dict(item['options']).get(value, value)
                        elif isinstance(value, (list, float)):
                            value = self.display_value(item)
                        if str(variable.get()) != str(value):
                            variable.set(value)
                    widget.configure(state='normal' if item['enabled'] else 'disabled')
            return
        self.last_signature = signature
        for child in self.content.winfo_children():
            child.destroy()
        self.fields = {}
        self.buttons = {}
        items = sorted(model['items'], key=lambda i: self.order.index(self.control_key(i)) if self.control_key(i) in self.order else len(self.order)+int(i['id']))
        for item in items:
            if self.control_key(item) in self.hidden:
                continue
            self.render_item(item)
        if switched:
            self.after_content_layout(model['group'])

    def after_content_layout(self, group):
        def restore():
            if self.loaded_group == group:
                self.canvas.configure(scrollregion=self.canvas.bbox('all'))
                self.canvas.yview_moveto(self.scroll_positions.get(group, 0.0))
        self.root.after_idle(restore)

    def draw_tabs(self, active_group):
        for child in self.tabs_host.winfo_children():
            child.destroy()
        self.tab_widgets = {}
        s = self.style
        for tab in self.tabs:
            active = tab['group'] == active_group
            background = s['background'] if active else s['surface']
            cell = tk.Frame(self.tabs_host, bg=background)
            round_widget(cell, 7)
            cell.pack(side='left', fill='y')
            marker = tk.Frame(cell, bg=s['accent'] if active else s['surface'], height=2)
            marker.pack(fill='x')
            label = tk.Label(
                cell, text=tab['title'], bg=background,
                fg=s['accent'] if active else s['foreground'],
                activebackground=background, activeforeground=s['accent'],
                font=('Segoe UI', s['font_size'], 'bold' if active else 'normal'),
                padx=12, pady=7, cursor='arrow' if active else 'hand2',
            )
            label.pack(side='left', fill='both', expand=True)
            close_tab = tk.Label(
                cell, text='×', bg=background, fg='#777e8e',
                activebackground=background, activeforeground='#f17878',
                font=('Segoe UI', s['font_size']), padx=7, pady=7, cursor='hand2',
            )
            close_tab.pack(side='right', fill='y')
            close_tab.bind('<Button-1>', lambda event, target=tab: self.close_tab(target))
            close_tab.bind('<Enter>', lambda event: event.widget.configure(fg='#f17878'))
            close_tab.bind('<Leave>', lambda event: event.widget.configure(fg='#777e8e'))
            if not active:
                label.bind('<Button-1>', lambda event, target=tab: self.select(target))
                label.bind('<Enter>', lambda event: event.widget.configure(fg=s['accent']))
                label.bind('<Leave>', lambda event: event.widget.configure(fg=s['foreground']))
            self.tab_widgets[tab['group']] = cell
        self.tabs_host.update_idletasks()
        active = self.tab_widgets.get(active_group)
        if active is not None:
            left = active.winfo_x()
            right = left + active.winfo_width()
            view_left = self.tabs_canvas.canvasx(0)
            view_right = view_left + self.tabs_canvas.winfo_width()
            total = max(1, self.tabs_host.winfo_reqwidth())
            if left < view_left:
                self.tabs_canvas.xview_moveto(left / total)
            elif right > view_right:
                self.tabs_canvas.xview_moveto(max(0, (right - self.tabs_canvas.winfo_width()) / total))

    def close_tab(self, tab):
        index = next((index for index, item in enumerate(self.tabs)
                      if item['group'] == tab['group']), None)
        if index is None:
            return
        was_active = tab['group'] in {self.loaded_group, self.pending_group}
        self.tabs.pop(index)
        if not self.tabs:
            self.close()
            return
        if was_active:
            target = self.tabs[min(index, len(self.tabs) - 1)]
            self.pending_group = None
            self.select(target)
        else:
            self.draw_tabs(self.pending_group or self.loaded_group)
        self.scroll_positions.pop(tab['group'], None)
        self.save()

    def render_item(self, item):
        s = self.style
        kind = item['kind']
        pad = 3 if s['compact'] else 6
        frame = tk.Frame(self.content, bg=s['background'], padx=10, pady=pad)
        frame.pack(fill='x')
        if kind == 'separator':
            tk.Frame(frame, bg=s['surface'], height=1).pack(fill='x')
            return
        if kind == 'button':
            button = self.button(frame, item['text'], lambda:self.action(item))
            button.configure(state='normal' if item['enabled'] else 'disabled', anchor='w', wraplength=340)
            button.pack(fill='x')
            self.buttons[item['id']] = button
            return
        if kind in {'label', 'progress'}:
            tk.Label(frame, text=item['text'], bg=s['background'], fg=s['foreground'],
                     anchor='w', wraplength=340, font=('Segoe UI', s['font_size'])).pack(fill='x')
            if kind == 'progress':
                ttk.Progressbar(frame, value=item['value']*100).pack(fill='x')
            return
        value = item['value']
        if item['type'] == 'BOOLEAN' and not isinstance(value, list):
            variable = tk.BooleanVar(value=value)
            widget = tk.Checkbutton(frame, text=item['text'], variable=variable,
                command=lambda:self.action(item, variable.get()), bg=s['background'], fg=s['foreground'],
                selectcolor=s['surface'], activebackground=s['background'], activeforeground=s['accent'],
                font=('Segoe UI', s['font_size']), anchor='w', wraplength=340)
        else:
            tk.Label(frame, text=item['text'], bg=s['background'], fg=s['foreground'], anchor='w',
                     font=('Segoe UI', s['font_size'])).pack(fill='x', pady=(0,3))
            variable = tk.StringVar(value=self.display_value(item))
            if item['type'] == 'ENUM' and not item.get('enum_flag'):
                choices = dict(item['options'])
                variable.set(choices.get(value, value))
                widget = DarkDropdown(
                    frame, variable, list(choices.values()),
                    lambda selected: self.action(
                        item, next((key for key, label in choices.items() if label == selected), selected),
                    ),
                    s,
                )
            else:
                widget = tk.Entry(frame, textvariable=variable, bg=s['surface'], fg=s['foreground'],
                                  insertbackground=s['accent'], relief='flat', font=('Segoe UI', s['font_size']),
                                  disabledbackground=s['surface'], disabledforeground='#777e8e',
                                  show='•' if item.get('subtype') == 'PASSWORD' else '')
                round_widget(widget, 6)
                widget.bind('<Return>', lambda e:self.property_value(item, variable))
                apply_button = self.button(frame, 'Apply', lambda:self.property_value(item, variable))
                apply_button.configure(state='normal' if item['enabled'] else 'disabled')
                apply_button.pack(side='right', padx=(4,0))
                self.buttons[item['id']] = apply_button
                if item.get('subtype') in {'COLOR', 'COLOR_GAMMA'}:
                    def pick_color():
                        color = colorchooser.askcolor(variable.get()[:7], parent=self.root)[1]
                        if color:
                            variable.set(color)
                            self.property_value(item, variable)
                    self.button(frame, 'Color', pick_color).pack(side='right')
                if item.get('subtype') in {'FILE_PATH', 'DIR_PATH'}:
                    def browse():
                        picker = filedialog.askdirectory if item['subtype']=='DIR_PATH' else filedialog.askopenfilename
                        path = picker(parent=self.root)
                        if path:
                            variable.set(path)
                            self.property_value(item, variable)
                    self.button(frame, '…', browse).pack(side='right')
        widget.configure(state='normal' if item['enabled'] else 'disabled')
        widget.pack(fill='x', expand=True)
        self.fields[item['id']] = widget, variable

    @staticmethod
    def display_value(item):
        value = item['value']
        if item.get('subtype') in {'COLOR', 'COLOR_GAMMA'}:
            return '#' + ''.join(f'{max(0,min(255,round(channel*255))):02x}' for channel in value)
        if isinstance(value, float):
            return f'{value:.6g}'
        return json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value

    def select(self, group):
        if group['group'] == self.loaded_group or group['group'] == self.pending_group:
            return
        self.scroll_positions[self.loaded_group] = self.canvas.yview()[0]
        self.pending_group = group['group']
        self.draw_tabs(group['group'])
        self.caption.configure(text=group['title'])
        self.status.configure(text='Loading group…')
        self.send(dict(type='select', section=group['section'], group=group['group']))

    def add_group(self):
        dialog = tk.Toplevel(self.root)
        dialog.title('Add a tool group')
        dialog.attributes('-topmost', self.pinned)
        choices = tk.Listbox(dialog, width=60, height=24, exportselection=False)
        choices.pack(fill='both', expand=True, padx=8, pady=8)
        for group in self.catalog:
            choices.insert('end', group['section'].replace('VIEW3D_PT_', '') + ' / ' + group['title'])
        def add():
            if choices.curselection():
                self.select(self.catalog[choices.curselection()[0]])
                dialog.destroy()
        ttk.Button(dialog, text='Add tab', command=add).pack(pady=8)
        choices.bind('<Double-Button-1>', lambda e:add())


    def poll(self):
        try:
            if self.outgoing:
                try:
                    sent = self.connection.send(self.outgoing)
                    self.outgoing = self.outgoing[sent:]
                except BlockingIOError:
                    pass
            try:
                data = self.connection.recv(65536)
                if not data:
                    self.close()
                    return
                self.incoming += data
            except BlockingIOError:
                pass
            if len(self.incoming) > 2*1024*1024:
                raise ValueError('Panel response too large')
            while b'\n' in self.incoming:
                line, self.incoming = self.incoming.split(b'\n', 1)
                message = json.loads(line)
                if message['type'] == 'catalog':
                    self.catalog = message['groups']
                elif message['type'] == 'model':
                    self.render(message)
                elif message['type'] == 'result':
                    self.status.configure(text=message['text'])
        except (OSError, ValueError) as error:
            self.connected = False
            self.status.configure(text=f'Disconnected: {error}')
            return
        self.root.after(30, self.poll)

    def close(self):
        self.save()
        self.connection.close()
        self.root.destroy()


def main():
    connection = socket.create_connection(('127.0.0.1', int(os.environ['AIRETOPO_PANEL_PORT'])), timeout=10)
    root = tk.Tk()
    app = PanelApp(root, connection, os.environ['AIRETOPO_PANEL_CONFIG'],
                   int(os.environ.get('AIRETOPO_BLENDER_OWNER', '0')))
    app.send(dict(token=os.environ.pop('AIRETOPO_PANEL_TOKEN')))
    root.mainloop()


if __name__ == '__main__':
    main()
