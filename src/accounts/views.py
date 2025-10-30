from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model
from django.contrib.auth import login, logout
import random
from django.core.cache import cache
from django.contrib import messages
from twilio.rest import Client
from core.env import config
from .forms import UserCreationForm
from .detection import FaceRecognition
from .tasks import send_email
import cv2
from django_otp.plugins.otp_totp.models import TOTPDevice
import qrcode
from io import BytesIO
import base64
import numpy as np
import os
from django.db.models import Sum
from accounts.models import Transaction
from django.shortcuts import get_object_or_404
from .forms import OTPForm 
from django.contrib.auth.hashers import check_password
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from accounts.models import Transaction
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
User = get_user_model()
faceRecognition = FaceRecognition()


def accounts_register(request):
    if request.method == "POST":
        face_base64 = request.POST.get("captured_image")  # from hidden input
        form = UserCreationForm(request.POST, request.FILES)

        if form.is_valid():
            new_user = form.save(commit=False)
            new_user.save()
            face_id = new_user.id
            phone_number = new_user.phone_number

            # ✅ Ensure dataset directory exists
            dataset_dir = os.path.join("media", "dataset")
            os.makedirs(dataset_dir, exist_ok=True)

            # Save Base64 image if provided
            if face_base64:
                try:
                    # Remove the prefix "data:image/png;base64,"
                    format, imgstr = face_base64.split(';base64,')
                    img_data = base64.b64decode(imgstr)
                    nparr = np.frombuffer(img_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    if img is None:
                        messages.error(request, "Failed to decode captured image")
                        new_user.delete()
                        return redirect("accounts:register")

                    save_path = os.path.join(dataset_dir, f"User.{face_id}.1.jpg")
                    cv2.imwrite(save_path, img)

                except Exception as e:
                    messages.error(request, f"Error processing image: {e}")
                    new_user.delete()
                    return redirect("accounts:register")
            else:
                messages.error(request, "No face image captured")
                new_user.delete()
                return redirect("accounts:register")

            # Train face recognition model
            try:
                faceRecognition.trainFace()
            except Exception as e:
                
                new_user.delete()
                return redirect("accounts:register")

            # Optional: send Twilio SMS
            if phone_number:
                try:
                    client = Client(config('PHONE_ACCOUNT_SID'), config('PHONE_AUTH_TOKEN'))
                    client.messages.create(
                        body="Welcome! Your face has been registered successfully.",
                        from_=config("PHONE_FROM"),
                        to=f"+91{phone_number}"
                    )
                except Exception as e:
                    print("Twilio error:", e)

            # Send async welcome email
            #send_email.delay(f"Hello {new_user.username}", new_user.email)

            
            return redirect("accounts:login")

        else:
            # Form errors
            return render(request, "accounts/register.html", {"form": form})

    else:
        form = UserCreationForm()

    return render(request, "accounts/register.html", {"form": form})

def accounts_login_page(request):
    """Redirect users to the unified auth flow instead of old login."""
    return redirect("accounts:auth_flow")


def auth_flow(request):
    """
    Renders the unified authentication (multi-step face → password → TOTP) flow.
    """
    return render(request, "accounts/auth_flow.html")


def accounts_login(request):
    """Step 1: Face recognition for MFA flow (supports AJAX + fallback)."""
    print("🟡 [accounts_login] Request received:", request.method)
    print("🟡 Headers:", dict(request.headers))
    print("🟡 Is AJAX:", request.headers.get("x-requested-with"))

    if request.method == "POST":
        face_base64 = request.POST.get("captured_image")
        print("🟡 Face data present:", bool(face_base64))

        if not face_base64:
            msg = "No face image received."
            print("❌", msg)
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return redirect("accounts:login")

        try:
            _, imgstr = face_base64.split(";base64,")
            img_data = base64.b64decode(imgstr)
            nparr = np.frombuffer(img_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            print("✅ Image decoded successfully")
        except Exception as e:
            err = f"Error decoding image: {e}"
            print("❌", err)
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": False, "error": err}, status=400)
            messages.error(request, err)
            return redirect("accounts:login")

        # Predict face
        face_id, confidence = faceRecognition.predict_from_image(img)
        print(f"🔍 Face Prediction → ID={face_id}, Confidence={confidence}")

        if face_id is None:
            msg = "No valid face detected. Try again."
            print("❌", msg)
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return redirect("accounts:login")

        threshold = 85
        if confidence > threshold:
            msg = f"Face not recognized (conf={confidence})."
            print("❌", msg)
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return redirect("accounts:register")

        # Found valid face
        try:
            user = get_object_or_404(User, id=face_id)
            print(f"✅ Found user in DB: {user.username} (id={user.id})")

            request.session["pending_user_id"] = user.id

            # ✅ Respond differently for AJAX vs normal
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                payload = {"ok": True, "next": "password", "user": user.username}
                print("🟢 Returning JSON:", payload)
                return JsonResponse(payload)

            print("⚙️ Fallback redirect (non-AJAX)")
            return redirect("accounts:verify_password")

        except Exception as e:
            err = f"Login failed: {e}"
            print("❌ Exception in face login:", err)
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": False, "error": err}, status=400)
            messages.error(request, err)
            return redirect("accounts:register")

    # GET fallback
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        print("❌ Invalid AJAX GET request.")
        return JsonResponse({"ok": False, "error": "Invalid method"}, status=405)

    print("⚙️ Rendering fallback camera page.")
    return render(request, "accounts/login.html")


def accounts_home(request):
    context = {}
    return render(request, "home.html", context)

def accounts_logout(request):
    logout(request)
    return redirect("accounts:auth_flow")

@login_required
def dashboard(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')[:10]
    total_credit = sum(t.amount for t in transactions if t.transaction_type == "credit")
    total_debit = sum(t.amount for t in transactions if t.transaction_type == "debit")
    balance = total_credit - total_debit

    context = {
        'transactions': transactions,
        'total_credit': total_credit,
        'total_debit': total_debit,
        'balance': balance,
    }
    return render(request, 'accounts/dashboard.html', context)
@login_required
def transfers_view(request):
    transactions = Transaction.objects.filter(user=request.user).order_by('-created_at')
    return render(request, "accounts/transfers.html", {"transactions": transactions})

@login_required
def cards_view(request):
    return render(request, "accounts/cards.html")

@login_required
def settings_view(request):
    return render(request, "accounts/settings.html")
@login_required
@require_http_methods(["GET", "POST"])
def new_transfer(request):
    """
    Allows the logged-in user to create a new credit or debit transaction.
    """
    if request.method == "POST":
        amount = request.POST.get("amount")
        description = request.POST.get("description")
        transaction_type = request.POST.get("transaction_type")

        # Validate
        if not amount or float(amount) <= 0:
            messages.error(request, "Invalid amount.")
            return redirect("accounts:dashboard")

        # Create transaction
        Transaction.objects.create(
            user=request.user,
            amount=amount,
            description=description,
            transaction_type=transaction_type,
            status="Completed"
        )

        messages.success(request, f"{transaction_type.title()} of ₹{amount} added successfully!")
        return redirect("accounts:dashboard")

    return render(request, "accounts/transfers.html")
@login_required
def reverify_face(request):
    """
    Re-runs face recognition every few seconds while the user is active on dashboard.
    Returns { status: 'valid' } if same person, else 'invalid'.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    face_base64 = request.POST.get("captured_image")
    if not face_base64:
        return JsonResponse({"error": "No image captured"}, status=400)

    try:
        # Decode base64 → image
        _, imgstr = face_base64.split(';base64,')
        img_data = base64.b64decode(imgstr)
        nparr = np.frombuffer(img_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Predict via ML model
        face_id, confidence = faceRecognition.predict_from_image(img)
        threshold = 85  # same as your login threshold

        if face_id == request.user.id and confidence < threshold:
            return JsonResponse({"status": "valid", "confidence": confidence})
        else:
            return JsonResponse({
                "status": "invalid",
                "confidence": confidence,
                "detected_id": face_id
            })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
# ---------------- TOTP Setup ----------------
@login_required
def setup_totp(request):
    """Generate and display a TOTP QR code for Google Authenticator."""
    user = request.user
    # Check if already has a TOTP device
    existing_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if existing_device:
        messages.info(request, "✅ TOTP already configured.")
        return redirect("accounts:verify_totp")

    # Create unconfirmed device
    device = TOTPDevice.objects.create(user=user, confirmed=False)

    # Generate provisioning URI (Google Authenticator QR)
    uri = device.config_url

    # Create QR code
    qr = qrcode.make(uri)
    buffer = BytesIO()
    qr.save(buffer, format='PNG')
    qr_b64 = base64.b64encode(buffer.getvalue()).decode()

    return render(request, "accounts/setup_totp.html", {
        "qr_code": qr_b64,
        "uri": uri
    })
def accounts_verify_password(request):
    """Step 2: Verify password, then go to TOTP verification."""
    user_id = request.session.get("pending_user_id")
    if not user_id:
        msg = "Session expired. Please login again."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": msg})
        messages.error(request, msg)
        return redirect("accounts:login")

    user = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        password = request.POST.get("password")
        if check_password(password, user.password):
            request.session["password_verified"] = True

            # ✅ AJAX response
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": True, "next": "totp"})

            # fallback
            if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
                return redirect("accounts:verify_totp")
            return redirect("accounts:setup_totp")

        # Wrong password
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Incorrect password."})
        messages.error(request, "❌ Incorrect password.")
        return redirect("accounts:verify_password")

    return render(request, "accounts/verify_password.html", {"user": user})


# ---------------- TOTP Verification ----------------
@login_required
def verify_totp(request):
    """Step 3: Verify TOTP and complete login."""
    user_id = request.session.get("pending_user_id")
    user = get_object_or_404(User, id=user_id)

    device = (
        TOTPDevice.objects.filter(user=user, confirmed=True).first()
        or TOTPDevice.objects.filter(user=user, confirmed=False).first()
    )

    if not device:
        msg = "No TOTP device found. Please set up first."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": msg})
        messages.error(request, msg)
        return redirect("accounts:setup_totp")

    if request.method == "POST":
        token = request.POST.get("token")
        if device.verify_token(token):
            device.confirmed = True
            device.save()

            # ✅ Now log user in and clean up
            login(request, user)
            request.session.pop("pending_user_id", None)
            request.session.pop("password_verified", None)

            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"ok": True})

            messages.success(request, "✅ Logged in successfully!")
            return redirect("accounts:dashboard")

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Invalid code."})
        messages.error(request, "❌ Invalid code, please try again.")
        return redirect("accounts:verify_totp")

    return render(request, "accounts/verify_totp.html")
