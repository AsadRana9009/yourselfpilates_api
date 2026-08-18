from django.contrib import admin

from .models import TVScreen, TVTrack, TVVideo


@admin.register(TVScreen)
class TVScreenAdmin(admin.ModelAdmin):
    list_display = ('name', 'region', 'slug', 'is_active', 'updated_at')
    list_filter = ('region', 'is_active')
    search_fields = ('name', 'slug')
    readonly_fields = ('slug', 'created_at', 'updated_at')


@admin.register(TVVideo)
class TVVideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'region', 'order', 'is_active', 'uploaded_at')
    list_filter = ('region', 'is_active')
    search_fields = ('title',)


@admin.register(TVTrack)
class TVTrackAdmin(admin.ModelAdmin):
    list_display = ('title', 'artist', 'region', 'order', 'is_active', 'uploaded_at')
    list_filter = ('region', 'is_active')
    search_fields = ('title', 'artist')
