"""
Views for Google Ads functionality
"""

import json
import logging
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie

from .models import Client, ClientPlatformAccount
from .models import GoogleAdsCampaign, GoogleAdsAdGroup, GoogleAdsMetrics, GoogleAdsDailyMetrics
from .services import GoogleAdsDataService



logger = logging.getLogger(__name__)

@login_required
@ensure_csrf_cookie
def google_ads_campaigns(request, client_id, account_id):
    """
    View to display Google Ads campaigns for a specific client account
    """
    # Get the client and account and verify user access
    client = get_object_or_404(Client, id=client_id, tenant__users=request.user)
    account = get_object_or_404(ClientPlatformAccount, id=account_id, client=client)
    
    # Set correct tenant in session
    request.session['selected_tenant_id'] = client.tenant.id
    
    # Get date range from query param, default to LAST_30_DAYS
    date_range = request.GET.get('date_range', 'LAST_30_DAYS')
    
    # Get campaigns for this account
    campaigns = GoogleAdsCampaign.objects.filter(
        client_account=account
    ).order_by('-metrics__impressions')
    
    # Get account summary metrics
    summary = {
        'impressions': 0,
        'clicks': 0,
        'ctr': 0,
        'cost': 0,
        'impressions_change': None,
        'clicks_change': None,
        'ctr_change': None,
        'cost_change': None
    }
    
    # Calculate summary stats
    for campaign in campaigns:
        campaign_metrics = campaign.metrics.filter(date_range=date_range).first()
        if campaign_metrics:
            summary['impressions'] += campaign_metrics.impressions
            summary['clicks'] += campaign_metrics.clicks
            summary['cost'] += float(campaign_metrics.cost)
            
            # Update changes if available
            if campaign_metrics.impressions_change is not None:
                if summary['impressions_change'] is None:
                    summary['impressions_change'] = 0
                summary['impressions_change'] += float(campaign_metrics.impressions_change)
            
            if campaign_metrics.clicks_change is not None:
                if summary['clicks_change'] is None:
                    summary['clicks_change'] = 0
                summary['clicks_change'] += float(campaign_metrics.clicks_change)
            
            if campaign_metrics.cost_change is not None:
                if summary['cost_change'] is None:
                    summary['cost_change'] = 0
                summary['cost_change'] += float(campaign_metrics.cost_change)
    
    # Calculate CTR for summary
    if summary['impressions'] > 0:
        summary['ctr'] = (summary['clicks'] / summary['impressions']) * 100
    
    # Prepare performance data for chart
    # Get daily data for all campaigns
    daily_data = GoogleAdsDailyMetrics.objects.filter(
        campaign__client_account=account
    ).order_by('date')
    
    dates = []
    impressions = []
    clicks = []
    cost = []
    
    # Group by date
    date_metrics = {}
    for metric in daily_data:
        date_str = metric.date.strftime('%Y-%m-%d')
        if date_str not in date_metrics:
            date_metrics[date_str] = {
                'impressions': 0,
                'clicks': 0,
                'cost': 0
            }
        
        date_metrics[date_str]['impressions'] += metric.impressions
        date_metrics[date_str]['clicks'] += metric.clicks
        date_metrics[date_str]['cost'] += float(metric.cost)
    
    # Sort dates
    sorted_dates = sorted(date_metrics.keys())
    
    # Prepare data for chart
    for date_str in sorted_dates:
        dates.append(date_str)
        impressions.append(date_metrics[date_str]['impressions'])
        clicks.append(date_metrics[date_str]['clicks'])
        cost.append(float(date_metrics[date_str]['cost']))
    
    # Create performance data JSON
    performance_data = json.dumps({
        'dates': dates,
        'impressions': impressions,
        'clicks': clicks,
        'cost': cost
    })
    
    context = {
        'client': client,
        'account': account,
        'campaigns': campaigns,
        'summary': summary,
        'date_range': date_range,
        'performance_data': performance_data
    }
    
    return render(request, 'google_ads_campaigns.html', context)

