"""Import manifest: one record per scanned file, kept beside the working blend, read by Resume Work.

Every file of the import folder gets an index (the order of its folder, then its name; folders such as
01, 02, ... 10 sort by number) and a path relative to the blend. Its status tells Resume Work where to go
on: ``completed`` / ``failed`` files are done, ``in_progress`` / ``interrupted`` / ``pending`` start again.
"""
import json
import os
import re
import tempfile
import time

MANIFEST_SUFFIX = "_import_manifest.json"
DONE_STATUSES = frozenset({"completed", "failed"})
COLLECTION_NUMBER = re.compile(r"^Generated\.(\d+)$", re.IGNORECASE)


def manifest_path(blend_path):
    stem = os.path.splitext(os.path.basename(blend_path))[0]
    return os.path.join(os.path.dirname(os.path.abspath(blend_path)), stem + MANIFEST_SUFFIX)


def relative_path(blend_path, path):
    """Path relative to the blend with forward slashes; absolute when no relative path exists (other drive)."""
    try:
        return os.path.relpath(path, os.path.dirname(os.path.abspath(blend_path))).replace("\\", "/")
    except ValueError:
        return os.path.abspath(path).replace("\\", "/")


def absolute_path(blend_path, relative):
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(blend_path)), relative))


def path_key(path):
    return os.path.normcase(os.path.realpath(path))


def collection_number(name):
    match = COLLECTION_NUMBER.fullmatch(name or "")
    return int(match.group(1)) if match else None


def folder_of(root, path):
    """First folder below the import root that holds the file ('' when it lies in the root itself)."""
    parts = os.path.relpath(path, root).replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else ""


class ImportManifest:
    def __init__(self, blend_path, root, entries):
        self.blend_path = blend_path
        self.root = root
        self.entries = entries
        self.path = manifest_path(blend_path)

    @classmethod
    def build(cls, blend_path, root, files, previous=None):
        """Entries for ``files`` in their given order; statuses carry over from ``previous`` by file."""
        known = {path_key(absolute_path(blend_path, e["file"])): e for e in previous.entries} if previous else {}
        entries = []
        for index, path in enumerate(files, 1):
            old = known.get(path_key(path), {})
            entries.append({
                "index": index,
                "folder": folder_of(root, path) if root else "",
                "file": relative_path(blend_path, path),
                "status": old.get("status", "pending"),
                "collection": old.get("collection", ""),
                "output": old.get("output", ""),
                "started": old.get("started"),
                "finished": old.get("finished"),
                "error": old.get("error", ""),
            })
        return cls(blend_path, root, entries)

    @classmethod
    def load(cls, blend_path):
        """The manifest beside the blend, or None when it is missing or unreadable."""
        try:
            with open(manifest_path(blend_path), "r", encoding="utf-8") as handle:
                data = json.load(handle)
            entries = [dict(entry) for entry in data["files"]]
            for entry in entries:
                entry["file"], entry["status"]
            return cls(blend_path, data.get("root", ""), entries)
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save(self):
        data = {"version": 1, "blend": os.path.basename(self.blend_path), "root": self.root,
                "updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "summary": self.counts(), "files": self.entries}
        folder = os.path.dirname(self.path)
        descriptor, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=1, ensure_ascii=False)
            os.replace(temporary, self.path)
        except OSError:
            if os.path.exists(temporary):
                os.remove(temporary)
            raise

    def counts(self):
        counts = {}
        for entry in self.entries:
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        return counts

    def entry_for(self, path):
        key = path_key(path)
        for entry in self.entries:
            if path_key(absolute_path(self.blend_path, entry["file"])) == key:
                return entry
        return None

    def update(self, path, **fields):
        """Change one file's record and write the manifest; a write error never stops the import."""
        entry = self.entry_for(path)
        if entry is None:
            return None
        entry.update(fields)
        try:
            self.save()
        except OSError:
            pass
        return entry


_COUNTS_CACHE = {}


def cached_counts(blend_path):
    """Status counts of the manifest beside the blend (None without one); cached by modification time."""
    if not blend_path:
        return None
    path = manifest_path(blend_path)
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return None
    cached = _COUNTS_CACHE.get(path)
    if cached is None or cached[0] != stamp:
        manifest = ImportManifest.load(blend_path)
        cached = (stamp, manifest.counts() if manifest else None)
        _COUNTS_CACHE[path] = cached
    return cached[1]


class ResumePlan:
    def __init__(self):
        self.files = []        # absolute paths still to import, in manifest order
        self.wipe = []         # Generated.N collections of unfinished files that are removed first
        self.notes = []        # human readable decisions for the log
        self.done = 0


def plan_resume(manifest, files, scene_numbers, saved_numbers):
    """Decide which files Resume Work imports.

    A file is done when its record is ``completed`` / ``failed`` and its Generated.N collection is in the
    open blend; when separate files are in use (any ``_Generated_NNN.blend`` exists) the file must exist too.
    Everything else (no record, in process, interrupted, or a record without its collection / file)
    starts again from scratch.
    """
    plan = ResumePlan()
    wanted = {path_key(path): path for path in files}
    separate = bool(saved_numbers)
    for entry in manifest.entries:
        path = wanted.get(path_key(absolute_path(manifest.blend_path, entry["file"])))
        if path is None:
            continue
        number = collection_number(entry.get("collection"))
        label = f"{entry['index']}. {entry['file']}"
        if entry["status"] in DONE_STATUSES:
            missing = []
            if number is None or number not in scene_numbers:
                missing.append(f"Generated.{number:03d} collection" if number else "collection record")
            if separate and (number is None or number not in saved_numbers):
                missing.append(f"Generated_{number:03d}.blend file" if number else "saved file")
            if not missing:
                plan.done += 1
                continue
            plan.notes.append(f"{label}: {' and '.join(missing)} missing, imported again")
        elif entry["status"] != "pending":
            plan.notes.append(f"{label}: {entry['status']}, restarts from the beginning")
        plan.files.append(path)
        if number is not None and number in scene_numbers and entry["status"] != "pending":
            plan.wipe.append(entry["collection"])
    # Files the manifest does not know yet follow the known ones.
    known = {path_key(absolute_path(manifest.blend_path, e["file"])) for e in manifest.entries}
    plan.files.extend(path for path in files if path_key(path) not in known)
    return plan
