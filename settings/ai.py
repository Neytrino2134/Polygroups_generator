"""Ai workflow RNA property groups."""
from .callbacks import (
    _prompt_collection_items,
    _prompt_file_items,
    bpy,
)


class AIRETOPO_PG_ai_generation_settings(bpy.types.PropertyGroup):
    show_prompt_library_settings: bpy.props.BoolProperty(
        name="Prompt Library",
        default=False,
    )
    prompt_library_collection: bpy.props.EnumProperty(
        name="Collection",
        description="Prompt library collection",
        items=_prompt_collection_items,
    )
    prompt_library_prompt: bpy.props.EnumProperty(
        name="Prompt",
        description="Prompt text file from the selected collection",
        items=_prompt_file_items,
    )
    prompt_library_status: bpy.props.StringProperty(
        name="Prompt Library Status",
        default="",
    )
    show_openai_image_settings: bpy.props.BoolProperty(
        name="OpenAI Image",
        default=False,
    )
    show_google_image_settings: bpy.props.BoolProperty(
        name="Google Image",
        default=False,
    )
    prompt: bpy.props.StringProperty(
        name="Prompt",
        description="Prompt for OpenAI image generation",
        default="",
        options={"TEXTEDIT_UPDATE"},
    )
    model: bpy.props.EnumProperty(
        name="Model",
        description="OpenAI image generation model",
        items=(
            ("gpt-image-2", "gpt-image-2", "State-of-the-art image generation model"),
            ("gpt-image-1", "gpt-image-1", "High quality image generation model"),
            ("gpt-image-1-mini", "gpt-image-1-mini", "Faster and lower cost image generation model"),
        ),
        default="gpt-image-1",
    )
    size: bpy.props.EnumProperty(
        name="Size",
        description="Generated image size",
        items=(
            ("1024x1024", "1024 x 1024", "Square image"),
            ("1024x1536", "1024 x 1536", "Portrait image"),
            ("1536x1024", "1536 x 1024", "Landscape image"),
        ),
        default="1024x1024",
    )
    quality: bpy.props.EnumProperty(
        name="Quality",
        description="Generated image quality",
        items=(
            ("auto", "Auto", "Let the API choose the quality"),
            ("low", "Low", "Lower quality and faster generation"),
            ("medium", "Medium", "Balanced quality"),
            ("high", "High", "Higher quality"),
        ),
        default="auto",
    )
    output_format: bpy.props.EnumProperty(
        name="Output Format",
        description="Generated image file format",
        items=(
            ("png", "PNG", "Save generated images as PNG"),
            ("jpeg", "JPEG", "Save generated images as JPEG"),
            ("webp", "WebP", "Save generated images as WebP"),
        ),
        default="png",
    )
    input_image_name: bpy.props.StringProperty(
        name="Input Image",
        description="Optional Blender image to send with the prompt as editing context",
        default="",
    )
    is_generating: bpy.props.BoolProperty(
        name="Generating",
        default=False,
    )
    last_status: bpy.props.StringProperty(
        name="Status",
        default="",
    )
    last_image_name: bpy.props.StringProperty(
        name="Last Image",
        default="",
    )
    last_image_path: bpy.props.StringProperty(
        name="Last Image Path",
        default="",
        subtype="FILE_PATH",
    )


class AIRETOPO_PG_google_image_settings(bpy.types.PropertyGroup):
    prompt: bpy.props.StringProperty(
        name="Prompt",
        description="Prompt for Google Gemini image generation",
        default="",
        options={"TEXTEDIT_UPDATE"},
    )
    model: bpy.props.EnumProperty(
        name="Model",
        description="Google Gemini image generation model",
        items=(
            ("gemini-3.1-flash-image", "Gemini 3.1 Flash Image", "Nano Banana 2 general image generation model"),
            ("gemini-3.1-flash-lite-image", "Gemini 3.1 Flash Lite Image", "Nano Banana 2 Lite fast and low-cost image model"),
            ("gemini-3-pro-image", "Gemini 3 Pro Image", "Nano Banana Pro premium image generation model"),
            ("gemini-2.5-flash-image", "Gemini 2.5 Flash Image", "Legacy Nano Banana image model"),
        ),
        default="gemini-3.1-flash-image",
    )
    aspect_ratio: bpy.props.EnumProperty(
        name="Aspect Ratio",
        description="Generated image aspect ratio",
        items=(
            ("1:1", "1:1", "Square"),
            ("2:3", "2:3", "Portrait"),
            ("3:2", "3:2", "Landscape"),
            ("3:4", "3:4", "Portrait"),
            ("4:3", "4:3", "Landscape"),
            ("4:5", "4:5", "Portrait"),
            ("5:4", "5:4", "Landscape"),
            ("9:16", "9:16", "Vertical"),
            ("16:9", "16:9", "Widescreen"),
            ("21:9", "21:9", "Ultrawide"),
        ),
        default="1:1",
    )
    image_size: bpy.props.EnumProperty(
        name="Image Size",
        description="Generated image size class",
        items=(
            ("1K", "1K", "Standard image size"),
            ("2K", "2K", "High image size"),
            ("4K", "4K", "Ultra image size"),
        ),
        default="1K",
    )
    output_format: bpy.props.EnumProperty(
        name="Save Format",
        description="File format used when saving generated Google images from Blender",
        items=(
            ("png", "PNG", "Save generated images as PNG"),
            ("jpeg", "JPEG", "Save generated images as JPEG"),
            ("webp", "WebP", "Save generated images as WebP"),
        ),
        default="png",
    )
    input_image_name: bpy.props.StringProperty(
        name="Input Image",
        description="Optional Blender image to send with the prompt as editing context",
        default="",
    )
    is_generating: bpy.props.BoolProperty(
        name="Generating",
        default=False,
    )
    last_status: bpy.props.StringProperty(
        name="Status",
        default="",
    )
    last_image_name: bpy.props.StringProperty(
        name="Last Image",
        default="",
    )
    last_image_path: bpy.props.StringProperty(
        name="Last Image Path",
        default="",
        subtype="FILE_PATH",
    )
