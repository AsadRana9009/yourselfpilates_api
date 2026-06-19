from rest_framework.viewsets import ModelViewSet
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import Pack, SubscriptionHistory, Order, Region, PackRegionPrice, CreditWallet
from django.template.loader import render_to_string
from .serializers import PackSerializer, SubscriptionHistorySerializer, OrderSerializer, RegionSerializer
from .permissions import IsAdminOrReadOnly
from .ifthenpay_service import IfThenPayService
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


from drf_spectacular.utils import extend_schema, OpenApiExample
from rest_framework import serializers as drf_serializers


class FreeCreditsRequestSerializer(drf_serializers.Serializer):
    user_id = drf_serializers.IntegerField(
        required=False,
        help_text="User ID — use this or 'email'"
    )
    email = drf_serializers.EmailField(
        required=False,
        help_text="User email — use this or 'user_id'"
    )
    hours = drf_serializers.IntegerField(
        required=True,
        min_value=1,
        help_text="Number of credit hours to assign (must be ≥ 1)"
    )
    region_id = drf_serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Region ID — required for Public Students, optional for Pro users"
    )


class FreeCreditsView(APIView):
    """Developer tool: assign free credits to any user for testing booking flows."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @extend_schema(
        request=FreeCreditsRequestSerializer,
        description=(
            "**Developer-only endpoint** — assign free credits to any user to test the booking flow.\n\n"
            "Works identically to paid credit assignment:\n"
            "- Updates `User.remaining_hours` and `User.total_purchased_hours`\n"
            "- Creates a `CreditWallet` entry when `region_id` is supplied "
            "(required for Public Students — the booking endpoint checks this wallet)\n\n"
            "**Pro Professor / Pro Student** → `user_id` + `hours`\n\n"
            "**Public Student** → `user_id` (or `email`) + `hours` + `region_id`"
        ),
        examples=[
            OpenApiExample(
                'Pro Professor or Pro Student',
                value={"user_id": 5, "hours": 10},
                request_only=True,
            ),
            OpenApiExample(
                'Public Student (region required)',
                value={"email": "student@gmail.com", "hours": 5, "region_id": 2},
                request_only=True,
            ),
        ],
    )
    def post(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        serializer = FreeCreditsRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data

        user_id = data.get('user_id')
        email = data.get('email')
        hours = data['hours']
        region_id = data.get('region_id')

        if not user_id and not email:
            return Response({'error': 'Provide user_id or email.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=user_id) if user_id else User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        region = None
        if region_id:
            try:
                region = Region.objects.get(pk=region_id, is_active=True)
            except Region.DoesNotExist:
                return Response({'error': 'Region not found or inactive.'}, status=status.HTTP_404_NOT_FOUND)

        hours_decimal = Decimal(str(hours))

        user.remaining_hours = (user.remaining_hours or Decimal('0')) + hours_decimal
        user.total_purchased_hours = (user.total_purchased_hours or Decimal('0')) + hours_decimal
        user.save(update_fields=['remaining_hours', 'total_purchased_hours'])

        wallet_data = None
        if region:
            wallet = CreditWallet.objects.create(
                user=user,
                pack=None,
                order=None,
                region=region,
                total_hours=hours_decimal,
                used_hours=Decimal('0'),
                purchase_date=timezone.now(),
                expiry_date=timezone.now() + timezone.timedelta(days=365),
                status='active',
            )
            wallet_data = {
                'id': wallet.id,
                'region': region.name,
                'total_hours': float(wallet.total_hours),
                'remaining_hours': float(wallet.remaining_hours),
                'expiry_date': wallet.expiry_date.date().isoformat(),
            }

        role = getattr(user, 'role', '')
        is_public = getattr(user, 'is_public', False)
        if role in ('professor', 'teacher'):
            display_role = 'Public Professor' if is_public else 'Pro Professor'
        elif role == 'student':
            display_role = 'Public Student' if is_public else 'Pro Student'
        else:
            display_role = role.capitalize() or 'Unknown'

        return Response({
            'success': True,
            'user_id': user.id,
            'email': user.email,
            'full_name': user.full_name,
            'display_role': display_role,
            'hours_added': hours,
            'new_remaining_hours': float(user.remaining_hours),
            'total_purchased_hours': float(user.total_purchased_hours),
            'region': region.name if region else None,
            'wallet_entry': wallet_data,
        }, status=status.HTTP_200_OK)

class PackViewSet(ModelViewSet):
    queryset = Pack.objects.all()
    serializer_class = PackSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user

        # Admins see all packs including inactive ones
        if user.is_authenticated and getattr(user, "role", None) == "admin":
            queryset = Pack.objects.all()
        else:
            # All other users (authenticated or anonymous) browse active packs freely.
            # Role/permission checks happen at the subscribe action, not here.
            queryset = Pack.objects.filter(active=True)

        # Region filter: returns packs for that region + global packs (no region assigned)
        region_id = self.request.query_params.get('region')
        if region_id:
            from django.db.models import Q
            queryset = queryset.filter(Q(region__id=region_id) | Q(region__isnull=True))

        return queryset

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def set_region_prices(self, request, pk=None):
        """Admin: set per-region prices for a pack. Body: {"prices": [{"region_id": 1, "price": "25.00"}]}"""
        if request.user.role != 'admin':
            return Response({"error": "Only admins can set region prices."}, status=status.HTTP_403_FORBIDDEN)

        pack = self.get_object()
        prices = request.data.get('prices', [])

        for entry in prices:
            region_id = entry.get('region_id')
            price = entry.get('price')
            if not region_id or price is None:
                continue
            try:
                region = Region.objects.get(pk=region_id)
            except Region.DoesNotExist:
                continue
            if price == '' or price is None:
                PackRegionPrice.objects.filter(pack=pack, region=region).delete()
            else:
                PackRegionPrice.objects.update_or_create(
                    pack=pack, region=region,
                    defaults={'price': price}
                )

        return Response(PackSerializer(pack, context={'request': request}).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def subscribe(self, request, pk=None):
        """
        Subscribe a professor to a pack with a chosen payment method.
        Accepts payment_method in the request body: 'creditcard', 'multibanco', or 'mbway'.
        For MB WAY, also accepts mbway_phone in the request body.
        Optionally accepts region_id to use location-specific pricing.
        """
        pack = self.get_object()
        user = request.user

        # Admins, professors, teachers, and students can subscribe
        if user.role not in ['admin', 'professor', 'teacher', 'student']:
            return Response(
                {"error": "You are not allowed to subscribe to packs."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Enforce role/pack match for non-admins
        if user.role != 'admin':
            if user.role in ['professor', 'teacher']:
                # Professors must buy professor packs (any visibility)
                if pack.target_role != 'professor':
                    return Response(
                        {"error": "This pack is not available for your role."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            elif user.role == 'student':
                is_public_user = getattr(user, 'is_public', False)
                if is_public_user:
                    # Public students must buy public packs (any target_role)
                    if not pack.is_public:
                        return Response(
                            {"error": "This pack is not available for your role."},
                            status=status.HTTP_403_FORBIDDEN
                        )
                else:
                    # Pro students must buy pro packs (is_public=False), any target_role
                    if pack.is_public:
                        return Response(
                            {"error": "This pack is not available for your role."},
                            status=status.HTTP_403_FORBIDDEN
                        )

        # Check if pack is active
        if not pack.active:
            return Response(
                {"error": "This pack is not available for subscription."},
                status=status.HTTP_400_BAD_REQUEST
            )

        payment_method = request.data.get('payment_method', 'creditcard').lower()
        mbway_phone = request.data.get('mbway_phone')

        if payment_method not in ['creditcard', 'multibanco', 'mbway']:
            return Response({"error": "Invalid payment method. Choose 'creditcard', 'multibanco', or 'mbway'."}, status=status.HTTP_400_BAD_REQUEST)

        if payment_method == 'mbway' and not mbway_phone:
            return Response({"error": "mbway_phone is required for MB WAY payments. Format: 351#912345678"}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve region and price
        region = None
        price = pack.price
        region_id = request.data.get('region_id')

        if user.role in ['professor', 'teacher']:
            # Professors don't attach a region to their pack purchase
            region = None
        else:
            # Public students MUST specify a region — credits are region-specific
            # Pro students don't need a region (their bookings use pro professors, not regions)
            if user.role != 'admin' and getattr(user, 'is_public', False) and not region_id:
                return Response(
                    {"error": "Region is required for public student pack purchases."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if region_id:
                try:
                    region = Region.objects.get(pk=region_id, is_active=True)
                    region_price = PackRegionPrice.objects.filter(pack=pack, region=region).first()
                    if region_price:
                        price = region_price.price
                except Region.DoesNotExist:
                    return Response({"error": "Region not found or inactive."}, status=status.HTTP_400_BAD_REQUEST)

        # Create order without order_id first
        order = Order.objects.create(
            user=user,
            pack=pack,
            amount=price,
            region=region,
            payment_method=payment_method,
            payment_status='Pendente',
            mbway_phone=mbway_phone if payment_method == 'mbway' else None,
            order_id=''  # Temporary, will set after pk is available
        )

        # Now generate a unique order_id using pk and uuid
        from .ifthenpay_service import IfThenPayService
        ifthenpay_service = IfThenPayService()
        order.order_id = ifthenpay_service.generate_order_id(order, max_length=15)
        order.save(update_fields=["order_id"])

        try:
            if payment_method == 'creditcard':
                return self._process_creditcard_payment(order, user, ifthenpay_service, request)
            elif payment_method == 'multibanco':
                return self._process_multibanco_payment(order, user, ifthenpay_service, request)
            elif payment_method == 'mbway':
                return self._process_mbway_payment(order, user, ifthenpay_service, mbway_phone, request)
        except Exception as e:
            logger.error(f"Error creating payment: {str(e)}")
            order.delete()
            return Response({
                "error": "Failed to create payment. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _process_multibanco_payment(self, order, user, ifthenpay_service, request):
        """Process MultiBanco payment"""
        result = ifthenpay_service.create_payment_reference(order, user, expiry_days=3)
        
        if result['success']:
            # Update order with payment reference details
            order.mb_key = ifthenpay_service.mb_key
            order.mb_entity = result['entity']
            order.mb_reference = result['reference']
            order.request_id = result['request_id']
            order.expiry_date = result['expiry_date']
            order.save()
            
            # Send email with payment reference
            self.send_multibanco_email(user, order, result)
            
            # Build callback URL for testing
            callback_url = (
                f"{request.scheme}://{request.get_host()}/api/subscriptions/callback/ifthenpay/"
                f"?key={result['entity']}&order_id={order.order_id}&amount={result['amount']}"
                f"&reference={result['reference']}&entity={result['entity']}"
            )
            
            return Response({
                "message": "Order created successfully. Please complete the payment.",
                "payment_method": "multibanco",
                "order": OrderSerializer(order).data,
                "payment_details": {
                    "entity": result['entity'],
                    "reference": result['reference'],
                    "amount": f"€{float(result['amount']):.2f}",
                    "expiry_date": result.get('expiry_date_display') or result.get('expiry_date'),
                },
                "callback_url_for_testing": callback_url
            }, status=status.HTTP_201_CREATED)
        else:
            order.delete()
            return Response({
                "error": f"Failed to generate payment reference: {result.get('error')}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _process_mbway_payment(self, order, user, ifthenpay_service, phone_number, request):
        """Process MB WAY payment"""
        result = ifthenpay_service.create_mbway_payment(order, user, phone_number)
        
        if result['success']:
            # Update order with MB WAY details
            order.request_id = result['request_id']
            order.save()
            
            # Send email notification
            self.send_mbway_email(user, order, phone_number)
            
            # Build callback URL for testing
            callback_url = (
                f"{request.scheme}://{request.get_host()}/api/subscriptions/callback/ifthenpay/"
                f"?key={ifthenpay_service.mbway_key}&order_id={order.order_id}&amount={result['amount']}"
                f"&requestId={result['request_id']}"
            )
            
            return Response({
                "message": "MB WAY payment request sent. Please approve on your phone within 4 minutes.",
                "payment_method": "mbway",
                "order": OrderSerializer(order).data,
                "payment_details": {
                    "phone_number": phone_number,
                    "amount": f"€{float(result['amount']):.2f}",
                    "status": result['status'],
                    "request_id": result['request_id'],
                    "timeout": "4 minutes"
                },
                "callback_url_for_testing": callback_url
            }, status=status.HTTP_201_CREATED)
        else:
            order.delete()
            return Response({
                "error": f"Failed to initiate MB WAY payment: {result.get('error')}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _process_creditcard_payment(self, order, user, ifthenpay_service, request):
        """Process Credit Card payment"""
        # Build callback URLs
        base_url = request.build_absolute_uri('/').rstrip('/')
        success_url = f"{base_url}/api/subscriptions/callback/creditcard/success/"
        error_url = f"{base_url}/api/subscriptions/callback/creditcard/error/"
        cancel_url = f"{base_url}/api/subscriptions/callback/creditcard/cancel/"
        
        result = ifthenpay_service.create_creditcard_payment(
            order, success_url, error_url, cancel_url, language='pt'
        )
        
        if result['success']:
            # Update order with Credit Card details
            order.request_id = result['request_id']
            order.ccard_payment_url = result['payment_url']
            order.save()
            
            # Send email notification
            self.send_creditcard_email(user, order, result['payment_url'])
            
            return Response({
                "message": "Credit Card payment page ready. Redirect user to payment_url.",
                "payment_method": "creditcard",
                "order": OrderSerializer(order).data,
                "payment_details": {
                    "payment_url": result['payment_url'],
                    "request_id": result['request_id'],
                    "amount": f"€{float(order.amount):.2f}",
                }
            }, status=status.HTTP_201_CREATED)
        else:
            order.delete()
            return Response({
                "error": f"Failed to initiate Credit Card payment: {result.get('error')}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def send_multibanco_email(self, user, order, payment_details):
        """Send email with MultiBanco payment reference"""
        subject = f"Referência de Pagamento - {order.pack.title}"
        
        # Use display date if available, otherwise try to format the datetime
        expiry_display = payment_details.get('expiry_date_display')
        if not expiry_display and payment_details.get('expiry_date'):
            expiry_date = payment_details['expiry_date']
            if expiry_date:
                expiry_display = expiry_date.strftime('%d-%m-%Y') if hasattr(expiry_date, 'strftime') else str(expiry_date)
            else:
                expiry_display = 'Sem expiração'
        
        message = f"""
