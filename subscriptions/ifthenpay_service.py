import os
import requests
import logging
import hashlib
from decimal import Decimal
from datetime import datetime
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class IfThenPayService:
    """Service to handle IfThenPay MultiBanco, MB WAY, and Credit Card API interactions"""
    
    # MultiBanco URLs
    MB_SANDBOX_URL = "https://api.ifthenpay.com/multibanco/reference/sandbox"
    MB_PRODUCTION_URL = "https://api.ifthenpay.com/multibanco/reference/init"
    
    # MB WAY URLs
    MBWAY_URL = "https://api.ifthenpay.com/spg/payment/mbway"
    MBWAY_STATUS_URL = "https://api.ifthenpay.com/spg/payment/mbway/status"
    
    # Credit Card URLs (based on documentation: /init/{CCARD_KEY} or /sandbox/init/{CCARD_KEY})
    CCARD_BASE_URL = "https://api.ifthenpay.com/creditcard"
    
    def __init__(self):
        self.mb_key = os.getenv('IFTHENPAY_MB_KEY')
        self.mbway_key = os.getenv('IFTHENPAY_MBWAY_KEY')
        self.ccard_key = os.getenv('IFTHENPAY_CCARD_KEY')
        self.backoffice_key = os.getenv('IFTHENPAY_BACKOFFICE_KEY')
        self.sandbox_mode = os.getenv('IFTHENPAY_SANDBOX_MODE', 'True').lower() == 'true'
    
    def get_multibanco_api_url(self):
        """Get the appropriate MultiBanco API URL based on sandbox mode"""
        return self.MB_SANDBOX_URL if self.sandbox_mode else self.MB_PRODUCTION_URL
    
    def get_api_url(self):
        """Get the appropriate API URL based on sandbox mode"""
        return self.SANDBOX_URL if self.sandbox_mode else self.PRODUCTION_URL
    
    def format_amount(self, amount):
        """Format amount to string with exactly 2 decimal places"""
        if isinstance(amount, (int, float, Decimal)):
            return f"{float(amount):.2f}"
        return str(amount)
    
    def parse_expiry_date(self, date_string):
        """
        Convert IfThenPay date format (DD-MM-YYYY) to Django timezone-aware datetime
        
        Args:
            date_string: Date in DD-MM-YYYY format or None
            
        Returns:
            timezone-aware datetime object or None
        """
        if not date_string or date_string == 'null':
            return None
        
        try:
            # Try DD-MM-YYYY format
            naive_dt = datetime.strptime(date_string, '%d-%m-%Y')
            # Make it timezone-aware
            return timezone.make_aware(naive_dt)
        except ValueError:
            try:
                # Try YYYY-MM-DD format (already correct)
                naive_dt = datetime.strptime(date_string, '%Y-%m-%d')
                return timezone.make_aware(naive_dt)
            except ValueError:
                logger.warning(f"Could not parse expiry date: {date_string}")
                return None
    
    def generate_order_id(self, order_instance, max_length=25):
        """
        Generate robust unique order ID for all payment methods.
        For MB WAY (max_length=15), use a hash-based suffix to ensure uniqueness.
        For others, use timestamp+pk+short uuid.
        """
        import uuid
        if max_length <= 15:
            # MB WAY: 15 chars max, use prefix + last 8 of uuid + last 3 of pk
            uid = uuid.uuid4().hex[-8:]
            pk_str = str(order_instance.pk)[-3:]
            return f"MBW{uid}{pk_str}"[:15]
        else:
            # MultiBanco/CreditCard: 25 chars max, use timestamp+pk+short uuid
            timestamp = datetime.now().strftime('%y%m%d%H%M%S')
            uid = uuid.uuid4().hex[:6]
            pk_str = str(order_instance.pk)
            return f"ORD{timestamp}{pk_str}{uid}"[:max_length]
    
    def create_payment_reference(self, order, user, expiry_days=3):
        """
        Create a MultiBanco payment reference via IfThenPay API
        
        Args:
            order: Order instance
            user: User instance (professor)
            expiry_days: Number of days until expiration (default: 3)
        
        Returns:
            dict: API response with reference details
        """
        url = self.get_multibanco_api_url()
        
        payload = {
            "mbKey": self.mb_key,
            "amount": self.format_amount(order.amount),
            "orderId": order.order_id,
            "clientEmail": user.email,
            "clientName": user.full_name,
            "clientPhone": user.contact_number or "",
            "description": f"Subscription: {order.pack.title}",
            "expiryDays": expiry_days,
        }
        
        try:
            logger.info(f"Requesting MultiBanco reference for order {order.order_id}")
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Check if request was successful (Status == "0")
            if data.get('Status') == "0":
                logger.info(f"MultiBanco reference generated successfully for order {order.order_id}")
                
                # Parse expiry date to proper format
                expiry_date_str = data.get('ExpiryDate')
                expiry_date = self.parse_expiry_date(expiry_date_str)
                
                return {
                    'success': True,
                    'entity': data.get('Entity'),
                    'reference': data.get('Reference'),
                    'amount': data.get('Amount'),
                    'request_id': data.get('RequestId'),
                    'expiry_date': expiry_date,
                    'expiry_date_display': expiry_date_str,  # Keep original for display
                    'order_id': data.get('OrderId'),
                }
            else:
                error_message = data.get('Message', 'Unknown error')
                logger.error(f"IfThenPay API error for order {order.order_id}: {error_message}")
                return {
                    'success': False,
                    'error': error_message,
                    'status': data.get('Status'),
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error calling IfThenPay API: {str(e)}")
            return {
                'success': False,
                'error': f"Network error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error in create_payment_reference: {str(e)}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
    
    def create_mbway_payment(self, order, user, phone_number):
        """
        Create an MB WAY payment request
        
        Args:
            order: Order instance
            user: User instance (professor)
            phone_number: Mobile number in format: country_code#number (e.g., 351#912345678)
        
        Returns:
            dict: API response with payment status
        """
        if not self.mbway_key:
            return {
                'success': False,
                'error': 'MB WAY key not configured'
            }
        
        url = self.MBWAY_URL
        
        # MB WAY uses POST with JSON body
        payload = {
            "mbWayKey": self.mbway_key,
            "orderId": order.order_id[:15],  # MB WAY has 15 char limit
            "amount": self.format_amount(order.amount),
            "mobileNumber": phone_number,
            "email": user.email,
            "description": f"Subscription: {order.pack.title}"[:100],
        }
        
        try:
            logger.info(f"Requesting MB WAY payment for order {order.order_id}")
            logger.info(f"URL: {url}")
            logger.info(f"Payload: {payload}")
            
            response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            status_code = data.get('Status')
            
            # Status codes:
            # 000 - Request initialized successfully (pending acceptance)
            # 100 - Could not complete, try again
            # 122 - Transaction declined
            # 999 - Error, try again
            
            if status_code == "000":
                logger.info(f"MB WAY payment initialized for order {order.order_id}")
                return {
                    'success': True,
                    'status': status_code,
                    'message': data.get('Message'),
                    'request_id': data.get('RequestId'),
                    'order_id': data.get('OrderId'),
                    'amount': data.get('Amount'),
                }
            else:
                error_message = data.get('Message', 'Payment request failed')
                logger.error(f"MB WAY payment error for order {order.order_id}: {error_message} (Status: {status_code})")
                return {
                    'success': False,
                    'error': error_message,
                    'status': status_code,
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error calling MB WAY API: {str(e)}")
            return {
                'success': False,
                'error': f"Network error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error in create_mbway_payment: {str(e)}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
    
    def check_mbway_status(self, request_id, amount):
        """
        Check MB WAY payment status
        
        Args:
            request_id: RequestId from the initial payment request
            amount: Payment amount (not used in status check, kept for compatibility)
        
        Returns:
            dict: Payment status information
        """
        if not self.mbway_key:
            return {
                'success': False,
                'error': 'MB WAY key not configured'
            }
        
        params = {
            "mbWayKey": self.mbway_key,
            "requestId": request_id
        }
        
        try:
            logger.info(f"Checking MB WAY status for request_id: {request_id}")
            response = requests.get(self.MBWAY_STATUS_URL, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            status_code = data.get('Status')
            
            # Status codes:
            # 000 - Transaction successfully completed (Payment confirmed)
            # 020 - Transaction rejected by user
            # 101 - Transaction expired (4 minutes timeout)
            # 122 - Transaction declined
            
            logger.info(f"MB WAY status response: {data}")
            
            return {
                'success': True,
                'status': status_code,
                'message': data.get('Message'),
                'request_id': data.get('RequestId'),
                'created_at': data.get('CreatedAt'),
                'updated_at': data.get('UpdateAt'),
                'is_paid': status_code == "000",
                'is_rejected': status_code in ["020", "122"],
                'is_expired': status_code == "101",
            }
        
        except Exception as e:
            logger.error(f"Error checking MB WAY status: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_creditcard_payment(self, order, success_url, error_url, cancel_url, language='pt'):
        """
        Create a Credit Card payment request
        
        Args:
            order: Order instance
            success_url: URL to redirect on successful payment
            error_url: URL to redirect on error
            cancel_url: URL to redirect on cancel
            language: Language for payment page (default 'pt')
        
        Returns:
            dict: API response with PaymentUrl
        """
        if not self.ccard_key:
            return {
                'success': False,
                'error': 'Credit Card key not configured'
            }
        
        # Build URL: /sandbox/init/{CCARD_KEY} or /init/{CCARD_KEY}
        endpoint = f"sandbox/init/{self.ccard_key}" if self.sandbox_mode else f"init/{self.ccard_key}"
        url = f"{self.CCARD_BASE_URL}/{endpoint}"
        
        payload = {
            "orderId": order.order_id[:15],  # Max 15 characters
            "amount": self.format_amount(order.amount),
            "successUrl": success_url,
            "errorUrl": error_url,
            "cancelUrl": cancel_url,
            "language": language
        }
        
        try:
            logger.info(f"Requesting Credit Card payment for order {order.order_id}")
            logger.info(f"URL: {url}")
            logger.info(f"Payload: {payload}")
            
            response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            status_code = data.get('Status')
            
            # Status codes:
            # 0 - Success (PaymentUrl returned)
            # -1 - Unauthorized request
            
            if status_code == "0":
                logger.info(f"Credit Card payment URL generated for order {order.order_id}")
                return {
                    'success': True,
                    'status': status_code,
                    'message': data.get('Message'),
                    'payment_url': data.get('PaymentUrl'),
                    'request_id': data.get('RequestId'),
                }
            else:
                error_message = data.get('Message', 'Payment request failed')
                logger.error(f"Credit Card payment error for order {order.order_id}: {error_message} (Status: {status_code})")
                return {
                    'success': False,
                    'error': error_message,
                    'status': status_code,
                }
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error calling Credit Card API: {str(e)}")
            return {
                'success': False,
                'error': f"Network error: {str(e)}"
            }
        
        except Exception as e:
            logger.error(f"Unexpected error in create_creditcard_payment: {str(e)}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
    
    # def verify_creditcard_signature(self, order_id, amount, request_id, signature_key):
    #     """
    #     Verify Credit Card payment signature (sk parameter)
        
    #     Args:
    #         order_id: Order ID from callback
    #         amount: Amount from callback
    #         request_id: Request ID from callback
    #         signature_key: Signature key (sk) from callback
        
    #     Returns:
    #         bool: True if signature is valid
    #     """
    #     if not self.ccard_key:
    #         logger.error("Credit Card key not configured for signature verification")
    #         return False
        
    #     # Create message: orderId + amount + requestId
    #     message = f"{order_id}{amount}{request_id}"
        
    #     # Calculate SHA-256 hash using CCARD_KEY as secret
    #     calculated_hash = hashlib.sha256(f"{message}{self.ccard_key}".encode()).hexdigest()
        
    #     logger.info(f"Signature verification - Message: {message}, Calculated: {calculated_hash}, Received: {signature_key}")
        
    #     return calculated_hash == signature_key
    
    def verify_callback(self, callback_data):
        """
        Verify IfThenPay callback authenticity
        
        Args:
            callback_data: Dict containing callback parameters
        
        Returns:
            bool: True if callback is valid
        """
        # TODO: Implement callback verification logic
        # This will depend on IfThenPay's callback security mechanism
        return True
