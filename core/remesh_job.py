"""Non-modal adapter for the installed Quad Remesher engine integration."""

import importlib
import math
import subprocess
import time
from types import SimpleNamespace

import bpy


def remesh_backend(context):
    if not hasattr(context.scene, "qremesher"):
        raise RuntimeError("Enable Quad Remesher before using Auto Remesh")
    operator_type = bpy.types.Operator.bl_rna_get_subclass_py("QREMESHER_OT_remesh")
    if operator_type is None:
        raise RuntimeError("Quad Remesher is not available")
    module = importlib.import_module(operator_type.__module__)
    if not all(callable(getattr(module, name, None)) for name in (
        "doRemeshing_Start", "doRemeshing_Finish",
    )):
        raise RuntimeError("This Quad Remesher version does not support queued remeshing")
    return module


class RemeshJob:
    def __init__(self, backend, report):
        self.backend = backend
        self.state = SimpleNamespace(
            report=report, remeshProcess=None, IsRemeshing=False,
            progressFilename=None, retopoFilename=None,
        )
        self.started = time.monotonic()
        self.exited = None

    def start(self, context):
        self.backend.doRemeshing_Start(self.state, context)
        if not self.state.IsRemeshing:
            raise RuntimeError("Quad Remesher could not start; check its installation and license")

    def poll(self):
        value, message = None, ""
        try:
            with open(self.state.progressFilename, encoding="utf-8") as stream:
                lines = stream.read().splitlines()
            value = float(lines[0])
            message = " ".join(lines[1:])
            if not math.isfinite(value):
                value = None
        except (OSError, ValueError, IndexError, TypeError):
            pass  # The engine may be in the middle of writing the file.
        if value == 2:
            return True, 1.0
        if value is not None and value < 0:
            raise RuntimeError(message or f"Quad Remesher failed ({value})")
        process = self.state.remeshProcess
        if process is not None and process.poll() is not None:
            if self.exited is None:
                self.exited = time.monotonic()
            if time.monotonic() - self.exited > 2:
                raise RuntimeError("Quad Remesher exited without a completed result")
        if value is None and time.monotonic() - self.started > 40:
            raise RuntimeError("Quad Remesher did not report progress within 40 seconds")
        return False, max(0.0, min(1.0, value or 0.0))

    def finish(self, context):
        self.backend.doRemeshing_Finish(self.state, context)

    def abort(self):
        process = self.state.remeshProcess
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
