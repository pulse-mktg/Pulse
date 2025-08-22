# budget_service.py

from django.db.models import Sum
from django.utils import timezone
import datetime
import logging
from ..models import Budget, BudgetAlert, SpendSnapshot
from ..models import ClientPlatformAccount, GoogleAdsDailyMetrics

logger = logging.getLogger(__name__)

def process_daily_budget_snapshots():
    """
    Process all active budgets and create daily snapshots
    This should be run via a scheduled task (e.g., Celery)
    """
    today = timezone.now().date()
    logger.info(f"Processing budget snapshots for {today}")
    
    # Get all active budgets
    active_budgets = Budget.objects.filter(
        is_active=True,
        start_date__lte=today,
        end_date__gte=today
    )
    
    logger.info(f"Found {active_budgets.count()} active budgets")
    
    for budget in active_budgets:
        try:
            # Calculate actual spend
            actual_spend = calculate_budget_spend(budget, today)
            
            # Calculate expected spend
            days_elapsed = (today - budget.start_date).days + 1
            expected_spend = (budget.amount * days_elapsed) / budget.days_in_period
            
            # Calculate variance
            variance = actual_spend - expected_spend
            variance_percentage = ((actual_spend / expected_spend) * 100) - 100 if expected_spend else 0
            
            # Create or update snapshot
            snapshot, created = SpendSnapshot.objects.update_or_create(
                budget=budget,
                date=today,
                defaults={
                    'spend_amount': actual_spend,
                    'expected_amount': expected_spend,
                    'variance_amount': variance,
                    'variance_percentage': variance_percentage,
                    # Platform breakdown would be added here
                }
            )
            
            logger.info(f"Created snapshot for budget {budget.id}: ${actual_spend} spent, ${expected_spend} expected")
            
            # Process alerts
            process_budget_alerts(budget, actual_spend, expected_spend)
            
        except Exception as e:
            logger.error(f"Error processing budget {budget.id}: {str(e)}")


def calculate_budget_spend(budget, date):
    """Calculate the actual spend for a budget on a specific date"""
    # Define date range (budget start to the given date)
    start_date = budget.start_date
    end_date = min(date, budget.end_date)
    
    total_spend = 0
    
    # Get data based on budget type
    if budget.client:
        # Client budget
        platform_accounts = ClientPlatformAccount.objects.filter(
            client=budget.client,
            is_active=True
        )
        
        for account in platform_accounts:
            spend = get_account_spend(account, start_date, end_date)
            total_spend += spend
            
    elif budget.client_group:
        # Client group budget
        clients = budget.client_group.clients.filter(is_active=True)
        
        for client in clients:
            platform_accounts = ClientPlatformAccount.objects.filter(
                client=client,
                is_active=True
            )
            
            for account in platform_accounts:
                spend = get_account_spend(account, start_date, end_date)
                total_spend += spend
    else:
        # Tenant-wide budget
        platform_accounts = ClientPlatformAccount.objects.filter(
            client__tenant=budget.tenant,
            is_active=True
        )
        
        for account in platform_accounts:
            spend = get_account_spend(account, start_date, end_date)
            total_spend += spend
    
    return total_spend


def get_account_spend(account, start_date, end_date):
    """Get the spend for a specific account in the given date range"""
    # Handle different platform types
    if account.platform_connection.platform_type.slug == 'google-ads':
        # Get Google Ads spend
        metrics = GoogleAdsDailyMetrics.objects.filter(
            campaign__client_account=account,
            date__gte=start_date,
            date__lte=end_date
        ).aggregate(total_cost=Sum('cost'))
        
        return float(metrics['total_cost'] or 0)
    
    # For other platforms, add similar code here
    
    return 0


def process_budget_alerts(budget, actual_spend, expected_spend):
    """Process alerts for a budget"""
    # Get all active alerts for this budget
    alerts = BudgetAlert.objects.filter(
        budget=budget,
        is_active=True
    )
    
    spend_percentage = (actual_spend / budget.amount) * 100 if budget.amount else 0
    variance_percentage = ((actual_spend / expected_spend) * 100) - 100 if expected_spend else 0
    
    for alert in alerts:
        triggered = False
        
        # Check if the alert should be triggered
        if alert.alert_type == 'overspend' and variance_percentage > alert.threshold:
            triggered = True
        elif alert.alert_type == 'underspend' and variance_percentage < -alert.threshold:
            triggered = True
        elif alert.alert_type == 'forecast' and spend_percentage > alert.threshold:
            triggered = True
        
        if triggered:
            # Mark as triggered
            alert.last_triggered = timezone.now()
            alert.save(update_fields=['last_triggered'])
            
            # Send notifications
            if alert.is_email_enabled:
                send_alert_email(alert, actual_spend, expected_spend, spend_percentage)
            
            logger.info(f"Alert triggered for budget {budget.id}: {alert.get_alert_type_display()} at {alert.threshold}%")


def send_alert_email(alert, actual_spend, expected_spend, spend_percentage):
    """Send an email notification for a budget alert"""
    # Implementation will depend on your email sending configuration
    # This is a placeholder
    logger.info(f"Email alert would be sent to {alert.user.email} for budget {alert.budget.name}")
    pass