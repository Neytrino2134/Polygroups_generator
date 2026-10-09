"""In-process flat cyan interface; mesh operations remain in existing operators."""


def register():
    from . import lifecycle
    lifecycle.register()


def unregister():
    from . import lifecycle
    lifecycle.unregister()
