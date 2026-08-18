from django.urls import reverse

from rest_framework import serializers

from subscriptions.models import Region

from .models import TVScreen, TVTrack, TVVideo


def stream_url(obj, file_field, route, context):
    """
    Playback URL for a media row.

    Points at the Range-capable streaming endpoint rather than the raw
    MEDIA_URL path, so players can seek to a position they have not buffered.
    """
    if not file_field:
        return None
    request = context.get('request')
    path = reverse(route, kwargs={'pk': obj.pk})
    return request.build_absolute_uri(path) if request else path


class DefaultTrueBooleanField(serializers.BooleanField):
    """
    DRF maps a checkbox missing from a multipart form to False, which would
    silently deactivate every item uploaded from a FormData request that omits
    the field. These rows should default to active, like the model does.
    """
    default_empty_html = True


class RegionScopedMixin:
    """Force non-admin staff to create/update media inside their own region."""

    def get_fields(self):
        fields = super().get_fields()
        # `region` is required by the model but non-admins never send it —
        # it is resolved from the caller in validate().
        if 'region' in fields:
            fields['region'].required = False
        if 'is_active' in fields:
            fields['is_active'] = DefaultTrueBooleanField(required=False)
        return fields

    def _resolve_region(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return attrs

        if getattr(user, 'role', None) == 'admin':
            if not attrs.get('region') and not self.instance:
                raise serializers.ValidationError({'region': 'This field is required.'})
            return attrs

        if not user.region_id:
            raise serializers.ValidationError(
                {'region': 'Your account is not assigned to a region. Ask an admin to set one.'}
            )
        attrs['region'] = Region.objects.get(pk=user.region_id)
        return attrs

    def validate(self, attrs):
        return self._resolve_region(super().validate(attrs))


class UploaderMixin:
    """Stamps the uploader. Only for models that actually have that field."""

    def create(self, validated_data):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            validated_data['uploaded_by'] = request.user
        return super().create(validated_data)


class TVVideoSerializer(RegionScopedMixin, UploaderMixin, serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name', read_only=True)
    file_url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(source='uploaded_by.full_name', read_only=True)

    class Meta:
        model = TVVideo
        fields = [
            'id', 'region', 'region_name', 'title', 'description', 'caption',
            'video_file', 'file_url', 'order', 'is_active',
            'uploaded_by', 'uploaded_by_name', 'uploaded_at',
        ]
        read_only_fields = ['id', 'uploaded_by', 'uploaded_at']

    def get_file_url(self, obj):
        return stream_url(obj, obj.video_file, 'tv:tv-video-stream', self.context)


class TVTrackSerializer(RegionScopedMixin, UploaderMixin, serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name', read_only=True)
    file_url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(source='uploaded_by.full_name', read_only=True)

    class Meta:
        model = TVTrack
        fields = [
            'id', 'region', 'region_name', 'title', 'artist',
            'audio_file', 'file_url', 'order', 'is_active',
            'uploaded_by', 'uploaded_by_name', 'uploaded_at',
        ]
        read_only_fields = ['id', 'uploaded_by', 'uploaded_at']

    def get_file_url(self, obj):
        return stream_url(obj, obj.audio_file, 'tv:tv-track-stream', self.context)


class TVScreenSerializer(RegionScopedMixin, serializers.ModelSerializer):
    region_name = serializers.CharField(source='region.name', read_only=True)
    public_path = serializers.SerializerMethodField()
    video_count = serializers.SerializerMethodField()
    track_count = serializers.SerializerMethodField()

    class Meta:
        model = TVScreen
        fields = [
            'id', 'region', 'region_name', 'name', 'slug', 'is_active',
            'quote_text', 'quote_author',
            'booking_url', 'booking_cta_title', 'booking_cta_subtitle',
            'welcome_message_template', 'show_teacher_name',
            'refresh_interval_seconds',
            'public_path', 'video_count', 'track_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']

    def get_public_path(self, obj):
        return f"/{obj.slug}"

    def get_video_count(self, obj):
        return obj.region.tvvideos.filter(is_active=True).count()

    def get_track_count(self, obj):
        return obj.region.tvtracks.filter(is_active=True).count()


class TVDisplayVideoSerializer(serializers.ModelSerializer):
    """Trimmed payload for the public screen."""
    src = serializers.SerializerMethodField()

    class Meta:
        model = TVVideo
        fields = ['id', 'title', 'caption', 'src', 'order']

    def get_src(self, obj):
        return stream_url(obj, obj.video_file, 'tv:tv-video-stream', self.context)


class TVDisplayTrackSerializer(serializers.ModelSerializer):
    src = serializers.SerializerMethodField()

    class Meta:
        model = TVTrack
        fields = ['id', 'title', 'artist', 'src', 'order']

    def get_src(self, obj):
        return stream_url(obj, obj.audio_file, 'tv:tv-track-stream', self.context)
