import json
import os
import sys

import firebase_admin
from firebase_admin import credentials, messaging


def main():
    service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    device_token = os.environ.get("FCM_DEVICE_TOKEN")

    if not service_account_json:
        print("FCM ERROR NOTIFIER : missing FIREBASE_SERVICE_ACCOUNT_JSON")
        return 1

    if not device_token:
        print("FCM ERROR NOTIFIER : missing FCM_DEVICE_TOKEN")
        return 1

    try:
        service_account_info = json.loads(service_account_json)
    except json.JSONDecodeError as exc:
        print(f"FCM ERROR NOTIFIER : invalid service account JSON: {exc}")
        return 1

    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred)

        message = messaging.Message(
            notification=messaging.Notification(
                title="İndirimli Otomasyon Hatası",
                body="Otomatik veri işleminde beklenmeyen bir hata oluştu.",
            ),
            data={
                "type": "automation_error",
                "source": "github_actions",
            },
            token=device_token,
        )

        response = messaging.send(message)

        print("FCM ERROR NOTIFIER : PASS")
        print(f"Message ID : {response}")
        return 0

    except Exception as exc:
        print(f"FCM ERROR NOTIFIER : FAILED")
        print(f"Reason : {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
