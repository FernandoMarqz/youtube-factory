"""PNG validation shared by visual adapters and application orchestration."""

from io import BytesIO

from PIL import Image, UnidentifiedImageError

from youtube_factory.application.exceptions import VisualAssetValidationError


def validate_png(image_bytes: bytes) -> tuple[int, int]:
    """Return actual dimensions after fully validating a non-empty PNG image."""
    if not image_bytes:
        raise VisualAssetValidationError("visual image is empty")
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            if image.format != "PNG":
                raise VisualAssetValidationError("visual image must use PNG format")
            width, height = image.size
            if width <= 0 or height <= 0:
                raise VisualAssetValidationError("visual image dimensions must be positive")
            image.verify()
    except VisualAssetValidationError:
        raise
    except (OSError, UnidentifiedImageError) as error:
        raise VisualAssetValidationError("visual image is not a valid PNG") from error
    return width, height
