"""Inline field editing: staged values, explicit commit and rollback on Escape."""
import math


def edit_key(edit, event, clipboard):
    text = edit['text']
    cursor = edit['cursor']
    if event.value != 'PRESS':
        return 'wait'
    if event.type in {'RET', 'NUMPAD_ENTER'}:
        return 'commit'
    if event.type == 'ESC':
        return 'cancel'
    if event.ctrl and event.type == 'A':
        edit['all'] = True
        return 'wait'
    if event.ctrl and event.type in {'C', 'X'}:
        clipboard.clipboard = text
        if event.type == 'X':
            edit.update(text='', cursor=0, all=False)
        return 'wait'
    insert = clipboard.clipboard if event.ctrl and event.type == 'V' else event.unicode
    if event.type in {'LEFT_ARROW', 'RIGHT_ARROW', 'HOME', 'END'}:
        edit['all'] = False
        edit['cursor'] = (max(0,cursor-1) if event.type=='LEFT_ARROW' else
                          min(len(text),cursor+1) if event.type=='RIGHT_ARROW' else
                          0 if event.type=='HOME' else len(text))
    elif event.type == 'BACK_SPACE':
        edit['text'] = '' if edit['all'] else text[:max(0,cursor-1)]+text[cursor:]
        edit['cursor'] = 0 if edit['all'] else max(0,cursor-1)
        edit['all'] = False
    elif event.type == 'DEL':
        edit['text'] = '' if edit['all'] else text[:cursor]+text[cursor+1:]
        edit['all'] = False
    elif insert and not event.alt and (not event.ctrl or event.type == 'V'):
        if edit['all']:
            text, cursor = '', 0
        insert = insert.replace('\r','').replace('\n',' ')
        edit.update(text=text[:cursor]+insert+text[cursor:], cursor=cursor+len(insert), all=False)
    return 'wait'


def parsed_value(edit, node):
    if node['type'] == 'STRING':
        return edit['text']
    value = float(edit['text'].strip().replace(',', '.'))
    if not math.isfinite(value):
        raise ValueError('Enter a finite numeric value')
    value = max(node['min'], min(node['max'], value))
    return int(round(value)) if node['type'] == 'INT' else value
