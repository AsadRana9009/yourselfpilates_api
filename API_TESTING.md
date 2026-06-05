# Yourself Pilates – API Testing Guide

Base URL (local dev): `http://127.0.0.1:8000`  
Swagger UI: `http://127.0.0.1:8000/api/docs/`

Replace the base URL with your production host when deploying.

---

## Authentication

Every write endpoint and most read endpoints require a DRF token header:

```http
Authorization: Token <your-token>
Content-Type: application/json
```

For file-upload endpoints (`image`, `video_file`, `photo`) use `multipart/form-data` — **do not set `Content-Type`**, the browser/client sets it automatically with the boundary.

---

## 1. Root & Docs

| Method | URL | Notes |
|--------|-----|-------|
| GET | `/` | Welcome message |
| GET | `/api/schema/` | OpenAPI schema |
| GET | `/api/docs/` | Swagger UI |
| GET | `/admin/` | Django admin |

---

## 2. Auth / User

Prefix: `/api/user/`

### POST `/api/user/register/`
Public registration.

```json
{
  "email": "teacher@example.com",
  "password": "StrongPass123",
  "full_name": "Maria Silva",
  "role": "professor",
  "bio": "Pilates instructor",
  "contact_number": "+351912345678",
  "city": "Lisbon"
}
```

### POST `/api/user/login/`
Returns a token.

```json
{
  "email": "teacher@example.com",
  "password": "StrongPass123"
}
```

**Response:**
```json
{
  "token": "abc123...",
  "email": "teacher@example.com",
  "full_name": "Maria Silva",
  "role": "professor",
  "user_id": "5"
}
```

### GET `/api/user/me/`
Authenticated user profile.

### PUT `/api/user/me/`
Full profile update.

### PATCH `/api/user/me/`
Partial profile update.

```json
{
  "full_name": "Maria Silva",
  "bio": "Updated bio",
  "city": "Porto",
  "contact_number": "+351912345678"
}
```

### POST `/api/user/request-reset-otp/`
```json
{ "email": "teacher@example.com" }
```

### POST `/api/user/verify-reset-otp/`
```json
{ "email": "teacher@example.com", "otp": "1234" }
```

### POST `/api/user/confirm-reset-otp/`
```json
{ "email": "teacher@example.com", "otp": "1234" }
```

### POST `/api/user/reset-password-with-otp/`
```json
{
  "email": "teacher@example.com",
  "otp": "1234",
  "new_password": "NewStrongPass123"
}
```

---

## 3. Admin – Users

Prefix: `/api/user/users/`  
Auth: admin token required for all write operations.

### GET `/api/user/users/`
List all users. Optional query params:
- `role` – filter by `professor`, `teacher`, `student`, `admin`
- `is_public` – `true` / `false`
- `show_all` – `true` to skip pagination

### POST `/api/user/users/`
Create a user (admin only).

```json
{
  "email": "professor2@example.com",
  "password": "StrongPass123",
  "full_name": "Joao Pereira",
  "role": "professor",
  "contact_number": "+351911111111",
  "city": "Lisbon",
  "street": "Rua A",
  "country": "Portugal",
  "zipcode": "1000-001",
  "student_ids": [1, 2, 3]
}
```

### GET `/api/user/users/{id}/`
Retrieve a user.

### PUT `/api/user/users/{id}/`
Full update.

### PATCH `/api/user/users/{id}/`
Partial update.

```json
{
  "full_name": "Joao Pereira Updated",
  "student_ids": [4, 5]
}
```

### DELETE `/api/user/users/{id}/`
Delete a user.

### GET `/api/user/users/approve/?user_id=5`
Activate a user (set `is_active=true`).

### GET `/api/user/users/cancel/?user_id=5`
Deactivate a user (set `is_active=false`).

### POST `/api/user/users/{id}/top_up_hours/`  ⭐ NEW
Admin: manually add or set remaining hours for a professor/teacher.

**Mode `add`** — adds hours on top of existing balance:
```json
{
  "hours": 10,
  "mode": "add"
}
```

**Mode `set`** — overwrites the balance to an exact value:
```json
{
  "hours": 20,
  "mode": "set"
}
```

**Response:**
```json
{
  "message": "Hours updated successfully.",
  "remaining_hours": 20.0,
  "total_purchased_hours": 30.0
}
```

> Use this to credit a professor before testing bookings without going through the payment flow.

---

## 4. Admin – Students

