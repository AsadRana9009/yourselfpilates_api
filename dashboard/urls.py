from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AnalyticsView, VideoViewSet

app_name = 'dashboard'

# Create the router and register viewsets if needed
router = DefaultRouter()
router.register(r'videos', VideoViewSet, basename='users-videos')

urlpatterns = [
    path('analytics/', AnalyticsView.as_view(), name='analytics'),

    path('', include(router.urls)),
]
