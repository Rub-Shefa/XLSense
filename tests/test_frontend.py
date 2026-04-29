import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestHomepageView:
    def test_homepage_loads(self, client):
        response = client.get(reverse("homepage"))
        assert response.status_code == 200

    def test_homepage_contains_hero_section(self, client):
        response = client.get(reverse("homepage"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Intelligent Data Workflow and Spreadsheet Automation Platform" in content

    def test_homepage_contains_features_section(self, client):
        response = client.get(reverse("homepage"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "Validation Engine" in content
        assert "AI Explanations" in content
        assert "Domain Templates" in content

    def test_homepage_has_register_link(self, client):
        response = client.get(reverse("homepage"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert reverse("register") in content

    def test_homepage_has_login_link(self, client):
        response = client.get(reverse("homepage"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert reverse("login") in content


@pytest.mark.django_db
class TestThemeSwitcher:
    def test_base_template_has_theme_switcher(self, authenticated_client):
        response = authenticated_client.get(reverse("dashboard"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "theme-cycle-btn" in content

    def test_base_template_has_fouc_script(self, client):
        response = client.get(reverse("login"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "xlsense-theme" in content
        assert "localStorage" in content


@pytest.mark.django_db
class TestLoginPage:
    def test_login_has_split_layout(self, client):
        response = client.get(reverse("login"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "split-container" in content
        assert "image-panel" in content
        assert "form-panel" in content

    def test_login_has_social_buttons(self, client):
        response = client.get(reverse("login"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "social-login" in content
        assert "Google" in content
        assert "Facebook" in content

    def test_login_has_register_link(self, client):
        response = client.get(reverse("login"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert reverse("register") in content


@pytest.mark.django_db
class TestRegisterPage:
    def test_register_has_split_layout(self, client):
        response = client.get(reverse("register"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "split-container" in content

    def test_register_has_login_link(self, client):
        response = client.get(reverse("register"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert reverse("login") in content


@pytest.mark.django_db
class TestBaseTemplate:
    def test_base_template_has_theme_switcher(self, authenticated_client):
        response = authenticated_client.get(reverse("dashboard"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "theme-cycle-btn" in content

    def test_base_template_has_home_link(self, authenticated_client):
        response = authenticated_client.get(reverse("dashboard"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert reverse("homepage") in content

    def test_base_template_theme_css_import(self, client):
        response = client.get(reverse("login"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "theme.css" in content


@pytest.mark.django_db
class TestDashboardTemplate:
    def test_dashboard_uses_card_class(
        self, authenticated_client, test_admin, test_template, db
    ):
        from django.contrib.auth.models import User

        User.objects.create_superuser(
            username="admin2", password="admin123", email="admin@test.com"
        )

        response = authenticated_client.get(reverse("dashboard"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "card" in content.lower()

    def test_dashboard_uses_theme_colors(self, authenticated_client, test_admin):
        response = authenticated_client.get(reverse("dashboard"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "var(--color" in content


@pytest.mark.django_db
class TestUploadHistoryTemplate:
    def test_upload_history_uses_theme(self, authenticated_client, test_uploaded_file):
        response = authenticated_client.get(reverse("upload_history"))
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "var(--color" in content or "card" in content.lower()


@pytest.mark.django_db
class TestReportTemplate:
    def test_report_uses_theme_colors(self, authenticated_client, test_uploaded_file):
        response = authenticated_client.get(
            reverse("validation_report", args=[test_uploaded_file.id])
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "var(--color" in content or "color-text" in content
