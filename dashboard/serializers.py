# videos/serializers.py
from rest_framework import serializers
from rest_framework.reverse import reverse
from .models import Video

class VideoSerializer(serializers.ModelSerializer):
    stream_url = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = ['id', 'uploaded_by', 'video_file', 'title', 'description', 'uploaded_at', 'stream_url']
        read_only_fields = ['id', 'uploaded_at', 'uploaded_by']

    def get_stream_url(self, obj):
        request = self.context.get('request')
        if request:
            return reverse('dashboard:users-videos-stream', kwargs={'pk': obj.pk}, request=request)
        return None

    def create(self, validated_data):
        validated_data['uploaded_by'] = self.context['request'].user
        return super().create(validated_data)
