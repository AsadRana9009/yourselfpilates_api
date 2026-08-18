from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    TVDisplayView,
    TVNowPlayingView,
    TVScreenViewSet,
    TVTrackStreamView,
    TVTrackViewSet,
    TVVideoStreamView,
    TVVideoViewSet,
)

app_name = 'tv'

router = DefaultRouter()
router.register(r'screens', TVScreenViewSet, basename='tv-screen')
router.register(r'videos', TVVideoViewSet, basename='tv-video')
router.register(r'music', TVTrackViewSet, basename='tv-track')

urlpatterns = [
    # Public (hidden-token) endpoints
    path('display/<slug:slug>/now/', TVNowPlayingView.as_view(), name='tv-display-now'),
    path('display/<slug:slug>/', TVDisplayView.as_view(), name='tv-display'),

    # Range-capable media streaming (used by the screens and the dashboard)
    path('stream/video/<int:pk>/', TVVideoStreamView.as_view(), name='tv-video-stream'),
    path('stream/track/<int:pk>/', TVTrackStreamView.as_view(), name='tv-track-stream'),

    path('', include(router.urls)),
]
