# In website/error_handlers.py
import logging
from django.shortcuts import render

logger = logging.getLogger(__name__)

def handler404(request, exception):
    """
    Custom 404 page not found handler
    """
    logger.warning(
        f"404 error at {request.path}",
        extra={
            'request_path': request.path,
            'request_method': request.method,
            'user_id': request.user.id if request.user.is_authenticated else None,
        }
    )
    return render(request, 'error_404.html', {'request_path': request.path}, status=404)

def handler500(request):
    """
    Custom 500 server error handler
    """
    # Error should already be logged by middleware, just render the template
    return render(request, 'error_500.html', status=500)

def handler403(request, exception):
    """
    Custom 403 permission denied handler
    """
    logger.warning(
        f"403 error at {request.path}",
        extra={
            'request_path': request.path,
            'request_method': request.method,
            'user_id': request.user.id if request.user.is_authenticated else None,
        }
    )
    return render(request, 'error_403.html', {'exception': str(exception)}, status=403)

def handler400(request, exception):
    """
    Custom 400 bad request handler
    """
    logger.warning(
        f"400 error at {request.path}",
        extra={
            'request_path': request.path,
            'request_method': request.method,
            'user_id': request.user.id if request.user.is_authenticated else None,
            'exception': str(exception),
        }
    )
    return render(request, 'error_400.html', {'exception': str(exception)}, status=400)