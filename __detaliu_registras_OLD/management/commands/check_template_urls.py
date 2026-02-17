
import re
from pathlib import Path
from django.core.management.base import BaseCommand
from django.urls import get_resolver, NoReverseMatch, reverse

URL_TAG_RE = re.compile(r"{%\s*url\s+['\"]([^'\"]+)['\"][^%]*%}")

class Command(BaseCommand):
    help = "Randa visus {% url 'name' %} šablonuose ir patikrina, ar vardai registruoti."

    def add_arguments(self, parser):
        parser.add_argument("--templates-root", default=".", help="Kur ieškoti šablonų (default: projektas)")

    def handle(self, *args, **opts):
        root = Path(opts["templates_root"]).resolve()
        html_files = list(root.rglob("*.html"))
        resolver = get_resolver()

        used = set()
        missing = {}

        for f in html_files:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for m in URL_TAG_RE.finditer(text):
                name = m.group(1)
                used.add(name)
                try:
                    reverse(name)
                except NoReverseMatch:
                    try:
                        if name in resolver.reverse_dict:
                            continue
                    except Exception:
                        pass
                    missing.setdefault(name, set()).add(str(f))

        self.stdout.write(self.style.MIGRATE_HEADING("Naudojami URL vardai:"))
        for n in sorted(used):
            self.stdout.write(f"  - {n}")

        if missing:
            self.stdout.write(self.style.ERROR("\nTrūkstami (nerasta reverse_dict):"))
            for n, files in missing.items():
                self.stdout.write(self.style.ERROR(f"  ✗ {n}"))
                for fp in sorted(files):
                    self.stdout.write(f"     ↳ {fp}")
        else:
            self.stdout.write(self.style.SUCCESS("\nVisi šablonų vardai rasti URL registruose."))
