from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from .models import CustomUser, ApprovalStatus


class UserApprovalEmailTest(TestCase):
    def test_approve_user_sends_approval_email(self):
        admin = CustomUser.objects.create_superuser(
            email='admin-test@example.com',
            password='TestPassword123!',
        )

        target = CustomUser.objects.create_user(
            email='approved-test@example.com',
            password='TestPassword123!',
            full_name='Approved Test User',
            approval_status=ApprovalStatus.PENDING,
            is_active=False,
        )

        self.client.force_login(admin)

        with patch('accounts.views.notifications.send_email') as mock_send_email:
            mock_send_email.return_value = (True, 'Sent successfully.')

            response = self.client.post(
                reverse('accounts:approve_user', kwargs={'user_id': target.id})
            )

        self.assertEqual(response.status_code, 302)

        target.refresh_from_db()
        self.assertEqual(target.approval_status, ApprovalStatus.APPROVED)
        self.assertTrue(target.is_active)

        mock_send_email.assert_called_once()

        args, kwargs = mock_send_email.call_args
        self.assertEqual(args[1], 'approved-test@example.com')
        self.assertEqual(args[2], 'Your DailyLedger account has been approved')
        self.assertEqual(kwargs['actor'], admin)