Olá {user.full_name},

Obrigado pela sua subscrição ao plano "{order.pack.title}".

Para concluir o seu pagamento, utilize os seguintes dados:

Entidade: {payment_details['entity']}
Referência: {payment_details['reference']}
Valor: €{float(payment_details['amount']):.2f}

Data de Expiração: {expiry_display or 'Sem expiração'}

Pode efetuar o pagamento em qualquer Multibanco, Homebanking ou aplicação MB WAY.

Após a confirmação do pagamento, as suas horas serão automaticamente adicionadas à sua conta.

ID do Pedido: {order.order_id}

Obrigado,
Equipa YourselfPilates
        """
        
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            logger.info(f"Payment reference email sent to {user.email}")
        except Exception as e:
            logger.error(f"Failed to send payment reference email: {str(e)}")
    
    def send_mbway_email(self, user, order, phone_number):
        """Send email notification for MB WAY payment"""
        subject = f'Pedido de Pagamento MB WAY - {order.pack.title}'
        message = f"""
Olá {user.full_name},

Foi enviado um pedido de pagamento MB WAY para o seu telemóvel!

Detalhes do Pagamento:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pack: {order.pack.title}
Valor: €{float(order.amount):.2f}
Telemóvel: {phone_number.replace('#', ' ')}
Validade: 4 minutos
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Por favor, abra a app MB WAY no seu telemóvel e aprove o pagamento.