Prefix: `/api/user/students/`

### GET `/api/user/students/`
- Professor sees their own students.
- Admin sees all students.

### POST `/api/user/students/`
```json
{
  "full_name": "Ana Costa",
  "email": "ana@example.com",
  "contact_number": "+351912345679",
  "professor": 1
}
```

### GET `/api/user/students/{id}/`
### PUT `/api/user/students/{id}/`
### PATCH `/api/user/students/{id}/`
### DELETE `/api/user/students/{id}/`

### GET `/api/user/students/by-professor/?professor_id=1`
Students belonging to a specific professor.

---

## 5. Bookings

Prefix: `/api/booking/`

> **Admin bypass:** When an admin creates a booking, the professor's remaining-hours check is skipped and no hours are deducted. Useful for testing.

### GET `/api/booking/bookings/`
List bookings visible to the authenticated user.
- Admin: all bookings.
- Professor/teacher: their own bookings.

Filter query params:
- `booking_type` – `pro` or `public`  ⭐ NEW
- `booking_date` – exact date `YYYY-MM-DD`

```
GET /api/booking/bookings/?booking_type=pro
GET /api/booking/bookings/?booking_type=public
GET /api/booking/bookings/?booking_date=2026-06-10
```

### POST `/api/booking/bookings/`
Create a booking.

```json
{
  "title": "Morning Pilates Class",
  "booking_type": "pro",
  "professor": 1,
  "booking_date": "2026-06-10",
  "time_slot": "09:00 - 10:00",
  "students": [1, 2],
  "notes": "Bring mat"
}
```

`booking_type` values: `"pro"` (professor-led, default) | `"public"` (student-initiated)

Valid `time_slot` values (exact string):
`"00:00 - 01:00"`, `"01:00 - 02:00"`, … `"23:00 - 24:00"`

> **Note:** Admin can create bookings for professors who have 0 remaining hours — no hours check or deduction applies for admin-created bookings.

### GET `/api/booking/bookings/{id}/`
### PUT `/api/booking/bookings/{id}/`

Full update:
```json
{
  "title": "Evening Session",
  "booking_type": "pro",
  "professor": 1,
  "booking_date": "2026-06-12",
  "time_slot": "18:00 - 19:00",
  "students": [1],
  "notes": "Updated notes"
}
```

### PATCH `/api/booking/bookings/{id}/`
Partial update (only send changed fields):
```json
{
  "notes": "New notes only"
}
```

### DELETE `/api/booking/bookings/{id}/`
Deletes a booking. Also cleans up any cancelled duplicate slots.

### GET `/api/booking/bookings/{id}/approve/`
Mark booking as `confirmed`. Admin or booking professor only.

### GET `/api/booking/bookings/{id}/reject/`
Mark booking as `cancelled`. Refunds 1 hour to professor. Admin or booking professor only.

### GET `/api/booking/bookings/available_slots/?date=2026-06-10`
Returns available (unbooked) time slots for a date.

**Response:**
```json
[
  { "value": "09:00 - 10:00", "display": "09:00 - 10:00" },
  { "value": "10:00 - 11:00", "display": "10:00 - 11:00" }
]
```

### GET `/api/booking/bookings/filter_bookings/`
Filter bookings for calendar view.

Query params (all optional):
- `month` – `"June 2026"`
- `week_start` – `"2026-06-01"`
- `week_end` – `"2026-06-07"`
- `day` – `"2026-06-15"`
- `status` – `"confirmed"` | `"cancelled"`

```
GET /api/booking/bookings/filter_bookings/?month=June%202026&status=confirmed
GET /api/booking/bookings/filter_bookings/?week_start=2026-06-01&week_end=2026-06-07
GET /api/booking/bookings/filter_bookings/?day=2026-06-10
```

---

## 6. Subscriptions – Packs

Prefix: `/api/subscriptions/packs/`

> Pack images are uploaded as `multipart/form-data`. The API always returns a fully-qualified absolute image URL.

### GET `/api/subscriptions/packs/`
- Admin: all packs.
- Professor/teacher: active `target_role=professor` packs.
- Student: active `target_role=student` packs.
- Public (unauthenticated): active packs.

### POST `/api/subscriptions/packs/`
Admin only. Use `multipart/form-data` when uploading an image.

**With image (multipart/form-data):**
```
title: 10 Hour Pack
description: Ten class hours
price: 79.90
total_hours: 10
active: true
is_public: false
target_role: professor
image: <file>
```

