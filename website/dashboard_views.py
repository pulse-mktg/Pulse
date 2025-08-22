from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Avg, Count, F, Q, Case, When, Value, DecimalField, IntegerField, FloatField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from datetime import timedelta
import json
import calendar

from .models import (
    Tenant, Client, ClientGroup, Budget, PlatformConnection, ClientPlatformAccount,
    GoogleAdsCampaign, GoogleAdsMetrics, GoogleAdsDailyMetrics, CampaignTag, CampaignTagAssignment
)

@login_required
def agency_dashboard(request):
    """
    Main agency dashboard view showing aggregated data across all clients
    """
    # Get the selected tenant from session
    selected_tenant_id = request.session.get('selected_tenant_id')
    
    # Ensure a tenant is selected
    if not selected_tenant_id:
        messages.error(request, "Please select a tenant first.")
        return redirect('home')
    
    # Get the tenant and verify the user has access to it
    tenant = get_object_or_404(Tenant, id=selected_tenant_id, users=request.user)
    
    # Define date ranges
    today = timezone.now().date()
    period_end = today
    period_start = today - timedelta(days=30)
    comparison_end = period_start - timedelta(days=1)
    comparison_start = comparison_end - timedelta(days=30)
    
    # Get all active clients for this tenant
    active_clients = Client.objects.filter(tenant=tenant, is_active=True)
    
    # Get all platform accounts and campaigns for these clients
    client_platform_accounts = ClientPlatformAccount.objects.filter(
        client__in=active_clients,
        is_active=True
    )
    
    # Aggregate metrics for current period
    current_metrics = GoogleAdsMetrics.objects.filter(
        campaign__client_account__in=client_platform_accounts,
        date_start__gte=period_start,
        date_end__lte=period_end
    ).aggregate(
        # Explicitly set output fields for all aggregations
        total_impressions=Coalesce(Sum('impressions'), Value(0), output_field=IntegerField()),
        total_clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()),
        total_conversions=Coalesce(Sum('conversions'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
        total_cost=Coalesce(Sum('cost'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
    )
    
    # Aggregate metrics for comparison period
    comparison_metrics = GoogleAdsMetrics.objects.filter(
        campaign__client_account__in=client_platform_accounts,
        date_start__gte=comparison_start,
        date_end__lte=comparison_end
    ).aggregate(
        # Explicitly set output fields for all aggregations
        total_impressions=Coalesce(Sum('impressions'), Value(0), output_field=IntegerField()),
        total_clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()),
        total_conversions=Coalesce(Sum('conversions'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
        total_cost=Coalesce(Sum('cost'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
    )
    
    # Calculate changes - IMPORTANT: Explicitly convert all values to float before calculations
    total_impressions = int(current_metrics['total_impressions'] or 0)
    total_clicks = int(current_metrics['total_clicks'] or 0)
    total_conversions = float(current_metrics['total_conversions'] or 0)
    total_spend = float(current_metrics['total_cost'] or 0)
    
    comparison_impressions = int(comparison_metrics['total_impressions'] or 1)  # Avoid division by zero
    comparison_clicks = int(comparison_metrics['total_clicks'] or 1)
    comparison_conversions = float(comparison_metrics['total_conversions'] or 1)
    comparison_spend = float(comparison_metrics['total_cost'] or 1)
    
    # Be explicit about types in all calculations
    impressions_change = ((total_impressions - comparison_impressions) / comparison_impressions) * 100.0
    clicks_change = ((total_clicks - comparison_clicks) / comparison_clicks) * 100.0
    conversions_change = ((total_conversions - comparison_conversions) / comparison_conversions) * 100.0
    spend_change = ((total_spend - comparison_spend) / comparison_spend) * 100.0
    
    # Get daily performance data for charts
    daily_data = {}
    
    # Collect daily metrics for the last 30 days
    daily_metrics = GoogleAdsDailyMetrics.objects.filter(
        campaign__client_account__in=client_platform_accounts,
        date__gte=period_start,
        date__lte=period_end
    ).values('date').annotate(
        # Explicitly set output fields for all annotations
        day_impressions=Coalesce(Sum('impressions'), Value(0), output_field=IntegerField()),
        day_clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()),
        day_conversions=Coalesce(Sum('conversions'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
        day_cost=Coalesce(Sum('cost'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2))
    ).order_by('date')
    
    # Prepare chart data
    performance_dates = []
    performance_impressions = []
    performance_clicks = []
    performance_spend = []
    performance_conversions = []
    
    for metric in daily_metrics:
        date_str = metric['date'].strftime('%Y-%m-%d')
        performance_dates.append(date_str)
        performance_impressions.append(int(metric['day_impressions']))
        performance_clicks.append(int(metric['day_clicks']))
        performance_spend.append(float(metric['day_cost']))
        performance_conversions.append(float(metric['day_conversions']))
    
    # Get client performance data
    client_performance = []
    for client in active_clients:
        # Get client accounts
        accounts = client_platform_accounts.filter(client=client)
        
        # Skip clients with no accounts
        if not accounts.exists():
            continue
        
        # Get metrics for this client
        client_metrics = GoogleAdsMetrics.objects.filter(
            campaign__client_account__in=accounts,
            date_start__gte=period_start,
            date_end__lte=period_end
        ).aggregate(
            # Explicitly set output fields
            impressions=Coalesce(Sum('impressions'), Value(0), output_field=IntegerField()),
            clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()),
            conversions=Coalesce(Sum('conversions'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
            cost=Coalesce(Sum('cost'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
        )
        
        # Calculate CTR - be explicit about types
        impressions = int(client_metrics['impressions'] or 0)
        clicks = int(client_metrics['clicks'] or 0)
        ctr = (float(clicks) / float(impressions) * 100.0) if impressions > 0 else 0.0
        
        # Get active campaigns count
        active_campaigns = GoogleAdsCampaign.objects.filter(
            client_account__in=accounts
        ).count()
        
        # Get budget status
        client_budgets = Budget.objects.filter(
            Q(client=client) | Q(client_group__in=client.groups.all()),
            is_active=True
        )
        
        # Determine budget status (simple logic - can be enhanced)
        budget_status = 'on-track'
        if client_budgets.exists():
            # Calculate total budget - convert Decimal to float
            total_budget = sum(float(budget.amount) for budget in client_budgets)
            
            # Calculate expected spend
            total_days = 0
            expected_spend = 0.0
            
            for budget in client_budgets:
                budget_days = (budget.end_date - budget.start_date).days + 1
                elapsed_days = min(budget_days, (today - budget.start_date).days + 1)
                if elapsed_days > 0:
                    # Be explicit about floating point calculations
                    budget_expected = (float(budget.amount) * float(elapsed_days)) / float(budget_days)
                    expected_spend += budget_expected
                    total_days += 1
            
            # Compare actual to expected - be explicit about types
            actual_spend = float(client_metrics['cost'] or 0)
            if expected_spend > 0:
                variance = ((actual_spend / expected_spend) - 1.0) * 100.0
                if variance < -15:
                    budget_status = 'underspend'
                elif variance > 15:
                    budget_status = 'overspend'
        
        client_performance.append({
            'id': client.id,
            'name': client.name,
            'logo': client.logo,
            'impressions': impressions,
            'clicks': clicks,
            'conversions': float(client_metrics['conversions'] or 0),
            'spend': float(client_metrics['cost'] or 0),
            'ctr': ctr,
            'active_campaigns': active_campaigns,
            'budget_status': budget_status
        })
    
    # Sort client performance by spend (descending)
    client_performance.sort(key=lambda x: x['spend'], reverse=True)
    
    # Get platform distribution data
    platform_distribution = []
    platform_labels = []
    platform_values = []
    platform_colors = []
    platform_border_colors = []
    
    # Define colors for common platforms
    platform_color_map = {
        'google-ads': {
            'color': 'rgba(66, 133, 244, 0.8)', 
            'border': 'rgba(66, 133, 244, 1)',
            'icon': 'google'
        },
        'facebook-ads': {
            'color': 'rgba(59, 89, 152, 0.8)', 
            'border': 'rgba(59, 89, 152, 1)',
            'icon': 'facebook'
        },
        'linkedin-ads': {
            'color': 'rgba(0, 119, 181, 0.8)', 
            'border': 'rgba(0, 119, 181, 1)',
            'icon': 'linkedin'
        },
        'twitter-ads': {
            'color': 'rgba(29, 161, 242, 0.8)', 
            'border': 'rgba(29, 161, 242, 1)',
            'icon': 'twitter'
        },
        'microsoft-ads': {
            'color': 'rgba(0, 120, 215, 0.8)', 
            'border': 'rgba(0, 120, 215, 1)',
            'icon': 'microsoft'
        },
        'default': {
            'color': 'rgba(108, 117, 125, 0.8)', 
            'border': 'rgba(108, 117, 125, 1)',
            'icon': 'box'
        }
    }
    
    # Group accounts by platform and calculate spend
    platform_spend = {}
    
    for account in client_platform_accounts:
        platform_slug = account.platform_connection.platform_type.slug
        platform_name = account.platform_connection.platform_type.name
        
        # Get metrics for this account
        metrics = GoogleAdsMetrics.objects.filter(
            campaign__client_account=account,
            date_start__gte=period_start,
            date_end__lte=period_end
        ).aggregate(
            # Explicitly set output field
            cost=Coalesce(Sum('cost'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2))
        )
        
        spend = float(metrics['cost'] or 0)
        
        if platform_slug not in platform_spend:
            platform_spend[platform_slug] = {
                'name': platform_name,
                'slug': platform_slug,
                'spend': 0,
                'icon': platform_color_map.get(platform_slug, platform_color_map['default'])['icon']
            }
        
        platform_spend[platform_slug]['spend'] += spend
    
    # Calculate percentages and prepare chart data
    total_platform_spend = sum(platform['spend'] for platform in platform_spend.values())
    
    for slug, data in platform_spend.items():
        # Be explicit about floating point calculations
        percentage = (data['spend'] / total_platform_spend * 100.0) if total_platform_spend > 0 else 0.0
        platform_info = {
            'name': data['name'],
            'slug': slug,
            'spend': data['spend'],
            'percentage': percentage,
            'icon': data['icon'],
            'color': platform_color_map.get(slug, platform_color_map['default'])['color']
        }
        platform_distribution.append(platform_info)
        
        # Prepare chart data
        platform_labels.append(data['name'])
        platform_values.append(data['spend'])
        platform_colors.append(platform_color_map.get(slug, platform_color_map['default'])['color'])
        platform_border_colors.append(platform_color_map.get(slug, platform_color_map['default'])['border'])
    
    # Sort platforms by spend
    platform_distribution.sort(key=lambda x: x['spend'], reverse=True)
    
    # Get budget overview
    active_budgets = Budget.objects.filter(
        tenant=tenant,
        is_active=True,
        end_date__gte=today
    )
    
    total_budget = sum(float(budget.amount) for budget in active_budgets)
    budget_utilization = (total_spend / total_budget * 100.0) if total_budget > 0 else 0.0
    
    # Count budgets by status
    on_track_count = 0
    underspend_count = 0
    overspend_count = 0
    needs_attention = []
    
    for budget in active_budgets:
        # Calculate expected spend based on time elapsed
        days_elapsed = (today - budget.start_date).days + 1 if today >= budget.start_date else 0
        total_days = (budget.end_date - budget.start_date).days + 1
        # Cast explicitly to float 
        expected_spend = (float(budget.amount) * float(days_elapsed)) / float(total_days) if total_days > 0 and days_elapsed > 0 else 0.0
        
        # Get actual spend
        if budget.client:
            # Client-specific budget
            client_accounts = client_platform_accounts.filter(client=budget.client)
            metrics = GoogleAdsDailyMetrics.objects.filter(
                campaign__client_account__in=client_accounts,
                date__gte=budget.start_date,
                date__lte=min(today, budget.end_date)
            ).aggregate(
                # Explicitly set output field
                actual_spend=Coalesce(Sum('cost'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2))
            )
            actual_spend = float(metrics['actual_spend'] or 0)
            
            # Calculate variance - explicit floating point
            if expected_spend > 0:
                variance = ((actual_spend / expected_spend) - 1.0) * 100.0
                status = 'on-track'
                if variance < -15:
                    status = 'underspend'
                    underspend_count += 1
                    needs_attention.append({
                        'id': budget.client.id,
                        'name': budget.client.name,
                        'budget_status': 'underspend'
                    })
                elif variance > 15:
                    status = 'overspend'
                    overspend_count += 1
                    needs_attention.append({
                        'id': budget.client.id,
                        'name': budget.client.name,
                        'budget_status': 'overspend'
                    })
                else:
                    on_track_count += 1
        
        elif budget.client_group:
            # Group budget (simplified for brevity)
            on_track_count += 1
        
        else:
            # Tenant-wide budget
            on_track_count += 1
    
    # Get top performing campaigns
    top_campaigns = []
    campaigns = GoogleAdsCampaign.objects.filter(
        client_account__in=client_platform_accounts
    ).select_related('client_account__client')
    
    for campaign in campaigns:
        # Get metrics for this campaign
        metrics = GoogleAdsMetrics.objects.filter(
            campaign=campaign,
            date_start__gte=period_start,
            date_end__lte=period_end
        ).first()
        
        if metrics and float(metrics.conversions) > 0:
            # Calculate metrics - explicit casting
            conversions_val = float(metrics.conversions)
            clicks_val = int(metrics.clicks)
            cost_val = float(metrics.cost)
            
            conversion_rate = (conversions_val / clicks_val * 100.0) if clicks_val > 0 else 0.0
            cpa = cost_val / conversions_val if conversions_val > 0 else 0.0
            
            # Determine platform icon
            platform_slug = campaign.client_account.platform_connection.platform_type.slug
            platform_icon = platform_color_map.get(platform_slug, platform_color_map['default'])['icon']
            
            top_campaigns.append({
                'id': campaign.id,
                'name': campaign.name,
                'client_id': campaign.client_account.client.id,
                'client_name': campaign.client_account.client.name,
                'account_id': campaign.client_account.id,
                'conversions': conversions_val,
                'conversion_rate': conversion_rate,
                'cpa': cpa,
                'platform_icon': platform_icon
            })
    
    # Sort by conversions (descending) and limit to top 5
    top_campaigns.sort(key=lambda x: x['conversions'], reverse=True)
    top_campaigns = top_campaigns[:5]
    
    # Get recent activity (placeholder for now)
    recent_activity = [
        {
            'title': 'Budget threshold alert',
            'description': 'Client "ABC Corp" is approaching budget limit (85% used)',
            'timestamp': 'March 13, 2025',
            'type_color': 'danger',
            'type_icon': 'exclamation-triangle'
        },
        {
            'title': 'New campaign created',
            'description': 'Campaign "Spring Promotion 2025" created for client "XYZ Inc"',
            'timestamp': 'March 12, 2025',
            'type_color': 'primary',
            'type_icon': 'plus'
        },
        {
            'title': 'Performance improvement',
            'description': 'Campaign "Product Launch" conversion rate increased by 12%',
            'timestamp': 'March 11, 2025',
            'type_color': 'success',
            'type_icon': 'graph-up'
        },
        {
            'title': 'Sync completed',
            'description': 'Google Ads data synchronized for all clients',
            'timestamp': 'March 10, 2025',
            'type_color': 'info',
            'type_icon': 'arrow-repeat'
        }
    ]
    
    context = {
        'total_impressions': total_impressions,
        'total_clicks': total_clicks,
        'total_conversions': total_conversions,
        'total_spend': total_spend,
        'impressions_change': impressions_change,
        'clicks_change': clicks_change,
        'conversions_change': conversions_change,
        'spend_change': spend_change,
        'performance_dates': json.dumps(performance_dates),
        'performance_impressions': json.dumps(performance_impressions),
        'performance_clicks': json.dumps(performance_clicks),
        'performance_spend': json.dumps(performance_spend),
        'performance_conversions': json.dumps(performance_conversions),
        'client_performance': client_performance,
        'platform_distribution': platform_distribution,
        'platform_labels': json.dumps(platform_labels),
        'platform_values': json.dumps(platform_values),
        'platform_colors': json.dumps(platform_colors),
        'platform_border_colors': json.dumps(platform_border_colors),
        'total_budget': total_budget,
        'budget_utilization': budget_utilization,
        'on_track_count': on_track_count,
        'underspend_count': underspend_count,
        'overspend_count': overspend_count,
        'needs_attention': needs_attention,
        'top_campaigns': top_campaigns,
        'recent_activity': recent_activity,
        'page_title': 'Agency Dashboard'
    }
    
    return render(request, 'agency_dashboard.html', context)

from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Avg, Count, F, Q, Case, When, Value, DecimalField, IntegerField, FloatField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta, datetime
import json
import calendar

from .models import (
    Tenant, Client, ClientGroup, Budget, PlatformConnection, ClientPlatformAccount,
    GoogleAdsCampaign, GoogleAdsMetrics, GoogleAdsDailyMetrics
)

# Update the client_dashboard function
@login_required
@ensure_csrf_cookie
def client_dashboard(request, client_id):
    """
    Enhanced client dashboard view with performance metrics and visualizations
    """
    # Get the client and verify access
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    
    # Update session with correct tenant
    request.session['selected_tenant_id'] = client.tenant.id
    
    # Get URL parameters
    account_id = request.GET.get('account_id')
    date_range = request.GET.get('date_range', '7d')  # Default to last 7 days
    
    # Calculate date ranges based on the selected range
    today = timezone.now().date()
    
    if date_range == '7d':
        period_end = today
        period_start = today - timedelta(days=6)  # Last 7 days including today
        date_range_label = 'Last 7 Days'
    elif date_range == '30d':
        period_end = today
        period_start = today - timedelta(days=29)  # Last 30 days including today
        date_range_label = 'Last 30 Days'
    elif date_range == 'month':
        # Current month
        period_start = today.replace(day=1)
        period_end = today
        date_range_label = f'{today.strftime("%B %Y")}'
    elif date_range == 'last_month':
        # Previous month
        last_month = today.replace(day=1) - timedelta(days=1)
        period_start = last_month.replace(day=1)
        period_end = last_month.replace(day=calendar.monthrange(last_month.year, last_month.month)[1])
        date_range_label = f'{last_month.strftime("%B %Y")}'
    else:
        # Default to last 7 days
        period_end = today
        period_start = today - timedelta(days=6)
        date_range_label = 'Last 7 Days'
    
    # Calculate comparison period (same length, previous period)
    period_length = (period_end - period_start).days + 1
    comparison_end = period_start - timedelta(days=1)
    comparison_start = comparison_end - timedelta(days=period_length-1)
    
    # Get platform accounts
    platform_accounts = ClientPlatformAccount.objects.filter(
        client=client,
        is_active=True
    ).select_related(
        'platform_connection__platform_type'
    )
    
    # Filter by selected account if provided
    if account_id:
        selected_account = get_object_or_404(ClientPlatformAccount, id=account_id, client=client)
        accounts_to_query = [selected_account]
        selected_account_id = int(account_id)
    else:
        accounts_to_query = platform_accounts
        selected_account_id = None
    
    # Get all Google Ads accounts
    google_ads_accounts = platform_accounts.filter(
        platform_connection__platform_type__slug='google-ads'
    )
    
    # Get client groups this client belongs to
    client_groups = client.groups.filter(is_active=True)
    
    # Get client budgets
    client_budgets = Budget.objects.filter(
        Q(client=client) | Q(client_group__in=client_groups),
        is_active=True
    ).select_related('client', 'client_group')
    
    # Get campaigns for the selected account(s)
    campaigns = GoogleAdsCampaign.objects.filter(
        client_account__in=accounts_to_query
    ).select_related(
        'client_account'
    )
    
    # Fetch the latest metrics for each campaign
    for campaign in campaigns:
        # First try to get metrics for the specified date range
        metric = GoogleAdsMetrics.objects.filter(
            campaign=campaign,
            date_range='LAST_30_DAYS'  # Default to 30 days if no exact match
        ).first()
        
        if metric:
            # Directly attach metrics to campaign
            campaign.metrics_data = metric
        else:
            # Create empty metrics if none exist
            from types import SimpleNamespace
            campaign.metrics_data = SimpleNamespace(
                impressions=0,
                clicks=0,
                cost=0,
                conversions=0,
                ctr=0,
                avg_cpc=0,
                conversion_rate=0
            )
    
    # Get performance metrics for the selected account(s) in the selected period
    metrics = GoogleAdsMetrics.objects.filter(
        campaign__client_account__in=accounts_to_query,
        date_start__gte=period_start,
        date_end__lte=period_end
    ).aggregate(
        # Explicitly set output fields for all aggregations
        impressions=Coalesce(Sum('impressions'), Value(0), output_field=IntegerField()),
        clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()),
        conversions=Coalesce(Sum('conversions'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
        cost=Coalesce(Sum('cost'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
    )
    
    # Get comparison period metrics
    comparison_metrics = GoogleAdsMetrics.objects.filter(
        campaign__client_account__in=accounts_to_query,
        date_start__gte=comparison_start,
        date_end__lte=comparison_end
    ).aggregate(
        # Explicitly set output fields for all aggregations
        impressions=Coalesce(Sum('impressions'), Value(0), output_field=IntegerField()),
        clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()),
        conversions=Coalesce(Sum('conversions'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
        cost=Coalesce(Sum('cost'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
    )
    
    # Calculate changes - IMPORTANT: Explicitly convert all values to appropriate types
    impressions = int(metrics['impressions'] or 0)
    clicks = int(metrics['clicks'] or 0) 
    cost = float(metrics['cost'] or 0)
    conversions = float(metrics['conversions'] or 0)
    
    comparison_impressions = int(comparison_metrics['impressions'] or 1)  # Avoid division by zero
    comparison_clicks = int(comparison_metrics['clicks'] or 1)
    comparison_cost = float(comparison_metrics['cost'] or 1)
    comparison_conversions = float(comparison_metrics['conversions'] or 1)
    
    # Explicit type conversion for all calculations
    impressions_change = ((impressions - comparison_impressions) / comparison_impressions) * 100.0 if comparison_impressions > 0 else 0
    clicks_change = ((clicks - comparison_clicks) / comparison_clicks) * 100.0 if comparison_clicks > 0 else 0
    cost_change = ((cost - comparison_cost) / comparison_cost) * 100.0 if comparison_cost > 0 else 0
    conversions_change = ((conversions - comparison_conversions) / comparison_conversions) * 100.0 if comparison_conversions > 0 else 0
    
    # Calculate additional metrics - explicit type conversions
    ctr = (float(clicks) / float(impressions) * 100.0) if impressions > 0 else 0.0
    ctr_previous = (float(comparison_clicks) / float(comparison_impressions) * 100.0) if comparison_impressions > 0 else 0.0
    ctr_change = ((ctr - ctr_previous) / ctr_previous * 100.0) if ctr_previous > 0 else 0.0
    
    avg_cpc = (cost / clicks) if clicks > 0 else 0.0
    avg_cpc_previous = (comparison_cost / comparison_clicks) if comparison_clicks > 0 else 0.0
    avg_cpc_change = ((avg_cpc - avg_cpc_previous) / avg_cpc_previous * 100.0) if avg_cpc_previous > 0 else 0.0
    
    conversion_rate = (conversions / clicks * 100.0) if clicks > 0 else 0.0
    conversion_rate_previous = (comparison_conversions / comparison_clicks * 100.0) if comparison_clicks > 0 else 0.0
    conversion_rate_change = ((conversion_rate - conversion_rate_previous) / conversion_rate_previous * 100.0) if conversion_rate_previous > 0 else 0.0
    
    cpa = (cost / conversions) if conversions > 0 else 0.0
    cpa_previous = (comparison_cost / comparison_conversions) if comparison_conversions > 0 else 0.0
    cpa_change = ((cpa - cpa_previous) / cpa_previous * 100.0) if cpa_previous > 0 else 0.0
    
    # Get daily performance data for charts
    daily_metrics = GoogleAdsDailyMetrics.objects.filter(
        campaign__client_account__in=accounts_to_query,
        date__gte=period_start,
        date__lte=period_end
    ).values('date').annotate(
        # Explicit output fields
        day_impressions=Coalesce(Sum('impressions'), Value(0), output_field=IntegerField()),
        day_clicks=Coalesce(Sum('clicks'), Value(0), output_field=IntegerField()),
        day_conversions=Coalesce(Sum('conversions'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2)),
        day_cost=Coalesce(Sum('cost'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2))
    ).order_by('date')
    
    # Prepare chart data
    performance_dates = []
    performance_impressions = []
    performance_clicks = []
    performance_cost = []
    performance_conversions = []
    
    for metric in daily_metrics:
        date_str = metric['date'].strftime('%Y-%m-%d')
        performance_dates.append(date_str)
        performance_impressions.append(int(metric['day_impressions']))
        performance_clicks.append(int(metric['day_clicks']))
        performance_cost.append(float(metric['day_cost']))
        performance_conversions.append(float(metric['day_conversions']))
    
    # If there's no daily data, create a placeholder with zeros
    if not performance_dates:
        current_date = period_start
        while current_date <= period_end:
            date_str = current_date.strftime('%Y-%m-%d')
            performance_dates.append(date_str)
            performance_impressions.append(0)
            performance_clicks.append(0)
            performance_cost.append(0)
            performance_conversions.append(0)
            current_date += timedelta(days=1)
    
    context = {
        'client': client,
        'platform_accounts': platform_accounts,
        'google_ads_accounts': google_ads_accounts,
        'client_groups': client_groups,
        'client_budgets': client_budgets,
        'campaigns': campaigns,
        'selected_account_id': selected_account_id,
        'date_range': date_range,
        'date_range_label': date_range_label,
        
        # Performance metrics
        'impressions': impressions,
        'clicks': clicks,
        'conversions': conversions,
        'cost': cost,
        'ctr': ctr,
        'conversion_rate': conversion_rate,
        'avg_cpc': avg_cpc,
        'cpa': cpa,
        
        # Changes
        'impressions_change': impressions_change,
        'clicks_change': clicks_change,
        'conversions_change': conversions_change,
        'cost_change': cost_change,
        'ctr_change': ctr_change,
        'conversion_rate_change': conversion_rate_change,
        'avg_cpc_change': avg_cpc_change,
        'cpa_change': cpa_change,
        
        # Chart data
        'performance_dates': json.dumps(performance_dates),
        'performance_impressions': json.dumps(performance_impressions),
        'performance_clicks': json.dumps(performance_clicks),
        'performance_cost': json.dumps(performance_cost),
        'performance_conversions': json.dumps(performance_conversions),
        
        'page_title': f'{client.name} Dashboard',
        
        # Add all tags for the tenant to use in the tag modal
        'all_tags': CampaignTag.objects.filter(tenant=client.tenant).order_by('name')
    }

    # Add default values for charts if they don't exist in context
    if 'platform_colors' not in context:
        context['platform_colors'] = json.dumps(['rgba(66, 133, 244, 0.8)', 'rgba(59, 89, 152, 0.8)', 'rgba(0, 119, 181, 0.8)'])
    if 'platform_border_colors' not in context:
        context['platform_border_colors'] = json.dumps(['rgba(66, 133, 244, 1)', 'rgba(59, 89, 152, 1)', 'rgba(0, 119, 181, 1)'])
    if 'platform_labels' not in context:
        context['platform_labels'] = json.dumps([])
    if 'platform_data' not in context:
        context['platform_data'] = json.dumps([])
    if 'platform_distribution' not in context:
        context['platform_distribution'] = []
    if 'geo_performance' not in context:
        context['geo_performance'] = []
    if 'device_data' not in context:
        context['device_data'] = {
            'mobile': {'percentage': 0, 'clicks': 0, 'ctr': 0, 'conversion_rate': 0, 'cpc': 0, 'cpa': 0},
            'desktop': {'percentage': 0, 'clicks': 0, 'ctr': 0, 'conversion_rate': 0, 'cpc': 0, 'cpa': 0},
            'tablet': {'percentage': 0, 'clicks': 0, 'ctr': 0, 'conversion_rate': 0, 'cpc': 0, 'cpa': 0}
        }
    if 'recent_activity' not in context:
        context['recent_activity'] = []
    
    return render(request, 'client_dashboard.html', context)