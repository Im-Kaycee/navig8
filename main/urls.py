from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import *

urlpatterns = [
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', RegisterView.as_view(), name = 'register'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('user/', UserDetailView.as_view(), name='user_detail'),
     path('password/reset/', 
         PasswordResetRequestView.as_view(), 
         name='password_reset'),
    
    path('password/reset/confirm/', 
         PasswordResetConfirmView.as_view(), 
         name='password_reset_confirm'),
]