from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.dashboard, name='home'),  # ✅ root now shows dashboard
    path('register/', views.accounts_register, name='register'),
    path('login/', views.accounts_login_page, name='login'),
    path('login_face/', views.accounts_login, name='login_face'),
    path('logout/', views.accounts_logout, name='logout'),
    path('verify_otp/', views.accounts_verify_otp, name='verify_otp'),
    path('verify_password/', views.accounts_verify_password, name='verify_password'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('transfer/', views.new_transfer, name='new_transfer'),
    path('cards/', views.cards_view, name='cards'),
    path('transfers/', views.transfers_view, name='transfers'),
    path('settings/', views.settings_view, name='settings'),
     path('home/', views.accounts_home, name='home'),
     path('reverify_face/', views.reverify_face, name='reverify_face'),
]
