from django import forms
from django.contrib.auth.models import User


class SignupForm(forms.Form):
    name = forms.CharField(
        label="Name",
        max_length=150,
        strip=True,
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        strip=False,
    )

    def clean_name(self):
        name = self.cleaned_data["name"]
        if not name:
            raise forms.ValidationError("Enter a name.")
        if User.objects.filter(username=name).exists():
            raise forms.ValidationError("That name is already taken.")
        return name

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if password == "":
            raise forms.ValidationError("Enter a password.")
        return password

    def save(self):
        return User.objects.create_user(
            username=self.cleaned_data["name"],
            password=self.cleaned_data["password"],
        )
