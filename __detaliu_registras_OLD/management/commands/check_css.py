import os
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

EXTENDS_RE = re.compile(r'{%\s*extends\s+"([^"]+)"\s*%}')
LOAD_STATIC_RE = re.compile(r'{%\s*load\s+static\s*%}')
USES_STATIC_TAG_RE = re.compile(r'{%\s*static\s+["\']')
LINK_TAG_RE = re.compile(r'<link[^>]+rel=["\']stylesheet["\'][^>]*>', re.IGNORECASE)
RAW_STATIC_PATH_RE = re.compile(r'href=["\'](/?static/[^"\']+)["\']', re.IGNORECASE)

# Šablonai, kurie NORMALIAI neturi paveldėti base.html (partial'ai, komponentai)
ALLOW_NO_EXTENDS_PATTERNS = (
    "components/",
    "partials/",
    "includes/",
    "fragment",
    "partial",
    "_",
)

class Command(BaseCommand):
    help = "Patikrina tipines CSS/static problemas šablonuose ir statiniuose failuose."

    def add_arguments(self, parser):
        parser.add_argument(
            "--templates-root",
            default=None,
            help="Pasirinktinis templates katalogas. Jei nenurodysi, skenuosime visus app'us ir project templates.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Daugiau išvesties.",
        )

    def handle(self, *args, **opts):
        verbose = opts["verbose"]

        # 1) Surenkam visus .html failus
        template_dirs = set()

        if opts["templates_root"]:
            template_dirs.add(Path(opts["templates_root"]))
        else:
            # Django TEMPLATES dirs
            for cfg in settings.TEMPLATES:
                for d in cfg.get("DIRS", []):
                    template_dirs.add(Path(d))

            # App templates (app_name/templates/)
            # Eisim nuo manage.py šaknies
            proj_root = Path(settings.BASE_DIR)
            for root, dirs, files in os.walk(proj_root):
                p = Path(root)
                if p.name == "templates":
                    template_dirs.add(p)

        html_files = []
        for tdir in sorted(template_dirs):
            if not tdir.exists():
                continue
            for root, dirs, files in os.walk(tdir):
                for f in files:
                    if f.endswith(".html"):
                        html_files.append(Path(root) / f)

        if not html_files:
            raise CommandError("Nerasta jokių .html šablonų.")

        problems = {
            "no_extends": [],
            "uses_static_without_load": [],
            "raw_static_links": [],
        }

        for path in sorted(html_files):
            rel = str(path).replace(str(Path(settings.BASE_DIR)) + os.sep, "")
            txt = path.read_text(encoding="utf-8", errors="ignore")

            # A) ar šablonas paveldi base.html (pilni puslapiai turėtų)
            m = EXTENDS_RE.search(txt)
            if not m:
                # jei tai partialas/komponentas – ok, praleidžiam
                if not any(pat in rel for pat in ALLOW_NO_EXTENDS_PATTERNS):
                    # dažnai AJAX partial’ai specialiai be extends, bet pažymėsim kaip INFO
                    problems["no_extends"].append(rel)

            # B) ar naudojamas {% static %} be {% load static %}
            uses_static = bool(USES_STATIC_TAG_RE.search(txt))
            has_load = bool(LOAD_STATIC_RE.search(txt))
            if uses_static and not has_load and not m:
                # jei nepaveldi base.html, o pats naudoja {% static %}, privalo turėti `{% load static %}`
                problems["uses_static_without_load"].append(rel)

            # C) ar yra <link rel="stylesheet" ... href="/static/..."> vietoj {% static %}
            if LINK_TAG_RE.search(txt):
                raw_links = RAW_STATIC_PATH_RE.findall(txt)
                for rl in raw_links:
                    problems["raw_static_links"].append((rel, rl))

        # 2) Patikrinam ar egzistuoja svarbūs statiniai failai (jei juos naudoji)
        #   pvz., js/uzklausa_history.js, css/app.css (pridėk, jei turi kitų)
        must_exist = [
            "js/uzklausa_history.js",  # jei naudojai išorėje; suplonintoj versijoj gali nebenaudoti
            "css/app.css",             # jei turi pagrindinį CSS
        ]
        missing_static = []
        static_dirs = []

        # STATICFILES_DIRS + app static
        static_dirs.extend([Path(d) for d in getattr(settings, "STATICFILES_DIRS", [])])
        # app-level static:
        proj_root = Path(settings.BASE_DIR)
        for root, dirs, files in os.walk(proj_root):
            if Path(root).name == "static":
                static_dirs.append(Path(root))

        for relpath in must_exist:
            found = False
            for sdir in static_dirs:
                if (sdir / relpath).exists():
                    found = True
                    break
            if not found:
                missing_static.append(relpath)

        # 3) Rezultatai
        self.stdout.write(self.style.SUCCESS("✓ Skenavimas baigtas.\n"))

        if problems["no_extends"]:
            self.stdout.write(self.style.WARNING("Šablonai be `{% extends \"base.html\" %}` (gali būti ok, jei partial):"))
            for p in problems["no_extends"]:
                self.stdout.write(f"  - {p}")
            self.stdout.write("")

        if problems["uses_static_without_load"]:
            self.stdout.write(self.style.ERROR("Naudojamas `{% static %}` be `{% load static %}` (ir šablonas nepaveldi base.html):"))
            for p in problems["uses_static_without_load"]:
                self.stdout.write(f"  - {p}")
            self.stdout.write("")

        if problems["raw_static_links"]:
            self.stdout.write(self.style.WARNING("Aptikti `<link rel=\"stylesheet\" href=\"/static/...\">` – geriau naudoti `{% static %}`:"))
            for rel, href in problems["raw_static_links"]:
                self.stdout.write(f"  - {rel}: {href}")
            self.stdout.write("")

        if missing_static:
            self.stdout.write(self.style.WARNING("Galimai trūksta šių statinių failų (neprivaloma, jei jų nenaudoji):"))
            for p in missing_static:
                self.stdout.write(f"  - {p}")
            self.stdout.write("")

        if not any(problems.values()) and not missing_static:
            self.stdout.write(self.style.SUCCESS("Atrodo gerai: didesnių CSS/static problemų nerasta."))
        else:
            self.stdout.write(self.style.WARNING("Jei reikia, gali dar paleisti: `python manage.py collectstatic --dry-run -v 2` ir patikrinti 404 Network skydelyje naršyklėje."))
