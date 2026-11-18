"""
Set an institution's branding from the server, the same settings admins see
in Settings: institution name, short name, logo and brand colour.

    python manage.py set_branding \
        --name "Nursing and Midwifery Training College, Tanoso" \
        --short-name CNMT --color "#166534" --logo path/to/logo.png

    python manage.py set_branding              # show the current branding
    python manage.py set_branding --clear-logo
    python manage.py set_branding --color ""   # back to the ClinOva colour

Only the options you pass are changed. Run it after `migrate`.
"""

import re
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from exams.branding import LogoError, process_logo
from exams.models import SiteSettings

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


class Command(BaseCommand):
    help = "Show or set the institution's name, short name, logo and brand colour."

    def add_arguments(self, parser):
        parser.add_argument("--name", help="Full institution name (max 150 characters).")
        parser.add_argument("--short-name", help="Short name or code, e.g. CNMT (max 30 characters).")
        parser.add_argument("--color", help='Brand colour as hex, e.g. "#166534". Empty string resets to the ClinOva colour.')
        logo = parser.add_mutually_exclusive_group()
        logo.add_argument("--logo", metavar="PATH", help="PNG, JPEG or WebP file, up to 2 MB.")
        logo.add_argument("--clear-logo", action="store_true", help="Remove the logo.")

    def handle(self, *args, **opts):
        s = SiteSettings.get()
        changed = []

        if opts["name"] is not None:
            name = opts["name"].strip()
            if len(name) > 150:
                raise CommandError("--name must be 150 characters or fewer.")
            s.institution_name = name
            changed.append("institution name")

        if opts["short_name"] is not None:
            short = opts["short_name"].strip()
            if len(short) > 30:
                raise CommandError("--short-name must be 30 characters or fewer.")
            s.short_name = short
            changed.append("short name")

        if opts["color"] is not None:
            color = opts["color"].strip()
            if color and not HEX.match(color):
                raise CommandError('--color must be a hex colour like "#166534", or "" to reset.')
            s.brand_color = color.lower()
            changed.append("brand colour")

        if opts["logo"]:
            path = Path(opts["logo"]).expanduser()
            if not path.is_file():
                raise CommandError(f"Logo file not found: {path}")
            with path.open("rb") as fh:
                try:
                    png = process_logo(File(fh))
                except LogoError as e:
                    raise CommandError(str(e))
            s.logo = png
            s.logo_content_type = "image/png"
            s.logo_updated_at = timezone.now()
            changed.append("logo")
        elif opts["clear_logo"]:
            s.logo = None
            s.logo_content_type = ""
            s.logo_updated_at = timezone.now()
            changed.append("logo (removed)")

        if changed:
            s.save()
            self.stdout.write(self.style.SUCCESS(f"Updated: {', '.join(changed)}."))
        self._show(s)

    def _show(self, s):
        self.stdout.write(self.style.MIGRATE_HEADING("Current branding"))
        rows = [
            ("Institution name", s.institution_name or "(not set)"),
            ("Short name", s.short_name or "(not set)"),
            ("Brand colour", s.brand_color or "(ClinOva default)"),
            ("Logo", f"set ({len(bytes(s.logo)) // 1024 or 1} KB PNG)" if s.logo else "(not set)"),
        ]
        for label, value in rows:
            self.stdout.write(f"  {label:<17} {value}")
