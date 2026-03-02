from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard_home'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('manage-templates/', views.manage_templates_view, name='manage_templates'), # New path
]