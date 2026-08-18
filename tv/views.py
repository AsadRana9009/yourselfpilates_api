from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import TVScreen, TVTrack, TVVideo
from .permissions import IsAdminOrRegionStaff
from .streaming import range_file_response
from .serializers import (
    TVDisplayTrackSerializer,
    TVDisplayVideoSerializer,
    TVScreenSerializer,
    TVTrackSerializer,
    TVVideoSerializer,
)
from .utils import build_welcome_payload, display_timezone, local_now


class RegionScopedViewSet(viewsets.ModelViewSet):
    """
    Admins see every region; professors/teachers only ever see (and can only
    ever write) the rows belonging to the region they are assigned to.
    """
    permission_classes = [IsAdminOrRegionStaff]

    def get_queryset(self):
        qs = self.queryset.select_related('region')
        user = self.request.user
        if getattr(user, 'role', None) != 'admin':
            qs = qs.filter(region_id=user.region_id)

        region = self.request.query_params.get('region')
        if region:
            qs = qs.filter(region_id=region)

        is_active = self.request.query_params.get('is_active')
        if is_active in ('true', 'false'):
            qs = qs.filter(is_active=(is_active == 'true'))
        return qs


class TVScreenViewSet(RegionScopedViewSet):
    """CRUD for the hidden TV Show pages (one or more per region)."""
    queryset = TVScreen.objects.all()
    serializer_class = TVScreenSerializer

    @action(detail=True, methods=['post'])
    def rotate_slug(self, request, pk=None):
        """Invalidate the current hidden URL and issue a new one."""
        screen = self.get_object()
        screen.rotate_slug()
        return Response(self.get_serializer(screen).data)


class TVVideoViewSet(RegionScopedViewSet):
    """Region-scoped videos played muted, in order, on the TV Show page."""
    queryset = TVVideo.objects.all()
    serializer_class = TVVideoSerializer

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        """Body: {"items": [{"id": 3, "order": 0}, ...]} — restricted to the caller's scope."""
        return _apply_reorder(self.get_queryset(), request)


class TVTrackViewSet(RegionScopedViewSet):
    """Region-scoped music playlist for the TV Show page."""
    queryset = TVTrack.objects.all()
    serializer_class = TVTrackSerializer

    @action(detail=False, methods=['post'])
    def reorder(self, request):
        return _apply_reorder(self.get_queryset(), request)


def _apply_reorder(queryset, request):
    items = request.data.get('items') or []
    if not isinstance(items, list):
        return Response({'detail': "'items' must be a list."}, status=status.HTTP_400_BAD_REQUEST)

    by_id = {obj.id: obj for obj in queryset}
    updated = []
    for item in items:
        try:
            item_id = int(item['id'])
            order = int(item['order'])
        except (KeyError, TypeError, ValueError):
            return Response(
                {'detail': "Each item needs an integer 'id' and 'order'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Unknown ids, and ids belonging to another region, are both invisible
        # here — report that instead of blaming the payload's shape.
        if item_id not in by_id:
            return Response(
                {'detail': f'Item {item_id} does not exist or is not in your region.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        obj = by_id[item_id]
        obj.order = order
        updated.append(obj)

    model = queryset.model
    model.objects.bulk_update(updated, ['order'])
    return Response({'updated': len(updated)})


class TVDisplayView(APIView):
    """
    Public, unauthenticated payload for a hidden screen URL.

    GET /api/tv/display/<slug>/
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        screen = get_object_or_404(TVScreen, slug=slug, is_active=True)
        ctx = {'request': request}
        videos = TVVideo.objects.filter(region=screen.region, is_active=True)
        tracks = TVTrack.objects.filter(region=screen.region, is_active=True)
        now = local_now()

        return Response({
            'screen': {
                'name': screen.name,
                'slug': screen.slug,
                'quote_text': screen.quote_text,
                'quote_author': screen.quote_author,
                # The footer describes the gym location itself, so it is read
                # straight off the region and editing it there updates every
                # screen at that address.
                'contact_phone': screen.region.phone,
                'wifi_name': screen.region.wifi_name,
                'wifi_password': screen.region.wifi_password,
                'booking_url': screen.booking_url,
                'booking_cta_title': screen.booking_cta_title,
                'booking_cta_subtitle': screen.booking_cta_subtitle,
                'refresh_interval_seconds': screen.refresh_interval_seconds,
            },
            'region': {
                'id': screen.region_id,
                'name': screen.region.name,
                'slug': screen.region.slug,
            },
            'videos': TVDisplayVideoSerializer(videos, many=True, context=ctx).data,
            'tracks': TVDisplayTrackSerializer(tracks, many=True, context=ctx).data,
            'now_playing': build_welcome_payload(screen, now=now),
            'server_time': now.isoformat(),
            # The screen must show the gym's wall clock, not the browser's. A
            # TV (or a laptop previewing it) in another timezone would
            # otherwise display a time that disagrees with the booking windows
            # resolved here.
            'timezone': str(display_timezone()),
        })


class TVMediaStreamView(APIView):
    """
    Serve TV media with HTTP Range support.

    Django only serves MEDIA_ROOT with plain 200 responses, so players cannot
    seek to a position they have not buffered yet. Playback and the dashboard
    preview both go through here instead. Public, like the screens themselves —
    the underlying files are already reachable under /media/.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    model = None
    file_attr = None
    fallback_content_type = 'application/octet-stream'

    def get(self, request, pk):
        obj = get_object_or_404(self.model, pk=pk)
        return range_file_response(
            request,
            getattr(obj, self.file_attr),
            self.fallback_content_type,
        )


class TVVideoStreamView(TVMediaStreamView):
    model = TVVideo
    file_attr = 'video_file'
    fallback_content_type = 'video/mp4'


class TVTrackStreamView(TVMediaStreamView):
    model = TVTrack
    file_attr = 'audio_file'
    fallback_content_type = 'audio/mpeg'


class TVNowPlayingView(APIView):
    """
    Lightweight poll target so the screen can refresh the welcome banner
    without re-downloading the media playlists.

    GET /api/tv/display/<slug>/now/
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        screen = get_object_or_404(TVScreen, slug=slug, is_active=True)
        now = local_now()
        return Response({
            'now_playing': build_welcome_payload(screen, now=now),
            'server_time': now.isoformat(),
            'timezone': str(display_timezone()),
        })
