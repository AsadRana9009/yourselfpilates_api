from django.apps import AppConfig


class UserConfig(AppConfig):
    def ready(self):
        import user.signals
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user'