**Without image (JSON):**
```json
{
  "title": "10 Hour Pack",
  "description": "Ten class hours",
  "price": "79.90",
  "total_hours": 10,
  "active": true,
  "is_public": false,
  "target_role": "professor"
}
```

`target_role` values: `"professor"` | `"student"`

### GET `/api/subscriptions/packs/{id}/`
### PUT `/api/subscriptions/packs/{id}/`
Full update (multipart/form-data or JSON):

```json
{
  "title": "10 Hour Pack",
  "description": "Updated description",
  "price": "89.90",
  "total_hours": 10,
  "active": true,
  "is_public": false,
  "target_role": "professor"
}
```

### PATCH `/api/subscriptions/packs/{id}/`
Partial update (admin only):

```json
{ "price": "89.90" }
```

To update only the image, send `multipart/form-data` with just:
```
image: <file>
```

### DELETE `/api/subscriptions/packs/{id}/`
Admin only.

### POST `/api/subscriptions/packs/{id}/subscribe/`
Professor, teacher, or student subscribes to a matching pack.

**Credit Card:**
```json
{ "payment_method": "creditcard" }
```

**MultiBanco:**
```json
{ "payment_method": "multibanco" }
```

**MB WAY:**
```json
{
  "payment_method": "mbway",
  "mbway_phone": "351#912345678"
}
```

---

## 7. Subscriptions – Orders

Prefix: `/api/subscriptions/orders/`

### GET `/api/subscriptions/orders/`
List orders.
- Admin: all orders. Filter by `owner_role=pro` or `owner_role=student`.
- Others: own orders only.

```
GET /api/subscriptions/orders/?owner_role=pro
GET /api/subscriptions/orders/?owner_role=student
GET /api/subscriptions/orders/?page=2
```

### POST `/api/subscriptions/orders/admin_create/`  ⭐ NEW
Admin only. Manually create an order for any user without going through the payment gateway. If `payment_status` is `"Pago"`, hours are immediately credited to the user.

```json
{
  "user_id": 3,
  "pack_id": 2,
  "payment_method": "manual",
  "payment_status": "Pago"
}
```

`payment_status` values: `"Pago"` | `"Pendente"` | `"Cancelado"`  
`payment_method` values: `"manual"` | `"multibanco"` | `"mbway"` | `"creditcard"`

> Use `"payment_status": "Pago"` to instantly credit hours to the professor/student for testing.

### GET `/api/subscriptions/orders/{id}/`
Retrieve an order.

### PATCH `/api/subscriptions/orders/{id}/`
Change payment method on a pending order. This cancels the old payment reference and generates a new one.

Switch to MB WAY:
```json
{
  "payment_method": "mbway",
  "mbway_phone": "351#912345678"
}
```

Switch to MultiBanco:
```json
{ "payment_method": "multibanco" }
```

Switch to Credit Card:
```json
{ "payment_method": "creditcard" }
```

### DELETE `/api/subscriptions/orders/{id}/`
Delete an order.

### GET `/api/subscriptions/orders/{id}/check_mbway_status/`
Poll MB WAY payment status for an order.

---

## 8. Payment Callbacks (IfThenPay webhooks)

These are called by IfThenPay automatically — not by the frontend.

### GET or POST `/api/subscriptions/callback/ifthenpay/`
MultiBanco / MB WAY payment confirmation.

Simulated test query string (MultiBanco):
```
/api/subscriptions/callback/ifthenpay/?referencia=ORD123ABC&amount=79.90&valor=79.90
```

Simulated test query string (MB WAY):
```
/api/subscriptions/callback/ifthenpay/?idpedido=REQ123&amount=79.90
```

### GET or POST `/api/subscriptions/callback/creditcard/success/`
```
?id=ORD123&amount=79.90&requestId=REQ123&sk=SIG123
```

### GET or POST `/api/subscriptions/callback/creditcard/error/`
```
?id=ORD123
```

### GET or POST `/api/subscriptions/callback/creditcard/cancel/`
```
?id=ORD123
```

---

## 9. Dashboard

Prefix: `/api/dashboard/`

### GET `/api/dashboard/analytics/`
Admin-only. Returns booking counts, teacher/student stats, and visitor trends.

**Response shape:**
```json
{
  "total_bookings": 42,
  "confirmed_bookings": 30,
  "cancelled_bookings": 5,
  "bookings_this_month": 12,
  "bookings_this_week": 4,
  "total_teachers": 8,
  "active_teachers": 6,
  "total_students": 25,
  "active_students": 20
}
```

