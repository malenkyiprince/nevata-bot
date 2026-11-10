"""Общая валидация фото и ссылок. Внешний анализ подключён отдельно в research.py."""
import io
import warnings
from urllib.parse import urlsplit

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PHOTO = 3 * 1024 * 1024
MAX_TEXT = 4000
Image.MAX_IMAGE_PIXELS = 20_000_000


class AnalysisError(Exception):
    """Сообщение, которое можно безопасно показать пользователю."""


def prepare_photo(data):
    """Проверяем настоящий формат, убираем метаданные, ограничиваем размеры."""
    if not data or len(data) > MAX_PHOTO:
        raise ValueError("Фото має бути не більше 3 МБ.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValueError("Обери фото JPEG, PNG або WebP.")
                source.load()
                picture = ImageOps.exif_transpose(source)
                picture.thumbnail((2000, 2000))
                background = Image.new("RGB", picture.size, "white")
                if picture.mode in ("RGBA", "LA") or "transparency" in picture.info:
                    picture = picture.convert("RGBA")
                    background.paste(picture, mask=picture.getchannel("A"))
                else:
                    background.paste(picture.convert("RGB"))
                output = io.BytesIO()
                background.save(output, format="JPEG", quality=90)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise ValueError("Не вдалося прочитати фото. Обери JPEG, PNG або WebP до 20 Мп.") from error


def safe_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username:
            return value
    except ValueError:
        pass
    return None
