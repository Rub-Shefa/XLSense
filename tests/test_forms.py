import pytest
from automation.forms import CustomUserCreationForm


@pytest.mark.django_db
class TestCustomUserCreationForm:
    def test_form_has_email_field(self):
        form = CustomUserCreationForm()
        assert "email" in form.fields

    def test_form_email_is_required(self):
        form = CustomUserCreationForm(
            data={
                "username": "newuser",
                "email": "",
                "password1": "TestPassword123!",
                "password2": "TestPassword123!",
            }
        )
        assert not form.is_valid()
        assert "email" in form.errors

    def test_form_valid_data(self):
        form = CustomUserCreationForm(
            data={
                "username": "newuser",
                "email": "newuser@example.com",
                "password1": "TestPassword123!",
                "password2": "TestPassword123!",
            }
        )
        assert form.is_valid(), form.errors

    def test_form_password_mismatch(self):
        form = CustomUserCreationForm(
            data={
                "username": "newuser",
                "email": "newuser@example.com",
                "password1": "TestPassword123!",
                "password2": "DifferentPassword123!",
            }
        )
        assert not form.is_valid()
        assert "password2" in form.errors

    def test_form_save_sets_email(self):
        form = CustomUserCreationForm(
            data={
                "username": "newuser",
                "email": "newuser@example.com",
                "password1": "TestPassword123!",
                "password2": "TestPassword123!",
            }
        )
        assert form.is_valid()
        user = form.save()
        assert user.email == "newuser@example.com"

    def test_form_email_widget_has_placeholder(self):
        form = CustomUserCreationForm()
        email_widget = form.fields["email"].widget
        assert "placeholder" in email_widget.attrs
        assert "Enter your email" in email_widget.attrs["placeholder"]

    def test_form_username_widget_has_placeholder(self):
        form = CustomUserCreationForm()
        username_widget = form.fields["username"].widget
        assert "placeholder" in username_widget.attrs
        assert "Username" in username_widget.attrs["placeholder"]

    def test_form_fields_have_form_control_class(self):
        form = CustomUserCreationForm()
        assert form.fields["username"].widget.attrs.get("class") == "form-control"
        assert form.fields["password1"].widget.attrs.get("class") == "form-control"
        assert form.fields["password2"].widget.attrs.get("class") == "form-control"
