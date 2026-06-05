import sys
import os

# Adjust this path to point to your Django project folder
sys.path.insert(0, '/home/yourselfpilates/yourselfpilates_api')

# Set your settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "yourselfpilot.settings")

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()