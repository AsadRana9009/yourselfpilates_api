from django.core.management.base import BaseCommand
from django.urls import get_resolver

class Command(BaseCommand):
    help = 'List all registered URLs'

    def handle(self, *args, **options):
        resolver = get_resolver()
        self.stdout.write("Registered URLs:")

        def show_urls(urllist, prefix=''):
            for pattern in urllist:
                if hasattr(pattern, 'url_patterns'):
                    show_urls(pattern.url_patterns, prefix + str(pattern.pattern))
                else:
                    url_pattern = prefix + str(pattern.pattern)
                    url_name = getattr(pattern, 'name', None)
                    self.stdout.write(f"{url_pattern} -> {url_name}")

        show_urls(resolver.url_patterns)