from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    
    path('dashboard/', views.user_dashboard_view, name='user_dashboard'),
    path('admin/', views.admin_dashboard_view, name='admin_dashboard'),
    path('manage-templates/', views.manage_templates_view, name='manage_templates'),
]
