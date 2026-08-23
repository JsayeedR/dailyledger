from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import CustomUser, SummaryFrequency


class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={'class': 'border rounded px-3 py-2 w-full'}),
    )
    password2 = forms.CharField(
        label=_('Confirm Password'),
        widget=forms.PasswordInput(attrs={'class': 'border rounded px-3 py-2 w-full'}),
    )

    class Meta:
        model = CustomUser
        fields = ['email', 'full_name']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'full_name': forms.TextInput(attrs={'class': 'border rounded px-3 py-2 w-full'}),
        }

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if CustomUser.objects.filter(email=email).exists():
            raise ValidationError(_('An account with this email already exists.'))
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError(_('Passwords do not match.'))
        if p1:
            validate_password(p1)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm


class StyledPasswordChangeForm(DjangoPasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'border rounded px-3 py-2 w-full'})


class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['full_name', 'email', 'phone_number', 'whatsapp_number', 'telegram_id']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'email': forms.EmailInput(attrs={'class': 'border rounded px-3 py-2 w-full'}),
            'phone_number': forms.TextInput(attrs={'class': 'border rounded px-3 py-2 w-full', 'placeholder': '+8801XXXXXXXXX'}),
            'whatsapp_number': forms.TextInput(attrs={'class': 'border rounded px-3 py-2 w-full', 'placeholder': '+8801XXXXXXXXX'}),
            'telegram_id': forms.TextInput(attrs={'class': 'border rounded px-3 py-2 w-full', 'placeholder': _('e.g. 123456789')}),
        }

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        qs = CustomUser.objects.filter(email=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(_('An account with this email already exists.'))
        return email


class NotificationPreferenceForm(forms.Form):
    frequencies = forms.MultipleChoiceField(
        choices=SummaryFrequency.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_('How often should we send you a summary? (pick any combination)'),
    )
    email_enabled = forms.BooleanField(required=False, label=_('Send via Email'))
    telegram_enabled = forms.BooleanField(required=False, label=_('Send via Telegram'))

    def clean(self):
        cleaned = super().clean()
        frequencies = cleaned.get('frequencies') or []
        email_enabled = cleaned.get('email_enabled')
        telegram_enabled = cleaned.get('telegram_enabled')
        if frequencies and not (email_enabled or telegram_enabled):
            raise ValidationError(_('Pick at least one channel (Email or Telegram) if you want summaries turned on.'))
        return cleaned
