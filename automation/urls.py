from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import download_excel_view

urlpatterns = [
    # Authentication
    path("", views.login_view, name="login"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    # Dashboards
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("admin/", views.admin_dashboard_view, name="admin_dashboard"),
    path("system-stats/", views.admin_dashboard_view, name="admin_dashboard"),
    # Features
    path("manage-templates/", views.manage_templates_view, name="manage_templates"),
    path("upload/", views.upload_file_view, name="upload_file"),
    # History
    path("history/", views.upload_history_view, name="upload_history"),
    # Report
    path(
        "report/<int:file_id>/", views.validation_report_view, name="validation_report"
    ),
    # AI Explain
    path("ai-explain/", views.ai_explain_view, name="ai_explain"),
]
urlpatterns += [
    path('download/<int:file_id>/', download_excel_view, name='download_excel'),
    path("preview/<int:file_id>/", views.preview_excel_view, name="preview_excel"),
]