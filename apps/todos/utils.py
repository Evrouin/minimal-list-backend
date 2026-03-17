import io

from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image


def process_image(image_file, max_width=1200, thumb_width=400):
    """Resize, convert to WebP, and generate thumbnail."""
    img = Image.open(image_file)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Resize main image
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    # Save main as WebP
    main_io = io.BytesIO()
    img.save(main_io, format="WEBP", quality=80)
    main_io.seek(0)
    main_name = image_file.name.rsplit(".", 1)[0] + ".webp"
    main_file = InMemoryUploadedFile(main_io, None, main_name, "image/webp", main_io.tell(), None)

    # Generate thumbnail
    ratio = thumb_width / img.width
    thumb = img.resize((thumb_width, int(img.height * ratio)), Image.LANCZOS)
    thumb_io = io.BytesIO()
    thumb.save(thumb_io, format="WEBP", quality=75)
    thumb_io.seek(0)
    thumb_name = image_file.name.rsplit(".", 1)[0] + "_thumb.webp"
    thumb_file = InMemoryUploadedFile(thumb_io, None, thumb_name, "image/webp", thumb_io.tell(), None)

    return main_file, thumb_file
