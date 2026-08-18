import secrets
import string

from django.conf import settings
from django.db import models

TOKEN_ALPHABET = string.ascii_lowercase + string.digits
TOKEN_LENGTH = 28


def generate_screen_token():
    """Random, unguessable slug used as the hidden public URL of a screen."""
    return ''.join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LENGTH))


class TVScreen(models.Model):
    """
    A "TV Show" — one hidden public page per gym region.

    The page lives at /<slug> on the public site and loops the region's
    videos (muted) plus its music playlist, while showing the booking that
    is running right now at that location.
    """
    region = models.ForeignKey(
        'subscriptions.Region',
        on_delete=models.CASCADE,
        related_name='tv_screens',
        help_text="Gym region/location this screen belongs to",
    )
    name = models.CharField(max_length=120, help_text="Internal name, e.g. 'Reception TV — Caldas'")
    slug = models.SlugField(
        max_length=64,
        unique=True,
        default=generate_screen_token,
        help_text="Hidden token used as the public URL. Regenerate to invalidate the old link.",
    )
    is_active = models.BooleanField(default=True)

    # Left rail
    quote_text = models.TextField(
        blank=True,
        default='Cuida deste espaço como cuidas de ti.',
        help_text="Quote shown under the clock",
    )
    quote_author = models.CharField(max_length=120, blank=True, default='YourSelf Pilates')

    # The bottom bar (phone, Wi-Fi network and password) belongs to the gym
    # location, not to one screen hanging in it, so it lives on Region and is
    # edited there once for every screen at that address.

    # Booking / QR card
    booking_url = models.URLField(
        blank=True,
        help_text="URL encoded in the QR code shown in the 'Agendar Online' card",
    )
    booking_cta_title = models.CharField(max_length=120, blank=True, default='Agendar Online')
    booking_cta_subtitle = models.CharField(
        max_length=200,
        blank=True,
        default='Aponta a câmara do telemóvel para o QR code',
    )

    # Welcome banner shown while a booking is running.
    # Supported placeholders: {student}, {teacher}, {region}
    welcome_message_template = models.CharField(
        max_length=255,
        blank=True,
        default='Bem-vindo(a) {student}, desejamos-te um excelente treino!',
    )
    show_teacher_name = models.BooleanField(default=True)

    refresh_interval_seconds = models.PositiveIntegerField(
        default=60,
        help_text="How often the screen re-checks the backend for the current booking",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['region__name', 'name']

    def __str__(self):
        return f"{self.name} ({self.region.name})"

    def rotate_slug(self):
        self.slug = generate_screen_token()
        self.save(update_fields=['slug', 'updated_at'])
        return self.slug


class TVMediaBase(models.Model):
    """Shared fields for the region-scoped media that a screen plays."""
    region = models.ForeignKey(
        'subscriptions.Region',
        on_delete=models.CASCADE,
        related_name='%(class)ss',
        help_text="Only screens of this region will play this item",
    )
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0, help_text="Playback order, lowest first")
    is_active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)ss',
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ['order', 'uploaded_at']

    def __str__(self):
        return f"{self.title} ({self.region.name})"


class TVVideo(TVMediaBase):
    """A video played muted, in order, on loop."""
    video_file = models.FileField(upload_to='tv/videos/')
    description = models.TextField(blank=True, null=True)
    caption = models.CharField(
        max_length=160,
        blank=True,
        help_text="Badge shown over the video, e.g. 'Inspiração em movimento'",
    )


class TVTrack(TVMediaBase):
    """A music track played in order, on loop."""
    audio_file = models.FileField(upload_to='tv/music/')
    artist = models.CharField(max_length=255, blank=True)
