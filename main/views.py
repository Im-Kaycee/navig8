from django.shortcuts import render
from rest_framework import generics
from .serializers import *
from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
# Create your views here.
class RegisterView(generics.CreateAPIView):
    queryset = get_user_model().objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    
class UserDetailView(generics.RetrieveAPIView):
    queryset = get_user_model().objects.all()
    serializer_class = UserSerializer
    lookup_field = 'id'
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        return self.request.user

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    def put(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()

        return Response({"detail": "Password changed successfully."}, status=status.HTTP_200_OK)

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class PasswordResetRequestView(APIView):
    """
    Request a password reset email.
    POST /api/v1/auth/password/reset/
    Body: { "email": "user@example.com" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip()
        
        # Validate email is provided
        if not email:
            return Response(
                {"email": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Basic email format validation
        if '@' not in email or '.' not in email:
            return Response(
                {"email": ["Enter a valid email address."]},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to find user by email
        try:
            user = User.objects.get(email=email)
            
            # Generate password reset token
            token = default_token_generator.make_token(user)
            
            # Encode user ID (base64)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Build reset URL
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:8080')
            reset_url = f"{frontend_url}/reset-password?uid={uid}&token={token}"
            
            # Email content
            subject = 'Password Reset Request - Waka'
            message = f"""Hello {user.username},

You requested to reset your password for your Waka account.

Click the link below to reset your password:
{reset_url}

This link will expire in 24 hours.

If you didn't request this password reset, please ignore this email. Your password will remain unchanged.

Best regards,
Waka Team
"""
            
            # Send email
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception as e:
                # Log the error but don't reveal it to user
                print(f"Email send error: {e}")
                # Still return success to prevent email enumeration
            
        except User.DoesNotExist:
            # Don't reveal that user doesn't exist (security best practice)
            pass
        
        # Always return success response to prevent email enumeration
        return Response(
            {"detail": "If an account exists with this email, you will receive a password reset link."},
            status=status.HTTP_200_OK
        )


class PasswordResetConfirmView(APIView):
    """
    Confirm password reset with token and set new password.
    POST /api/v1/auth/password/reset/confirm/
    Body: {
        "uid": "encoded_user_id",
        "token": "reset_token",
        "new_password1": "newpassword123",
        "new_password2": "newpassword123"
    }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        # Get data from request
        uid = request.data.get('uid', '').strip()
        token = request.data.get('token', '').strip()
        new_password1 = request.data.get('new_password1', '')
        new_password2 = request.data.get('new_password2', '')
        
        # Validate all required fields
        errors = {}
        
        if not uid:
            errors['uid'] = ['This field is required.']
        if not token:
            errors['token'] = ['This field is required.']
        if not new_password1:
            errors['new_password1'] = ['This field is required.']
        if not new_password2:
            errors['new_password2'] = ['This field is required.']
        
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Check passwords match
        if new_password1 != new_password2:
            return Response(
                {"new_password2": ["The two password fields didn't match."]},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Decode user ID and retrieve user
        try:
            # Decode the base64 encoded user ID
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {"detail": "Invalid reset link."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate the token
        if not default_token_generator.check_token(user, token):
            return Response(
                {"token": ["Invalid or expired reset link. Please request a new password reset."]},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate password strength using Django's validators
        try:
            validate_password(new_password1, user=user)
        except ValidationError as e:
            return Response(
                {"new_password2": list(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # All validations passed - set the new password
        user.set_password(new_password1)
        user.save()
        
        # Token is now automatically invalid because password hash changed
        
        return Response(
            {"detail": "Password has been reset successfully. You can now log in with your new password."},
            status=status.HTTP_200_OK
        )