### GET `/api/dashboard/videos/`
List all uploaded videos (paginated).

### POST `/api/dashboard/videos/`
Upload a video. Use `multipart/form-data`.

```
video_file: <file>
title: Intro Class
description: Warm-up video
```

### GET `/api/dashboard/videos/{id}/`
### PUT `/api/dashboard/videos/{id}/`
### PATCH `/api/dashboard/videos/{id}/`
### DELETE `/api/dashboard/videos/{id}/`

### GET `/api/dashboard/videos/{id}/stream/`
Stream the video with HTTP range support.

---

## 10. Quick Test Flow (Step by Step)

### A – Credit a professor for booking testing

```bash
# 1. Login as admin
POST /api/user/login/
{ "email": "admin@gmail.com", "password": "..." }

# 2. Get professors to find their ID
GET /api/user/users/?role=professor

# 3. Top up hours (no payment needed)
POST /api/user/users/{professor_id}/top_up_hours/
{ "hours": 10, "mode": "add" }

# 4. Create a booking as admin (bypasses hours check anyway)
POST /api/booking/bookings/
{
  "title": "Test Class",
  "booking_type": "pro",
  "professor": {professor_id},
  "booking_date": "2026-06-20",
  "time_slot": "09:00 - 10:00",
  "students": [1]
}
```

### B – Create a manual order (credits hours instantly)

```bash
# Admin login first, then:
POST /api/subscriptions/orders/admin_create/
{
  "user_id": {professor_id},
  "pack_id": {pack_id},
  "payment_method": "manual",
  "payment_status": "Pago"
}
# → professor.remaining_hours increases immediately
```

### C – Full payment flow (professor)

```bash
# 1. Login as professor
POST /api/user/login/

# 2. Browse packs
GET /api/subscriptions/packs/

# 3. Subscribe with MultiBanco
POST /api/subscriptions/packs/{id}/subscribe/
{ "payment_method": "multibanco" }

# 4. Simulate IfThenPay callback to mark order as paid
GET /api/subscriptions/callback/ifthenpay/?referencia={order_id}&amount={price}

# 5. Check remaining hours
GET /api/user/me/

# 6. Create booking
POST /api/booking/bookings/
{ ... }
```

### D – Filter bookings by type

```bash
# Pro bookings (professor-led)
GET /api/booking/bookings/?booking_type=pro

# Public bookings (student-initiated)
GET /api/booking/bookings/?booking_type=public
```

---

## 11. Field Reference

### Booking `time_slot` valid values
```
"00:00 - 01:00"  "01:00 - 02:00"  "02:00 - 03:00"  "03:00 - 04:00"
"04:00 - 05:00"  "05:00 - 06:00"  "06:00 - 07:00"  "07:00 - 08:00"
"08:00 - 09:00"  "09:00 - 10:00"  "10:00 - 11:00"  "11:00 - 12:00"
"12:00 - 13:00"  "13:00 - 14:00"  "14:00 - 15:00"  "15:00 - 16:00"
"16:00 - 17:00"  "17:00 - 18:00"  "18:00 - 19:00"  "19:00 - 20:00"
"20:00 - 21:00"  "21:00 - 22:00"  "22:00 - 23:00"  "23:00 - 24:00"
```

### Booking `status` values
`"confirmed"` | `"cancelled"`

### Booking `booking_type` values  ⭐ NEW
`"pro"` (default — professor-led booking) | `"public"` (student-initiated booking)

### Pack `target_role` values
`"professor"` | `"student"`

### Order `payment_status` values
`"Pago"` (paid) | `"Pendente"` (pending) | `"Cancelado"` (cancelled)

### Order `payment_method` values
`"multibanco"` | `"mbway"` | `"creditcard"` | `"manual"` (admin-created only)

### User `role` values
`"admin"` | `"professor"` | `"teacher"` | `"student"`

---

## 12. Django Admin Shortcuts

> Changes made directly in Django admin now sync to the user's remaining hours automatically.

| Action | Effect |
|--------|--------|
| Create a **SubscriptionHistory** record | `remaining_hours` on the user is incremented by `hours_added` |
| Save an **Order** with `payment_status = Pago` | Hours are credited + SubscriptionHistory created |
| Set `payment_status` to `Pago` on an existing order | Hours credited (same as above) |
