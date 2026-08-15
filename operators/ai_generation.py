import os
import re
import tempfile
import threading
import time

import bpy

from ..services.openai_images import OpenAIImageError
from ..services.openai_images import generate_image_bytes
from ..services.gemini_images import GeminiImageError
from ..services.gemini_images import generate_image_bytes as generate_gemini_image_bytes


_RESULT_LOCK = threading.Lock()
_PENDING_RESULTS = []


def _safe_path_name(name):
    safe_name = re.sub(r'[<>:"/\\|?*]+', "_", name).strip(" .")
    return safe_name or "Scene"


def _extension_for_format(output_format):
    if output_format == "jpeg":
        return "jpg"
    return output_format


def _get_preferences(context):
    addon = context.preferences.addons.get(__package__.split(".")[0])
    if addon is None:
        return None
    return addon.preferences


def _settings_for_provider(scene, provider):
    if provider == "GOOGLE":
        return scene.airetopo_google_image_settings
    return scene.airetopo_ai_generation_settings


def _get_api_key(context, provider):
    preferences = _get_preferences(context)
    if preferences is None:
        return ""

    if provider == "GOOGLE":
        if preferences.use_env_gemini_api_key:
            env_key = os.environ.get("GEMINI_API_KEY", "")
            if env_key:
                return env_key
        return preferences.gemini_api_key

    if preferences.use_env_openai_api_key:
        env_key = os.environ.get("OPENAI_API_KEY", "")
        if env_key:
            return env_key

    return preferences.openai_api_key


def _queue_result(result):
    with _RESULT_LOCK:
        _PENDING_RESULTS.append(result)


def _pop_result():
    with _RESULT_LOCK:
        if not _PENDING_RESULTS:
            return None
        return _PENDING_RESULTS.pop(0)


def _open_image_in_editor(image):
    screen = getattr(bpy.context, "screen", None)
    if screen is None:
        return False

    for area in screen.areas:
        if area.type != "IMAGE_EDITOR":
            continue

        for space in area.spaces:
            if space.type == "IMAGE_EDITOR":
                space.image = image
                return True

    return False


def _load_generated_image(settings, filepath, image_name):
    existing_image = bpy.data.images.get(image_name)
    if existing_image is not None:
        bpy.data.images.remove(existing_image)

    image = bpy.data.images.load(filepath, check_existing=False)
    image.name = image_name
    settings.last_image_name = image.name
    settings.last_image_path = filepath
    _open_image_in_editor(image)


def _apply_pending_results():
    result = _pop_result()
    if result is None:
        for scene in bpy.data.scenes:
            openai_settings = getattr(scene, "airetopo_ai_generation_settings", None)
            google_settings = getattr(scene, "airetopo_google_image_settings", None)
            if openai_settings is not None and openai_settings.is_generating:
                return 0.25
            if google_settings is not None and google_settings.is_generating:
                return 0.25
        return None

    scene = bpy.data.scenes.get(result["scene_name"])
    if scene is None:
        return 0.1

    settings = _settings_for_provider(scene, result["provider"])
    settings.is_generating = False

    if result["ok"]:
        _load_generated_image(settings, result["filepath"], result["image_name"])
        settings.last_status = result["status"]
    else:
        settings.last_status = result["error"]

    return 0.1


def _ensure_result_timer():
    if not bpy.app.timers.is_registered(_apply_pending_results):
        bpy.app.timers.register(_apply_pending_results, first_interval=0.25)


def _openai_generation_worker(scene_name, api_key, prompt, model, size, quality, output_format):
    try:
        image_bytes = generate_image_bytes(
            api_key=api_key,
            prompt=prompt,
            model=model,
            size=size,
            quality=quality,
            output_format=output_format,
        )
        extension = _extension_for_format(output_format)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        image_name = f"AI_Generated_{timestamp}.{extension}"
        filepath = os.path.join(tempfile.gettempdir(), image_name)

        with open(filepath, "wb") as image_file:
            image_file.write(image_bytes)

        _queue_result(
            {
                "ok": True,
                "provider": "OPENAI",
                "scene_name": scene_name,
                "filepath": filepath,
                "image_name": image_name,
                "status": f"Generated image: {image_name}",
            },
        )
    except OpenAIImageError as error:
        _queue_result(
            {
                "ok": False,
                "provider": "OPENAI",
                "scene_name": scene_name,
                "error": str(error),
            },
        )
    except Exception as error:
        _queue_result(
            {
                "ok": False,
                "provider": "OPENAI",
                "scene_name": scene_name,
                "error": f"Image generation failed: {error}",
            },
        )


def _google_generation_worker(scene_name, api_key, prompt, model, aspect_ratio, image_size):
    try:
        image_bytes = generate_gemini_image_bytes(
            api_key=api_key,
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
        )
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        image_name = f"Google_Generated_{timestamp}.png"
        filepath = os.path.join(tempfile.gettempdir(), image_name)

        with open(filepath, "wb") as image_file:
            image_file.write(image_bytes)

        _queue_result(
            {
                "ok": True,
                "provider": "GOOGLE",
                "scene_name": scene_name,
                "filepath": filepath,
                "image_name": image_name,
                "status": f"Generated image: {image_name}",
            },
        )
    except GeminiImageError as error:
        _queue_result(
            {
                "ok": False,
                "provider": "GOOGLE",
                "scene_name": scene_name,
                "error": str(error),
            },
        )
    except Exception as error:
        _queue_result(
            {
                "ok": False,
                "provider": "GOOGLE",
                "scene_name": scene_name,
                "error": f"Image generation failed: {error}",
            },
        )


