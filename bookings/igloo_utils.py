import random
from datetime import datetime, timedelta
from igloo.client import IglooClient
from django.conf import settings


def generate_random_pin(length=6):
    return ''.join(str(random.randint(0, 9)) for _ in range(length))

def create_igloo_pin_for_booking(booking, device_id, bridge_id):
    """
    Create a PIN for the booking using Bridge Proxied Jobs API and return the PIN and jobId.
    """
    client = IglooClient()
    access_name = f"Booking {booking.id}"
    pin = generate_random_pin()
    # Parse booking start/end from booking_date and time_slot
    start_time, end_time = booking.time_slot.split(' - ')
    # Use UTC timezone for ISO format
    from datetime import timezone
    start_dt = datetime.combine(booking.booking_date, datetime.strptime(start_time, '%H:%M').time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(booking.booking_date, datetime.strptime(end_time, '%H:%M').time()).replace(tzinfo=timezone.utc)
    start_iso = start_dt.isoformat()
    end_iso = end_dt.isoformat()
    result = client.create_pin_job(
        device_id=device_id,
        bridge_id=bridge_id,
        access_name=access_name,
        pin=pin,
        start_date=start_iso,
        end_date=end_iso
    )
    return pin, result.get('jobId')


def delete_igloo_pin_for_booking(booking):
    """
    Delete the PIN for the booking using Bridge Proxied Jobs API.
    """
    device_id = getattr(settings, 'IGLOO_DEVICE_ID', None)
    bridge_id = getattr(settings, 'IGLOO_BRIDGE_ID', None)
    pin = booking.igloo_pin
    if device_id and bridge_id and pin:
        client = IglooClient()
        try:
            client.delete_pin_job(device_id=device_id, bridge_id=bridge_id, pin=pin)
        except Exception as e:
            print(f"Igloo PIN deletion failed: {e}")
