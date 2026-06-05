import requests
from .auth import IglooAuth

class IglooClient:
    def __init__(self, client_id=None, client_secret=None):
        self.auth = IglooAuth(client_id, client_secret)
        self.api_base = "https://api.igloodeveloper.co/igloohome"

    def delete_pin_job(self, device_id, bridge_id, pin):
        """
        Delete a PIN from the lock via the bridge jobs endpoint.
        """
        token = self.auth.get_token()
        url = f"{self.api_base}/devices/{device_id}/jobs/bridges/{bridge_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        job_data = {
            "jobType": 5,  # Delete PIN code
            "jobData": {
                "pin": pin
            }
        }
        response = requests.post(url, json=job_data, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to delete PIN job: {response.status_code} {response.text}")

    def create_pin_job(self, device_id, bridge_id, access_name, pin, start_date, end_date=None):
        token = self.auth.get_token()
        url = f"{self.api_base}/devices/{device_id}/jobs/bridges/{bridge_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        job_data = {
            "jobType": 4,  # Create Custom PIN code
            "jobData": {
                "accessName": access_name,
                "pin": pin,
                "pinType": 4,  # Duration
                "startDate": start_date,
            }
        }
        if end_date:
            job_data["jobData"]["endDate"] = end_date
        response = requests.post(url, json=job_data, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to create PIN job: {response.status_code} {response.text}")
