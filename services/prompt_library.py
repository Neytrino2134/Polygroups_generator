import os
import subprocess
import sys

try:
    import bpy
except ImportError:
    bpy = None


PROMPT_LIBRARY_ENV = "AIRETOPO_PROMPT_LIBRARY_DIR"
PROMPT_LIBRARY_FOLDER = os.path.join("ai_retopo_toolkit", "prompts")

SAMPLE_PROMPTS = {
    "Texture References": {
        "pbr_basecolor_reference.txt": (
            "Create a clean PBR base color reference for a retopologized AI-generated 3D mesh.\n"
            "Preserve the original object identity and material intent.\n"
            "Avoid text, labels, logos, borders, and watermarks.\n"
            "Use physically plausible color variation and subtle surface detail.\n"
        ),
        "normal_detail_reference.txt": (
            "Create a normal-map style detail reference for the selected object material.\n"
            "Emphasize believable medium and small scale surface relief.\n"
            "Avoid changing the object silhouette or adding unrelated decorative motifs.\n"
        ),
    },
    "Retopo Concepts": {
        "clean_material_groups.txt": (
            "Generate a clear material-group reference for retopology planning.\n"
            "Separate visually distinct surfaces with readable boundaries.\n"
            "Keep the result useful for polygroup, seam, and baking decisions.\n"
        ),
    },
}


def prompt_library_root():
    override = os.environ.get(PROMPT_LIBRARY_ENV, "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))

    if bpy is not None:
        return bpy.utils.user_resource("CONFIG", path=PROMPT_LIBRARY_FOLDER, create=True)

    return os.path.join(os.path.expanduser("~"), "AI Retopo Toolkit", "prompts")


def ensure_prompt_library():
    root = prompt_library_root()
    os.makedirs(root, exist_ok=True)

    for collection_name, prompts in SAMPLE_PROMPTS.items():
        collection_path = _safe_child(root, collection_name)
        os.makedirs(collection_path, exist_ok=True)

        for prompt_file, prompt_text in prompts.items():
            filepath = _safe_child(collection_path, prompt_file)
            if os.path.exists(filepath):
                continue
            with open(filepath, "w", encoding="utf-8") as file:
                file.write(prompt_text)

    return root


def collection_names():
    root = ensure_prompt_library()
    names = [
        item
        for item in os.listdir(root)
        if os.path.isdir(os.path.join(root, item))
    ]
    return sorted(names, key=str.casefold)


def prompt_names(collection_name):
    root = ensure_prompt_library()
    if not collection_name:
        collections = collection_names()
        collection_name = collections[0] if collections else ""

    if not collection_name:
        return []

    collection_path = _safe_child(root, collection_name)
    if not os.path.isdir(collection_path):
        return []

    names = [
        item
        for item in os.listdir(collection_path)
        if item.lower().endswith(".txt") and os.path.isfile(os.path.join(collection_path, item))
    ]
    return sorted(names, key=str.casefold)


def read_prompt(collection_name, prompt_file):
    if not collection_name or not prompt_file or prompt_file == "__NONE__":
        raise FileNotFoundError("Prompt file is not selected")

    root = ensure_prompt_library()
    filepath = _safe_child(root, collection_name, prompt_file)
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"Prompt file was not found: {prompt_file}")

    with open(filepath, "r", encoding="utf-8") as file:
        return file.read().strip()


def prompt_count():
    return sum(len(prompt_names(collection)) for collection in collection_names())


def open_prompt_library_folder():
    root = ensure_prompt_library()
    if os.name == "nt":
        os.startfile(root)
        return

    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, root])


def _safe_child(root, *parts):
    root_path = os.path.abspath(root)
    child_path = os.path.abspath(os.path.join(root_path, *parts))
    if child_path != root_path and not child_path.startswith(root_path + os.sep):
        raise ValueError("Path is outside the prompt library")
    return child_path