class OBJECT_OT_airetopo_generate_openai_image(bpy.types.Operator):
    bl_idname = "object.airetopo_generate_openai_image"
    bl_label = "Generate OpenAI Image"
    bl_description = "Generate an image with the OpenAI Images API"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.airetopo_ai_generation_settings
        prompt = settings.prompt.strip()
        if not prompt:
            self.report({"WARNING"}, "Prompt is empty")
            return {"CANCELLED"}

        if settings.is_generating:
            self.report({"WARNING"}, "Image generation is already running")
            return {"CANCELLED"}

        api_key = _get_api_key(context, "OPENAI")
        if not api_key:
            settings.last_status = "OpenAI API key is missing"
            self.report({"ERROR"}, settings.last_status)
            return {"CANCELLED"}

        settings.is_generating = True
        settings.last_status = "Generating image..."
        thread = threading.Thread(
            target=_openai_generation_worker,
            args=(
                context.scene.name,
                api_key,
                prompt,
                settings.model,
                settings.size,
                settings.quality,
                settings.output_format,
            ),
            daemon=True,
        )
        thread.start()
        _ensure_result_timer()

        self.report({"INFO"}, "Image generation started")
        return {"FINISHED"}


class OBJECT_OT_airetopo_generate_google_image(bpy.types.Operator):
    bl_idname = "object.airetopo_generate_google_image"
    bl_label = "Generate Google Image"
    bl_description = "Generate an image with the Google Gemini API"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.scene.airetopo_google_image_settings
        prompt = settings.prompt.strip()
        if not prompt:
            self.report({"WARNING"}, "Prompt is empty")
            return {"CANCELLED"}

        if settings.is_generating:
            self.report({"WARNING"}, "Image generation is already running")
            return {"CANCELLED"}

        api_key = _get_api_key(context, "GOOGLE")
        if not api_key:
            settings.last_status = "Google Gemini API key is missing"
            self.report({"ERROR"}, settings.last_status)
            return {"CANCELLED"}

        settings.is_generating = True
        settings.last_status = "Generating image..."
        thread = threading.Thread(
            target=_google_generation_worker,
            args=(
                context.scene.name,
                api_key,
                prompt,
                settings.model,
                settings.aspect_ratio,
                settings.image_size,
            ),
            daemon=True,
        )
        thread.start()
        _ensure_result_timer()

        self.report({"INFO"}, "Image generation started")
        return {"FINISHED"}


class OBJECT_OT_airetopo_open_generated_image(bpy.types.Operator):
    bl_idname = "object.airetopo_open_generated_image"
    bl_label = "Open In Image Editor"
    bl_description = "Show the last generated image in an existing Image Editor area"
    bl_options = {"REGISTER"}

    provider: bpy.props.EnumProperty(
        items=(
            ("OPENAI", "OpenAI", "OpenAI generated image"),
            ("GOOGLE", "Google", "Google Gemini generated image"),
        ),
        default="OPENAI",
    )

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, "airetopo_ai_generation_settings")

    def execute(self, context):
        settings = _settings_for_provider(context.scene, self.provider)
        image = bpy.data.images.get(settings.last_image_name)
        if image is None and settings.last_image_path:
            image = bpy.data.images.load(settings.last_image_path, check_existing=True)

        if image is None:
            self.report({"WARNING"}, "Generated image was not found")
            return {"CANCELLED"}

        if not _open_image_in_editor(image):
            self.report({"WARNING"}, "Open an Image Editor area to display the image")
            return {"CANCELLED"}

        return {"FINISHED"}


class OBJECT_OT_airetopo_save_generated_image(bpy.types.Operator):
    bl_idname = "object.airetopo_save_generated_image"
    bl_label = "Save Image"
    bl_description = "Save the last generated image next to the blend file"
    bl_options = {"REGISTER"}

    provider: bpy.props.EnumProperty(
        items=(
            ("OPENAI", "OpenAI", "OpenAI generated image"),
            ("GOOGLE", "Google", "Google Gemini generated image"),
        ),
        default="OPENAI",
    )

    @classmethod
    def poll(cls, context):
        return hasattr(context.scene, "airetopo_ai_generation_settings")

    def execute(self, context):
        settings = _settings_for_provider(context.scene, self.provider)
        if not bpy.data.filepath:
            self.report({"ERROR"}, "Save the blend file first")
            return {"CANCELLED"}

        image = bpy.data.images.get(settings.last_image_name)
        if image is None and settings.last_image_path:
            image = bpy.data.images.load(settings.last_image_path, check_existing=True)

        if image is None:
            self.report({"WARNING"}, "Generated image was not found")
            return {"CANCELLED"}

        blend_dir = os.path.dirname(bpy.data.filepath)
        active_object = context.active_object
        folder_source_name = active_object.name if active_object else context.scene.name
        provider_folder = "Google" if self.provider == "GOOGLE" else "OpenAI"
        output_dir = os.path.join(
            blend_dir,
            "AI_Generations",
            provider_folder,
            _safe_path_name(folder_source_name),
        )
        os.makedirs(output_dir, exist_ok=True)

        extension = _extension_for_format(settings.output_format)
        file_prefix = "Google_Generated" if self.provider == "GOOGLE" else "OpenAI_Generated"
        index = 1
        while True:
            filepath = os.path.join(output_dir, f"{file_prefix}_{index:03d}.{extension}")
            if not os.path.exists(filepath):
                break
            index += 1

        original_filepath = image.filepath_raw
        original_format = image.file_format
        image.filepath_raw = filepath
        image.file_format = settings.output_format.upper() if settings.output_format != "jpeg" else "JPEG"
        image.save()
        image.filepath_raw = original_filepath
        image.file_format = original_format

        settings.last_image_path = filepath
        settings.last_status = f"Saved image: {filepath}"
        self.report({"INFO"}, settings.last_status)
        return {"FINISHED"}
