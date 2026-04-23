from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import editor_views
from .views import download_excel_view
from .text_import_views import text_import_view, download_ai_excel


urlpatterns = [
    # Homepage
    path("", views.homepage_view, name="homepage"),
    # Authentication
    path("", views.login_view, name="login"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    # Dashboards
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("admin/", views.admin_dashboard_view, name="admin_dashboard"),
    path("audit-logs/", views.audit_logs_view, name="audit_logs"),
    path("system-stats/", views.admin_dashboard_view, name="admin_dashboard"),
    # Features
    path("manage-templates/", views.manage_templates_view, name="manage_templates"),
    path("upload/", views.upload_file_view, name="upload_file"),
    # History
    path("history/", views.upload_history_view, name="upload_history"),
    path("trash/", views.trash_view, name="trash"),
    # Report
    path(
        "report/<int:file_id>/", views.validation_report_view, name="validation_report"
    ),
    # AI Explain
    path("ai-explain/", views.ai_explain_view, name="ai_explain"),
    path("editor/", views.workbook_list_view, name="workbook_list"),
    path(
        "editor/<int:file_id>/",
        editor_views.workbook_editor_view,
        name="workbook_editor",
    ),
    path(
        "editor/<int:file_id>/save/",
        editor_views.save_workbook_data,
        name="save_workbook",
    ),
    path('validate-cell/', editor_views.validate_single_cell, name='validate_single_cell'),

    path('text-import/', text_import_view, name='text_import'),
    path('text-import/download/', download_ai_excel, name='download_ai_excel'),
]
urlpatterns += [
    path("download/<int:file_id>/", download_excel_view, name="download_excel"),
    path("preview/<int:file_id>/", views.preview_excel_view, name="preview_excel"),
    path("api/files/<int:file_id>/status/", views.delete_file_status_view, name="delete_file_status"),
]