Após a confirmação do pagamento, as horas do pack ({order.pack.total_hours} horas) serão automaticamente adicionadas à sua conta.

ID do Pedido: {order.order_id}

Obrigado,
Equipa YourselfPilates
        """
        
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            logger.info(f"MB WAY payment email sent to {user.email}")
        except Exception as e:
            logger.error(f"Failed to send MB WAY payment email: {str(e)}")
    
    def send_creditcard_email(self, user, order, payment_url):
        """Send email notification for Credit Card payment"""
        subject = f'Pagamento por Cartão de Crédito - {order.pack.title}'
        message = f"""
Olá {user.full_name},

A sua página de pagamento por cartão de crédito está pronta!

Detalhes do Pagamento:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pack: {order.pack.title}
Valor: €{float(order.amount):.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Por favor, clique no link abaixo para completar o pagamento:
{payment_url}

Após a confirmação do pagamento, as horas do pack ({order.pack.total_hours} horas) serão automaticamente adicionadas à sua conta.

ID do Pedido: {order.order_id}

Obrigado,
Equipa YourselfPilates
        """
        
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
            logger.info(f"Credit Card payment email sent to {user.email}")
        except Exception as e:
            logger.error(f"Failed to send Credit Card payment email: {str(e)}")


class OrderViewSet(ModelViewSet):
    """ViewSet for managing payment orders"""
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter orders based on user role"""
        user = self.request.user
        owner_role = self.request.query_params.get('owner_role')
        
        # Admin can see all orders
        if user.role == 'admin':
            queryset = Order.objects.all()
            if owner_role == 'pro':
                queryset = queryset.filter(user__role__in=['professor', 'teacher'])
            elif owner_role == 'student':
                queryset = queryset.filter(user__role='student')
            return queryset.order_by('-created_at')
        
        # Professors, teachers and students can only see their own orders
        if user.role in ['professor', 'teacher', 'student']:
            queryset = Order.objects.filter(user=user)
            if owner_role == 'pro':
                queryset = queryset.filter(user__role__in=['professor', 'teacher'])
            elif owner_role == 'student':
                queryset = queryset.filter(user__role='student')
            return queryset.order_by('-created_at')

        return Order.objects.none()

    def perform_destroy(self, instance):
        # Only deduct hours if the order was actually paid
        if instance.payment_status == 'Pago':
            user = instance.user
            hours = instance.pack.total_hours
            user.remaining_hours = max(0, (user.remaining_hours or 0) - hours)
            user.total_purchased_hours = max(0, (user.total_purchased_hours or 0) - hours)
            user.save(update_fields=['remaining_hours', 'total_purchased_hours'])
        instance.delete()

    def partial_update(self, request, *args, **kwargs):
        """Handle PATCH requests to update payment method for pending orders"""
        order = self.get_object()
        
        # Check if user owns this order or is admin
        if order.user != request.user and request.user.role != 'admin':
            return Response(
                {"error": "You don't have permission to update this order."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Only allow updates for pending orders
        if order.payment_status != 'Pendente':
            return Response(
                {"error": f"Cannot update payment method. Order status is '{order.payment_status}'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get new payment method
        new_payment_method = request.data.get('payment_method')
        
        # If payment method is being changed
        if new_payment_method and new_payment_method != order.payment_method:
            return self._handle_payment_method_change(order, new_payment_method, request)
        
        # If just updating mbway_phone without changing method
        return super().partial_update(request, *args, **kwargs)
    
    def _handle_payment_method_change(self, order, new_payment_method, request):
        """Handle changing payment method for an order"""
        # Validate payment method
        if new_payment_method not in ['multibanco', 'mbway', 'creditcard']:
            return Response(
                {"error": "Invalid payment method. Choose 'multibanco', 'mbway', or 'creditcard'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # For MB WAY, validate phone number (accept both 'phone_number' and 'mbway_phone')
        phone_number = request.data.get('mbway_phone') or request.data.get('phone_number', '')
        if new_payment_method == 'mbway' and not phone_number:
            return Response(
                {"error": "Phone number is required for MB WAY payments. Format: 351#912345678"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Always clear old payment details BEFORE any payment method change or API call
        self._clear_payment_details(order)

        # Track the change
        order.previous_payment_method = order.payment_method
        order.payment_method_updated_at = timezone.now()

        # Update payment method
        order.payment_method = new_payment_method
        if new_payment_method == 'mbway':
            order.mbway_phone = phone_number

        # Do NOT regenerate order_id. It must remain unique and constant for each order.
        order.save()
        
        # Generate new payment details
        try:
            from .ifthenpay_service import IfThenPayService
            ifthenpay_service = IfThenPayService()
            user = order.user
            if new_payment_method == 'multibanco':
                result = self._regenerate_multibanco_payment(order, user, ifthenpay_service, request)
            elif new_payment_method == 'mbway':
                result = self._regenerate_mbway_payment(order, user, ifthenpay_service, phone_number, request)
            elif new_payment_method == 'creditcard':
                result = self._regenerate_creditcard_payment(order, user, ifthenpay_service, request)
            return result
        except Exception as e:
            logger.error(f"Error regenerating payment details: {str(e)}")
            return Response(
                {"error": f"Failed to generate new payment details. {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _clear_payment_details(self, order):
        """Clear old payment details when changing payment method"""
        # Clear MultiBanco details
        order.mb_key = None
        order.mb_entity = None
        order.mb_reference = None
        order.expiry_date = None
        
        # Clear MB WAY details (keep phone if switching to mbway)
        order.request_id = None
        
        # Clear Credit Card details
        order.ccard_payment_url = None
        order.ccard_signature_key = None
    
    def _regenerate_multibanco_payment(self, order, user, ifthenpay_service, request):
        """Regenerate MultiBanco payment reference"""
        result = ifthenpay_service.create_payment_reference(order, user, expiry_days=3)
        
        if result['success']:
            order.mb_key = ifthenpay_service.mb_key
            order.mb_entity = result['entity']
            order.mb_reference = result['reference']
            order.request_id = result['request_id']
            order.expiry_date = result['expiry_date']
            order.save()
            
            # Send email with new payment reference
            pack_viewset = PackViewSet()
            pack_viewset.send_multibanco_email(user, order, result)
            
            callback_url = (
                f"{request.scheme}://{request.get_host()}/api/subscriptions/callback/ifthenpay/"
                f"?key={result['entity']}&order_id={order.order_id}&amount={result['amount']}"
                f"&reference={result['reference']}&entity={result['entity']}"
            )
            
            return Response({
                "message": "Payment method updated successfully to MultiBanco.",
                "payment_method": "multibanco",
                "order": OrderSerializer(order).data,
                "payment_details": {
                    "entity": result['entity'],
                    "reference": result['reference'],
                    "amount": f"€{float(result['amount']):.2f}",
                    "expiry_date": result.get('expiry_date_display') or result.get('expiry_date'),
                },
                "callback_url_for_testing": callback_url
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": f"Failed to generate payment reference: {result.get('error')}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _regenerate_mbway_payment(self, order, user, ifthenpay_service, phone_number, request):
        """Regenerate MB WAY payment request"""
        result = ifthenpay_service.create_mbway_payment(order, user, phone_number)
        
        if result['success']:
            order.request_id = result['request_id']
            order.save()
            
            # Send email notification
            pack_viewset = PackViewSet()
            pack_viewset.send_mbway_email(user, order, phone_number)
            
            callback_url = (
                f"{request.scheme}://{request.get_host()}/api/subscriptions/callback/ifthenpay/"
                f"?key={ifthenpay_service.mbway_key}&order_id={order.order_id}&amount={result['amount']}"
                f"&requestId={result['request_id']}"
            )
            
            return Response({
                "message": "Payment method updated successfully to MB WAY. Please approve on your phone within 4 minutes.",
                "payment_method": "mbway",
                "order": OrderSerializer(order).data,
                "payment_details": {
                    "phone_number": phone_number,
                    "amount": f"€{float(result['amount']):.2f}",
                    "status": result['status'],
                    "request_id": result['request_id'],
                    "timeout": "4 minutes"
                },
                "callback_url_for_testing": callback_url
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": f"Failed to initiate MB WAY payment: {result.get('error')}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _regenerate_creditcard_payment(self, order, user, ifthenpay_service, request):
        """Regenerate Credit Card payment URL"""
        base_url = request.build_absolute_uri('/').rstrip('/')
        success_url = f"{base_url}/api/subscriptions/callback/creditcard/success/"
        error_url = f"{base_url}/api/subscriptions/callback/creditcard/error/"
        cancel_url = f"{base_url}/api/subscriptions/callback/creditcard/cancel/"
        
        result = ifthenpay_service.create_creditcard_payment(
            order, success_url, error_url, cancel_url, language='pt'
        )
        
        if result['success']:
            order.ccard_payment_url = result['payment_url']
            order.request_id = result.get('request_id')
            order.save()
            
            # Send email with payment link
            pack_viewset = PackViewSet()
            pack_viewset.send_creditcard_email(user, order, result['payment_url'])
            
            return Response({
                "message": "Payment method updated successfully to Credit Card.",
                "payment_method": "creditcard",
                "order": OrderSerializer(order).data,
                "payment_details": {
                    "payment_url": result['payment_url'],
                    "amount": f"€{float(order.amount):.2f}",
                }
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {"error": f"Failed to generate payment URL: {result.get('error')}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def admin_create(self, request):
        """Admin-only: create an order manually on behalf of any user."""
        if request.user.role != 'admin':
            return Response(
                {"error": "Only admins can create orders manually."},
                status=status.HTTP_403_FORBIDDEN
            )

        from django.contrib.auth import get_user_model
        User = get_user_model()

        user_id = request.data.get('user_id')
        pack_id = request.data.get('pack_id')
        payment_method = request.data.get('payment_method', 'manual')
        payment_status_value = request.data.get('payment_status', 'Pago')
        region_id = request.data.get('region_id')

        if not user_id or not pack_id:
            return Response(
                {"error": "user_id and pack_id are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            pack = Pack.objects.get(pk=pack_id)
        except Pack.DoesNotExist:
            return Response({"error": "Pack not found."}, status=status.HTTP_404_NOT_FOUND)

        # Resolve optional region and its price override
        region = None
        price = pack.price
        if region_id:
            try:
                region = Region.objects.get(pk=region_id, is_active=True)
                region_price = PackRegionPrice.objects.filter(pack=pack, region=region).first()
                if region_price:
                    price = region_price.price
            except Region.DoesNotExist:
                return Response({"error": "Region not found or inactive."}, status=status.HTTP_400_BAD_REQUEST)

        # For 'manual' payment method, store as 'multibanco' (closest offline method)
        stored_method = payment_method if payment_method in ['multibanco', 'mbway', 'creditcard'] else 'multibanco'

        order = Order.objects.create(
            user=user,
            pack=pack,
            amount=price,
            region=region,
            payment_method=stored_method,
            payment_status=payment_status_value,
        )

        # If paid, add hours to the user and log subscription history
        if payment_status_value == 'Pago':
            user.remaining_hours = (user.remaining_hours or 0) + pack.total_hours
            user.total_purchased_hours = (user.total_purchased_hours or 0) + pack.total_hours
            user.subscribed_pack = pack
            user.subscription_date = timezone.now()
            user.save()

            SubscriptionHistory.objects.create(
                user=user,
                pack=pack,
                order=order,
                hours_added=pack.total_hours,
            )

            create_wallet_entry(user, pack, order)

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def check_mbway_status(self, request, pk=None):
        """
        Check MB WAY payment status for a specific order.
        Only works for MB WAY payments.
        """
        order = self.get_object()
        
        # Check if user owns this order or is admin
        if order.user != request.user and request.user.role != 'admin':
            return Response(
                {"error": "You don't have permission to check this order."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if this is a MB WAY payment
        if order.payment_method != 'mbway':
            return Response(
                {"error": "This endpoint only works for MB WAY payments."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if already paid
        if order.payment_status == 'Pago':
            return Response({
                "status": "paid",
                "message": "Payment has already been confirmed.",
                "order": OrderSerializer(order).data
            })
        
        # Check if order has request_id
        if not order.request_id:
            return Response(
                {"error": "No request_id found for this order."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check payment status with IfThenPay
        from .ifthenpay_service import IfThenPayService
        ifthenpay_service = IfThenPayService()
        
        try:
            result = ifthenpay_service.check_mbway_status(order.request_id, order.amount)
            
            return Response({
                "order_id": order.order_id,
                "payment_status": order.payment_status,
                "mbway_status": result['status'],
                "is_paid": result['is_paid'],
                "is_rejected": result['is_rejected'],
                "is_expired": result['is_expired'],
                "message": result['message']
            })
            
        except Exception as e:
            logger.error(f"Error checking MB WAY status: {str(e)}")
            return Response({
                "error": "Failed to check payment status. Please try again later."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RegionViewSet(ModelViewSet):
    """CRUD for gym regions/locations. Admins can write; anyone authenticated can read."""
    queryset = Region.objects.all()
    serializer_class = RegionSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and getattr(user, 'role', None) == 'admin':
            return Region.objects.all()
        return Region.objects.filter(is_active=True)


# Callback endpoint for IfThenPay payment notifications
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

@csrf_exempt
def ifthenpay_callback(request):
    """
    Webhook endpoint to receive payment confirmation from IfThenPay.
    This endpoint will be called by IfThenPay when a payment is completed.
    
    Expected parameters (will vary based on IfThenPay callback format):
    - order_id or reference
    - amount
    - status
    """
    if request.method != 'GET' and request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)
    
    try:
        # Get parameters from request (adjust based on actual IfThenPay callback format)
        params = request.GET if request.method == 'GET' else request.POST

        logger.info(f"IfThenPay callback received: {params}")

        # (Anti-phishing key validation removed as per user request)


        # Extract relevant data (adjust field names based on actual callback)
        request_id = params.get('idpedido')      # MBWay request_id
        reference = params.get('referencia') or params.get('reference')  # This is your order_id
        amount = params.get('valor') or params.get('amount')
        payment_datetime = params.get('datahorapag')
        status = params.get('estado')

        logger.info(f"Callback payment_datetime: {payment_datetime}")

        if not request_id and not reference:
            logger.error("Missing order_id or reference in callback")
            return HttpResponse('Missing parameters', status=400)

        # Find the order: Try by order_id (from referencia), then by request_id (from idpedido), then by mb_reference
        order = None
        if reference:
            order = Order.objects.filter(order_id=reference).first()
        if not order and request_id:
            order = Order.objects.filter(request_id=request_id).first()
        if not order and reference:
            order = Order.objects.filter(mb_reference=reference).first()

        if not order:
            logger.error(f"Order not found: order_id={request_id}, reference={reference}")
            return HttpResponse('Order not found', status=404)

        # Check if already paid
        if order.payment_status == 'Pago':
            logger.info(f"Order {order.order_id} already paid")
            return HttpResponse('OK', status=200)

        # Validate payment method and details match current order state
        # Only run Multibanco validation if order.payment_method == 'multibanco'
        if order.payment_method == 'multibanco':
            if reference:
                if order.mb_reference != reference:
                    logger.warning(f"Order {order.order_id} reference mismatch. Expected {order.mb_reference}, got {reference}")
                    return HttpResponse('Reference mismatch - possibly superseded payment', status=400)
        # Only run MBWay validation if order.payment_method == 'mbway'
        if order.payment_method == 'mbway':
            if request_id:
                if order.request_id != request_id:
                    logger.warning(f"Order {order.order_id} request_id mismatch. Expected {order.request_id}, got {request_id}")
                    return HttpResponse('RequestId mismatch - possibly superseded payment', status=400)

        # Update order status
        order.payment_status = 'Pago'
        order.paid_at = timezone.now()
        order.save()

        # Add hours to user account
        user = order.user
        user.remaining_hours += order.pack.total_hours
        user.total_purchased_hours += order.pack.total_hours
        user.subscribed_pack = order.pack
        user.subscription_date = timezone.now()
        user.save()

        # Create subscription history
        SubscriptionHistory.objects.create(
            user=user,
            pack=order.pack,
            hours_added=order.pack.total_hours
        )

        # Create credit wallet entry
        create_wallet_entry(user, order.pack, order)

        # Send confirmation email
        send_payment_confirmation_email(user, order)

        logger.info(f"Payment confirmed for order {order.order_id}")
        return HttpResponse('OK', status=200)

    except Exception as e:
        logger.error(f"Error processing IfThenPay callback: {str(e)}")
        return HttpResponse('Internal server error', status=500)

def create_wallet_entry(user, pack, order):
    """Create or update a CreditWallet entry when a pack payment is confirmed."""
    CreditWallet.objects.update_or_create(
        order=order,
        defaults={
            'user': user,
            'pack': pack,
            'region': order.region,
            'total_hours': pack.total_hours,
            'used_hours': 0,
            'remaining_hours': pack.total_hours,
            'status': 'active',
        }
    )


def send_payment_confirmation_email(user, order):
    """Send branded HTML email confirming payment was received"""
    subject = f"Pagamento Confirmado - {order.pack.title}"

    try:
        html_message = render_to_string(
            'emails/payment_confirmed.html',
            {
                'full_name': user.full_name,
                'order_id': order.order_id,
                'pack_name': order.pack.title,
                'amount': f'{float(order.amount):.2f}',
                'hours_added': int(order.pack.total_hours),
                'available_hours': int(user.remaining_hours),
                'frontend_url': settings.FRONTEND_URL,
            },
        )
        send_mail(
            subject,
            '',  # plain-text fallback
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False,
        )
        logger.info(f"Payment confirmation email sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {str(e)}")


# Credit Card callback endpoints
@csrf_exempt
def creditcard_success_callback(request):
    """
    Callback endpoint for successful Credit Card payment
    Parameters: id, amount, requestId, sk (signature key)
    """
    try:
        params = request.GET if request.method == 'GET' else request.POST
        logger.info(f"Credit Card SUCCESS callback received: {params}")
        
        order_id = params.get('id')
        amount = params.get('amount')
        request_id = params.get('requestId')
        signature_key = params.get('sk')
        
        if not all([order_id, amount, request_id, signature_key]):
            logger.error("Missing parameters in success callback")
            return HttpResponse('Missing parameters', status=400)
        
        # Find the order
        order = Order.objects.filter(order_id=order_id).first()
        if not order:
            logger.error(f"Order not found: {order_id}")
            return HttpResponse('Order not found', status=404)
        
        # Validate payment method
        if order.payment_method != 'creditcard':
            logger.warning(f"Order {order.order_id} payment method is {order.payment_method}, but Credit Card callback received")
            return HttpResponse('Payment method mismatch', status=400)
        
        # Verify signature
        # from .ifthenpay_service import IfThenPayService
        # ifthenpay_service = IfThenPayService()
        
        # if not ifthenpay_service.verify_creditcard_signature(order_id, amount, request_id, signature_key):
        #     logger.error(f"Invalid signature for order {order_id}")
        #     return HttpResponse('Invalid signature', status=403)
        
        # Check if already paid
        if order.payment_status == 'Pago':
            logger.info(f"Order {order.order_id} already paid")
            return HttpResponse('OK - Already paid', status=200)
        
        # Update order
        order.payment_status = 'Pago'
        order.paid_at = timezone.now()
        order.ccard_signature_key = signature_key
        order.save()
        
        # Add hours to user
        user = order.user
        user.remaining_hours += order.pack.total_hours
        user.total_purchased_hours += order.pack.total_hours
        user.subscribed_pack = order.pack
        user.subscription_date = timezone.now()
        user.save()
        
        # Create subscription history
        SubscriptionHistory.objects.create(
            user=user,
            pack=order.pack,
            hours_added=order.pack.total_hours
        )

        # Create credit wallet entry
        create_wallet_entry(user, order.pack, order)

        # Send confirmation email
        send_payment_confirmation_email(user, order)

        logger.info(f"Credit Card payment confirmed for order {order.order_id}")
        
        # Get frontend URL from settings
        import os
        frontend_url = os.getenv('FRONTEND_URL', '/')
        
        # Redirect to a success page (you can customize this)
        return HttpResponse(f"""
            <html>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: green;">✓ Pagamento Confirmado!</h1>
                <p>O seu pagamento foi processado com sucesso.</p>
                <p>Pedido: {order.order_id}</p>
                <p>Valor: €{float(order.amount):.2f}</p>
                <p>As suas horas foram adicionadas à sua conta.</p>
                <p><a href="{frontend_url}">Voltar ao início</a></p>
            </body>
            </html>
        """, content_type='text/html')
        
    except Exception as e:
        logger.error(f"Error processing Credit Card success callback: {str(e)}")
        return HttpResponse('Internal server error', status=500)


@csrf_exempt
def creditcard_error_callback(request):
    """
    Callback endpoint for failed Credit Card payment
    Parameters: id, amount, requestId
    """
    try:
        params = request.GET if request.method == 'GET' else request.POST
        logger.info(f"Credit Card ERROR callback received: {params}")
        
        order_id = params.get('id')
        
        if order_id:
            order = Order.objects.filter(order_id=order_id).first()
            if order:
                order.payment_status = 'Cancelado'
                order.save()
                logger.info(f"Order {order_id} marked as Cancelado (error)")
        
        # Get frontend URL from settings
        import os
        frontend_url = os.getenv('FRONTEND_URL', '/')
        
        return HttpResponse(f"""
            <html>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: red;">✗ Erro no Pagamento</h1>
                <p>Ocorreu um erro ao processar o seu pagamento.</p>
                <p>Por favor, tente novamente.</p>
                <p><a href="{frontend_url}">Voltar ao início</a></p>
            </body>
            </html>
        """, content_type='text/html')
        
    except Exception as e:
        logger.error(f"Error processing Credit Card error callback: {str(e)}")
        return HttpResponse('Internal server error', status=500)


@csrf_exempt
def creditcard_cancel_callback(request):
    """
    Callback endpoint for cancelled Credit Card payment
    Parameters: id, amount, requestId
    """
    try:
        params = request.GET if request.method == 'GET' else request.POST
        logger.info(f"Credit Card CANCEL callback received: {params}")
        
        order_id = params.get('id')
        
        if order_id:
            order = Order.objects.filter(order_id=order_id).first()
            if order:
                order.payment_status = 'Cancelado'
                order.save()
                logger.info(f"Order {order_id} marked as Cancelado (user cancelled)")
        
        # Get frontend URL from settings
        import os
        frontend_url = os.getenv('FRONTEND_URL', '/')
        
        return HttpResponse(f"""
            <html>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1 style="color: orange;">⚠ Pagamento Cancelado</h1>
                <p>O pagamento foi cancelado.</p>
                <p>Se mudou de ideias, pode tentar novamente.</p>
                <p><a href="{frontend_url}">Voltar ao início</a></p>
            </body>
            </html>
        """, content_type='text/html')
        
    except Exception as e:
        logger.error(f"Error processing Credit Card cancel callback: {str(e)}")
        return HttpResponse('Internal server error', status=500)
