"""
Background task service for handling async Google Ads operations
"""
import uuid
import logging
import threading
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from ..models import BackgroundTask, GoogleAdsDataFreshness, Tenant, Client

logger = logging.getLogger(__name__)


class BackgroundTaskService:
    """
    Service for managing background tasks without external queue systems
    """
    
    def __init__(self, tenant):
        self.tenant = tenant
    
    def create_task(self, task_type, parameters=None, created_by=None, estimated_duration=None):
        """
        Create a new background task
        
        Args:
            task_type: Type of task ('google_ads_sync', 'google_ads_backfill', etc.)
            parameters: Dict of task parameters
            created_by: User who created the task
            estimated_duration: Expected duration in seconds
            
        Returns:
            BackgroundTask instance
        """
        task_id = str(uuid.uuid4())
        
        task = BackgroundTask.objects.create(
            task_type=task_type,
            task_id=task_id,
            tenant=self.tenant,
            created_by=created_by,
            parameters=parameters or {},
            estimated_duration=estimated_duration
        )
        
        logger.info(f"Created background task {task_id} of type {task_type} for tenant {self.tenant.name}")
        return task
    
    def start_bulk_refresh_task(self, created_by, force_refresh=False, date_range_days=30):
        """
        Start a background bulk refresh task
        
        Args:
            created_by: User initiating the task
            force_refresh: Whether to ignore freshness checks
            date_range_days: Number of days to sync
            
        Returns:
            BackgroundTask instance
        """
        # Check if there's already a running task
        existing_task = BackgroundTask.objects.filter(
            tenant=self.tenant,
            task_type='bulk_refresh',
            status__in=['pending', 'running']
        ).first()
        
        if existing_task:
            logger.info(f"Bulk refresh task already running: {existing_task.task_id}")
            return existing_task
        
        # Create new task
        parameters = {
            'force_refresh': force_refresh,
            'date_range_days': date_range_days,
            'intelligent_refresh': not force_refresh
        }
        
        task = self.create_task(
            task_type='bulk_refresh',
            parameters=parameters,
            created_by=created_by,
            estimated_duration=300  # 5 minutes estimate
        )
        
        # Start task in background thread
        thread = threading.Thread(
            target=self._execute_bulk_refresh_task,
            args=(task,),
            daemon=True
        )
        thread.start()
        
        return task
    
    def start_backfill_task(self, created_by, start_date, end_date, client_ids=None):
        """
        Start a background backfill task for historical data
        
        Args:
            created_by: User initiating the task
            start_date: Start date for backfill
            end_date: End date for backfill  
            client_ids: List of specific client IDs (None for all)
            
        Returns:
            BackgroundTask instance
        """
        parameters = {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'client_ids': client_ids or []
        }
        
        task = self.create_task(
            task_type='google_ads_backfill',
            parameters=parameters,
            created_by=created_by,
            estimated_duration=600  # 10 minutes estimate
        )
        
        # Start task in background thread
        thread = threading.Thread(
            target=self._execute_backfill_task,
            args=(task,),
            daemon=True
        )
        thread.start()
        
        return task
    
    def _execute_bulk_refresh_task(self, task):
        """
        Execute bulk refresh task in background
        """
        try:
            task.start()
            
            from .performance_service import PerformanceDataService
            performance_service = PerformanceDataService(self.tenant)
            
            # Extract parameters
            force_refresh = task.parameters.get('force_refresh', False)
            date_range_days = task.parameters.get('date_range_days', 30)
            
            logger.info(f"Starting bulk refresh task {task.task_id} (force: {force_refresh})")
            
            # Update progress
            task.update_progress({
                'stage': 'initializing',
                'message': 'Preparing to sync Google Ads data...',
                'clients_processed': 0,
                'total_clients': 0
            })
            
            # Perform intelligent sync
            if force_refresh:
                sync_result = performance_service.sync_all_clients_performance_data()
            else:
                sync_result = performance_service.intelligent_sync_all_clients(
                    freshness_hours=24,
                    date_range_days=date_range_days
                )
            
            # Update final progress
            task.update_progress({
                'stage': 'completed',
                'message': 'Bulk refresh completed',
                'clients_processed': sync_result.get('clients_processed', 0),
                'total_clients': sync_result.get('total_clients', 0),
                'accounts_synced': sync_result.get('total_accounts_synced', 0),
                'accounts_failed': sync_result.get('total_accounts_failed', 0)
            })
            
            # Complete task
            task.complete(sync_result)
            
            logger.info(f"Bulk refresh task {task.task_id} completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Bulk refresh task {task.task_id} failed: {error_msg}")
            task.fail(error_msg)
    
    def _execute_backfill_task(self, task):
        """
        Execute backfill task in background
        """
        try:
            task.start()
            
            from .performance_service import PerformanceDataService
            performance_service = PerformanceDataService(self.tenant)
            
            # Extract parameters
            start_date = datetime.fromisoformat(task.parameters['start_date']).date()
            end_date = datetime.fromisoformat(task.parameters['end_date']).date()
            client_ids = task.parameters.get('client_ids', [])
            
            logger.info(f"Starting backfill task {task.task_id} from {start_date} to {end_date}")
            
            # Update progress
            task.update_progress({
                'stage': 'backfilling',
                'message': f'Backfilling data from {start_date} to {end_date}...',
                'date_start': start_date.isoformat(),
                'date_end': end_date.isoformat(),
                'progress_percent': 0
            })
            
            # Perform backfill
            backfill_result = performance_service.backfill_historical_data(
                start_date=start_date,
                end_date=end_date,
                client_ids=client_ids,
                progress_callback=lambda progress: task.update_progress({
                    'stage': 'backfilling',
                    'message': f'Backfilling data... {progress["progress_percent"]}% complete',
                    'progress_percent': progress['progress_percent'],
                    'current_date': progress.get('current_date', ''),
                    'clients_processed': progress.get('clients_processed', 0)
                })
            )
            
            # Update final progress
            task.update_progress({
                'stage': 'completed',
                'message': 'Backfill completed',
                'progress_percent': 100,
                'total_days_processed': backfill_result.get('total_days_processed', 0),
                'accounts_backfilled': backfill_result.get('accounts_backfilled', 0)
            })
            
            # Complete task
            task.complete(backfill_result)
            
            logger.info(f"Backfill task {task.task_id} completed successfully")
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Backfill task {task.task_id} failed: {error_msg}")
            task.fail(error_msg)
    
    def get_task_status(self, task_id):
        """
        Get current status of a background task
        
        Args:
            task_id: Task ID to check
            
        Returns:
            Dict with task status information
        """
        try:
            task = BackgroundTask.objects.get(
                task_id=task_id,
                tenant=self.tenant
            )
            
            return {
                'task_id': task.task_id,
                'task_type': task.task_type,
                'status': task.status,
                'progress': task.progress,
                'result': task.result,
                'error_message': task.error_message,
                'created_at': task.created_at.isoformat(),
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'duration_display': task.duration_display,
                'is_active': task.is_active,
                'is_completed': task.is_completed
            }
            
        except BackgroundTask.DoesNotExist:
            return {
                'error': 'Task not found',
                'task_id': task_id
            }
    
    def get_active_tasks(self):
        """
        Get all active tasks for the tenant
        
        Returns:
            List of active task information
        """
        active_tasks = BackgroundTask.objects.filter(
            tenant=self.tenant,
            status__in=['pending', 'running']
        )
        
        return [self.get_task_status(task.task_id) for task in active_tasks]
    
    def cancel_task(self, task_id):
        """
        Cancel a pending or running task
        
        Args:
            task_id: Task ID to cancel
            
        Returns:
            Boolean indicating success
        """
        try:
            task = BackgroundTask.objects.get(
                task_id=task_id,
                tenant=self.tenant,
                status__in=['pending', 'running']
            )
            
            task.status = 'cancelled'
            task.completed_at = timezone.now()
            task.error_message = 'Task cancelled by user'
            task.save(update_fields=['status', 'completed_at', 'error_message'])
            
            logger.info(f"Cancelled task {task_id}")
            return True
            
        except BackgroundTask.DoesNotExist:
            logger.warning(f"Cannot cancel task {task_id} - not found or not active")
            return False