@login_required
def google_ads_campaign_detail(request, client_id, account_id, campaign_id):
    """
    View to display detailed information for a specific Google Ads campaign
    """
    # Get the client, account, and campaign and verify user access
    client = get_object_or_404(Client, id=client_id, tenant__users=request.user)
    account = get_object_or_404(ClientPlatformAccount, id=account_id, client=client)
    campaign = get_object_or_404(GoogleAdsCampaign, id=campaign_id, client_account=account)
    
    # Set correct tenant in session
    request.session['selected_tenant_id'] = client.tenant.id
    
    # Get date range from query param, default to LAST_30_DAYS
    date_range = request.GET.get('date_range', 'LAST_30_DAYS')
    
    # Get campaign metrics
    metrics = campaign.metrics.filter(date_range=date_range).first()
    campaign.metrics = metrics  # Attach metrics to campaign object directly
    
    # Get ad groups for this campaign
    ad_groups = GoogleAdsAdGroup.objects.filter(
        campaign=campaign
    ).order_by('-metrics__impressions')
    
    # Prepare daily performance data for chart
    daily_metrics = campaign.daily_metrics.all().order_by('date')
    
    dates = []
    impressions = []
    clicks = []
    cost = []
    
    for metric in daily_metrics:
        dates.append(metric.date.strftime('%Y-%m-%d'))
        impressions.append(metric.impressions)
        clicks.append(metric.clicks)
        cost.append(float(metric.cost))
    
    # Create daily performance JSON
    daily_performance = json.dumps({
        'dates': dates,
        'impressions': impressions,
        'clicks': clicks,
        'cost': cost
    })
    
    # Add budget information if the models exist
    campaign_budget_info = None
    try:
        from .models import Budget, BudgetAllocation
        import calendar
        from django.db.models import Sum
        
        # Add budget allocation information
        budget_allocations = BudgetAllocation.objects.filter(
            campaign=campaign,
            budget__is_active=True
        ).select_related('budget')
        
        # Get campaign budget info
        campaign_budget_info = {
            'allocations': budget_allocations,
            'has_custom_budgets': budget_allocations.exists()
        }
        
        # If no custom allocations, use campaign's own budget
        if not budget_allocations.exists() and campaign.budget_amount:
            today = timezone.now().date()
            days_in_month = calendar.monthrange(today.year, today.month)[1]
            monthly_budget = float(campaign.budget_amount) * days_in_month
            
            # Get month-to-date spend
            month_start = today.replace(day=1)
            month_spend_data = GoogleAdsDailyMetrics.objects.filter(
                campaign=campaign,
                date__gte=month_start,
                date__lte=today
            ).aggregate(total=Sum('cost'))
            month_spend = float(month_spend_data['total'] or 0)
            
            # Calculate pacing
            days_elapsed = (today - month_start).days + 1
            expected_spend = (monthly_budget / days_in_month) * days_elapsed
            pacing = (month_spend / expected_spend) * 100 if expected_spend else 0
            
            # Determine status
            budget_status = 'on-track'
            if pacing < 85:
                budget_status = 'underspend'
            elif pacing > 115:
                budget_status = 'overspend'
            
            campaign_budget_info.update({
                'campaign_budget': True,
                'daily_budget': campaign.budget_amount,
                'monthly_estimate': monthly_budget,
                'month_spend': month_spend,
                'pacing': pacing,
                'budget_status': budget_status
            })
    except ImportError:
        # Budget models don't exist yet
        logger.warning("Budget models not yet available")
        campaign_budget_info = None
    
    context = {
        'client': client,
        'account': account,
        'campaign': campaign,
        'ad_groups': ad_groups,
        'date_range': date_range,
        'daily_performance': daily_performance,
        'campaign_budget_info': campaign_budget_info
    }
    
    return render(request, 'google_ads_campaign_detail.html', context)
    """
    View to display detailed information for a specific Google Ads campaign
    """
    # Get the client, account, and campaign and verify user access
    client = get_object_or_404(Client, id=client_id, tenant__users=request.user)
    account = get_object_or_404(ClientPlatformAccount, id=account_id, client=client)
    campaign = get_object_or_404(GoogleAdsCampaign, id=campaign_id, client_account=account)
    
    # Set correct tenant in session
    request.session['selected_tenant_id'] = client.tenant.id
    
    # Get date range from query param, default to LAST_30_DAYS
    date_range = request.GET.get('date_range', 'LAST_30_DAYS')
    
    # Get campaign metrics
    metrics = campaign.metrics.filter(date_range=date_range).first()
    
    # Get ad groups for this campaign
    ad_groups = GoogleAdsAdGroup.objects.filter(
        campaign=campaign
    ).order_by('-metrics__impressions')
    
    # Prepare daily performance data for chart
    daily_metrics = campaign.daily_metrics.all().order_by('date')
    
    dates = []
    impressions = []
    clicks = []
    cost = []
    
    for metric in daily_metrics:
        dates.append(metric.date.strftime('%Y-%m-%d'))
        impressions.append(metric.impressions)
        clicks.append(metric.clicks)
        cost.append(float(metric.cost))
    
    # Create daily performance JSON
    daily_performance = json.dumps({
        'dates': dates,
        'impressions': impressions,
        'clicks': clicks,
        'cost': cost
    })
    
    context = {
        'client': client,
        'account': account,
        'campaign': campaign,
        'metrics': metrics,
        'ad_groups': ad_groups,
        'date_range': date_range,
        'daily_performance': daily_performance
    }
    
    return render(request, 'google_ads_campaign_detail.html', context)

