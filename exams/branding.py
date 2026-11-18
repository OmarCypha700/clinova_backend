"""
Institution branding helpers.

Branding (institution name, short name, logo) is stored on the SiteSettings
singleton so every school runs the same code and differs only in data.
"""

import io

from PIL import Image, UnidentifiedImageError

PRODUCT_NAME = "ClinOva"

LOGO_MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB upload limit
LOGO_MAX_PIXELS = 25_000_000  # reject decompression bombs before decoding
LOGO_MAX_SIZE = (512, 512)  # stored logos are downscaled to fit this box
LOGO_ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}  # no SVG: it can carry scripts


class LogoError(ValueError):
    """Raised with a user-facing message when an uploaded logo is rejected."""


def process_logo(uploaded_file):
    """
    Validate an uploaded logo and return it re-encoded as PNG bytes.

    Re-encoding means whatever is served back is a clean image produced by
    Pillow, never the uploaded bytes themselves.
    """
    if uploaded_file.size > LOGO_MAX_UPLOAD_BYTES:
        raise LogoError("Logo must be 2 MB or smaller.")

    data = uploaded_file.read()
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise LogoError("File is not a valid image.")

    if fmt not in LOGO_ALLOWED_FORMATS:
        raise LogoError("Logo must be a PNG, JPEG or WebP image.")
    if width * height > LOGO_MAX_PIXELS:
        raise LogoError("Logo dimensions are too large.")

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            img = img.convert("RGBA")
            img.thumbnail(LOGO_MAX_SIZE)
            out = io.BytesIO()
            img.save(out, format="PNG", optimize=True)
    except (OSError, ValueError):
        raise LogoError("Logo could not be processed.")
    return out.getvalue()


def logo_url(settings):
    """Versioned public URL of the logo, or None when no logo is set."""
    if not settings.logo:
        return None
    version = int(settings.logo_updated_at.timestamp()) if settings.logo_updated_at else 0
    return f"/api/exams/branding/logo?v={version}"


def display_name(settings):
    return settings.short_name or settings.institution_name


# ── Django admin (Unfold) callables, referenced by dotted path in settings ──

def _settings_or_none():
    from .models import SiteSettings

    try:
        return SiteSettings.get()
    except Exception:  # DB not migrated yet (e.g. during the first deploy)
        return None


def site_header(request):
    s = _settings_or_none()
    name = display_name(s) if s else ""
    return f"{PRODUCT_NAME} · {name}" if name else PRODUCT_NAME


def site_title(request):
    s = _settings_or_none()
    name = s.institution_name if s else ""
    return f"{PRODUCT_NAME} – {name}" if name else f"{PRODUCT_NAME} Clinical Practical Assessment"
