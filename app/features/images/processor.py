from pathlib import Path
from PIL import Image
import asyncio


SUPPORTED_IMAGE_FORMATS = {
    "webp": {"extension": ".webp"},
    "png": {"extension": ".png"},
    "jpg": {"extension": ".jpg"},
    "jpeg": {"extension": ".jpg"},
    "gif": {"extension": ".gif"},
    "bmp": {"extension": ".bmp"},
    "tiff": {"extension": ".tiff"},
    "avif": {"extension": ".avif"},
}


async def convert_image(
    input_path: str,
    output_path: str,
    format: str = "webp",
    width: int | None = None,
    height: int | None = None,
    quality: int | None = None,
) -> None:
    """
    Convert image to another format with optional resize and quality settings.
    """
    format = format.lower()
    if format not in SUPPORTED_IMAGE_FORMATS:
        raise ValueError(f"Unsupported image format: {format}")

    if not Path(input_path).exists():
        raise FileNotFoundError(f"Image file not found: {input_path}")

    def _convert():
        with Image.open(input_path) as img:
            # Convert RGBA to RGB for formats that don't support transparency
            if format in ("jpg", "jpeg") and img.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background
            elif format in ("webp", "png") and img.mode not in ("RGBA", "RGB", "L"):
                img = img.convert("RGBA")

            # Resize if width/height specified
            if width or height:
                original_width, original_height = img.size
                if width and height:
                    new_width, new_height = width, height
                elif width:
                    ratio = width / original_width
                    new_width, new_height = width, int(original_height * ratio)
                else:
                    ratio = height / original_height
                    new_width, new_height = int(original_width * ratio), height
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Save with quality setting
            save_kwargs = {}
            if quality is not None:
                save_kwargs["quality"] = quality
                if format == "webp":
                    save_kwargs["method"] = 6

            img.save(output_path, format=format.upper() if format != "jpg" else "JPEG", **save_kwargs)

    await asyncio.to_thread(_convert)


async def compress_image(
    input_path: str,
    output_path: str,
    quality: int = 80,
    max_width: int | None = None,
    max_height: int | None = None,
) -> dict:
    """
    Compress image by reducing quality and optionally resizing.
    """
    if not Path(input_path).exists():
        raise FileNotFoundError(f"Image file not found: {input_path}")

    def _compress():
        with Image.open(input_path) as img:
            original_size = Path(input_path).stat().st_size
            original_width, original_height = img.size

            # Resize if max dimensions specified
            if max_width or max_height:
                if max_width and max_height:
                    ratio = min(max_width / original_width, max_height / original_height)
                elif max_width:
                    ratio = max_width / original_width
                else:
                    ratio = max_height / original_height

                if ratio < 1:
                    new_width = int(original_width * ratio)
                    new_height = int(original_height * ratio)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Handle transparency for JPEG
            if img.mode in ("RGBA", "LA", "P"):
                if img.mode == "P":
                    img = img.convert("RGBA")
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = background

            save_kwargs = {"quality": quality, "optimize": True}
            if img.format == "WEBP":
                save_kwargs["method"] = 6

            img.save(output_path, **save_kwargs)
            processed_size = Path(output_path).stat().st_size

            return {
                "original_size": original_size,
                "processed_size": processed_size,
                "bytes_saved": original_size - processed_size,
                "percentage_saved": round((original_size - processed_size) / original_size * 100, 2) if original_size > 0 else 0,
            }

    return await asyncio.to_thread(_compress)