@login_required
def sync_google_ads_data(request, client_id, account_id=None):
    """
    Sync Google Ads data for a specific account or all client accounts
    """
    # Get the client and verify access
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    
    # Get all Google Ads accounts for this client
    if account_id:
        accounts = ClientPlatformAccount.objects.filter(
            id=account_id,
            client=client,
            platform_connection__platform_type__slug='google-ads',
            is_active=True
        )
    else:
        accounts = ClientPlatformAccount.objects.filter(
            client=client,
            platform_connection__platform_type__slug='google-ads',
            is_active=True
        )
    
    if not accounts.exists():
        messages.error(request, "No Google Ads accounts found for this client.")
        return redirect('client_dashboard', client_id=client_id)
    
    # Initialize the data service with improved error handling
    try:
        from .services.google_ads_data import GoogleAdsDataService
        data_service = GoogleAdsDataService(client.tenant)
        
        # Track sync results
        success_count = 0
        failure_count = 0
        failure_messages = []
        
        # Sync each account
        for account in accounts:
            try:
                success, message = data_service.sync_client_account_data(account)
                if success:
                    success_count += 1
                else:
                    failure_count += 1
                    failure_messages.append(f"{account.platform_client_name}: {message}")
            except Exception as e:
                failure_count += 1
                failure_messages.append(f"{account.platform_client_name}: Unexpected error: {str(e)}")
                logger.error(f"Error syncing account {account.id}: {str(e)}")
                logger.error(traceback.format_exc())
        
        # Create user feedback
        if success_count > 0:
            messages.success(request, f"Successfully synced data for {success_count} Google Ads account(s).")
        
        if failure_count > 0:
            messages.error(request, f"Failed to sync {failure_count} account(s). Details: {'; '.join(failure_messages)}")
        
    except Exception as e:
        messages.error(request, f"Error initializing data service: {str(e)}")
        logger.error(f"Error in sync_google_ads_data: {str(e)}")
        logger.error(traceback.format_exc())
    
    # Redirect back to the dashboard with the appropriate filters
    if account_id:
        return redirect('client_dashboard', client_id=client_id)
    else:
        return redirect('client_dashboard', client_id=client_id)
