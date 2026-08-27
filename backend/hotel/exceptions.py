from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    """Turn ProtectedError into a 409 instead of letting it become a 500.

    Deleting a department or role that still has people on it is a normal thing
    to try, so it deserves a real message rather than a stack trace.
    """
    if isinstance(exc, ProtectedError):
        blockers = sorted({obj._meta.verbose_name_plural.title() for obj in exc.protected_objects})
        return Response(
            {"detail": f"Still referenced by: {', '.join(blockers)}. Reassign them first."},
            status=status.HTTP_409_CONFLICT,
        )
    return exception_handler(exc, context)
