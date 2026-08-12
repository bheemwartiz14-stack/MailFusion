from django.http import JsonResponse
from django.core.management import call_command
from django.views.decorators.http import require_GET
import threading


def run_sync():
    try:
        call_command("sync")
    except Exception as e:
        print(f"Sync error: {e}")


@require_GET
def sync_api(request):
    thread = threading.Thread(target=run_sync, daemon=True)
    thread.start()
    return JsonResponse({
        "success": True,
        "message": "Sync started in background"
    })