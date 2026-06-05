from django.utils import timezone
from bookings.models import Booking
from igloo.client import IglooClient
from django.conf import settings

def delete_igloo_pin(booking):
    client = IglooClient()
    device_id = getattr(settings, 'IGLOO_DEVICE_ID', None)
    bridge_id = getattr(settings, 'IGLOO_BRIDGE_ID', None)
    if device_id and bridge_id and booking.igloo_pin:
        try:
            # Igloo API: jobType 5 = Delete PIN code
            job_data = {
                "jobType": 5,
                "jobData": {
                    "pin": booking.igloo_pin
                }
            }
            url = f"{client.api_base}/devices/{device_id}/jobs/bridges/{bridge_id}"
            token = client.auth.get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            import requests
            response = requests.post(url, json=job_data, headers=headers)
            if response.status_code == 200:
                booking.igloo_pin = None
                booking.save(update_fields=["igloo_pin"])
                return True
            else:
                print(f"Failed to delete PIN for booking {booking.id}: {response.text}")
        except Exception as e:
            print(f"Error deleting PIN for booking {booking.id}: {e}")
    return False

def expire_igloo_pins():
    now = timezone.now()
    expired_bookings = Booking.objects.filter(
        igloo_pin__isnull=False,
        booking_date__lt=now.date()
    )
    for booking in expired_bookings:
        delete_igloo_pin(booking)
    # Also check for bookings ending today but with end time passed
    today_bookings = Booking.objects.filter(
        igloo_pin__isnull=False,
        booking_date=now.date()
    )
    from datetime import datetime
    for booking in today_bookings:
        # Parse end time from time_slot
        try:
            _, end_time = booking.time_slot.split(' - ')
            end_dt = datetime.combine(booking.booking_date, datetime.strptime(end_time, '%H:%M').time())
            if timezone.now() > timezone.make_aware(end_dt):
                delete_igloo_pin(booking)
        except Exception as e:
            print(f"Error parsing end time for booking {booking.id}: {e}")
