# In website/utils/error_utils.py
import logging
import traceback
import functools
from django.http import JsonResponse

logger = logging.getLogger(__name__)

class ApiError(Exception):
    """Custom exception for API-related errors with status code"""
    def __init__(self, message, status_code=500, details=None):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)

def api_error_handler(view_func):
    """Decorator for handling API errors in views"""
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except ApiError as e:
            logger.warning(
                f"API Error in {view_func.__name__}: {str(e)}",
                extra={
                    'status_code': e.status_code,
                    'details': e.details,
                    'request_path': request.path,
                    'user_id': request.user.id if request.user.is_authenticated else None,
                }
            )
            return JsonResponse({
                'status': 'error',
                'message': e.message,
                'details': e.details
            }, status=e.status_code)
        except Exception as e:
            # Log unexpected errors
            logger.error(
                f"Unexpected error in {view_func.__name__}",
                exc_info=True,
                extra={
                    'request_path': request.path,
                    'user_id': request.user.id if request.user.is_authenticated else None,
                }
            )
            # Return generic error for non-API errors
            return JsonResponse({
                'status': 'error',
                'message': 'An unexpected error occurred'
            }, status=500)
    return wrapper

def handle_platform_error(platform, error, operation=None):
    """
    Handle and log platform-specific errors
    
    Args:
        platform (str): Platform name (e.g., 'google-ads')
        error (Exception): The exception that occurred
        operation (str, optional): Description of the operation being performed
        
    Returns:
        tuple: (error_message, error_details)
    """
    error_message = str(error)
    error_details = None
    
    # Extract platform-specific error details
    if platform == 'google-ads':
        if hasattr(error, 'failure') and hasattr(error.failure, 'errors'):
            error_details = [str(e) for e in error.failure.errors]
        elif hasattr(error, 'response') and hasattr(error.response, 'json'):
            try:
                error_details = error.response.json()
            except:
                pass
    
    # Log the error with contextual information
    logger.error(
        f"{platform} error during {operation or 'operation'}",
        exc_info=True,
        extra={
            'platform': platform,
            'operation': operation,
            'error_details': error_details,
            'traceback': traceback.format_exc()
        }
    )
    
    return error_message, error_details