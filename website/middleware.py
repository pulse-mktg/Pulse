# In website/middleware.py
import logging
import traceback
from django.http import HttpResponseServerError
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)

class ErrorHandlingMiddleware:
    """
    Middleware to catch unhandled exceptions and provide proper error responses.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        """
        Process exceptions raised during request processing.
        """
        # Log the error with detailed information
        logger.error(
            f"Unhandled exception in {request.path}",
            exc_info=exception,
            extra={
                'request_path': request.path,
                'request_method': request.method,
                'user_id': request.user.id if request.user.is_authenticated else None,
                'tenant_id': request.session.get('selected_tenant_id'),
            }
        )

        # For API requests, return JSON error response
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({
                'status': 'error',
                'message': str(exception) if settings.DEBUG else 'An unexpected error occurred.',
                'detail': traceback.format_exc() if settings.DEBUG else None,
            }, status=500)

        # For regular requests, render error template
        try:
            context = {
                'exception': exception,
                'exception_type': exception.__class__.__name__,
                'traceback': traceback.format_exc() if settings.DEBUG else None,
                'request_path': request.path,
            }
            return HttpResponseServerError(
                render_to_string('error_500.html', context, request)
            )
        except:
            # Fallback if rendering the template fails
            return HttpResponseServerError("Internal Server Error", content_type='text/plain')