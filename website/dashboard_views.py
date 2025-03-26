from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Avg, Count, F, Q, Case, When, Value, DecimalField, IntegerField, FloatField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
import json
import calendar

from .models import (
    Tenant, Client, ClientGroup, Budget, PlatformConnection, ClientPlatformAccount,
    GoogleAdsCampaign, GoogleAdsMetrics, GoogleAdsDailyMetrics
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

@login_required
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
    
    # Define date ranges
    today = timezone.now().date()
    period_end = today
    period_start = today - timedelta(days=30)
    comparison_end = period_start - timedelta(days=1)
    comparison_start = comparison_end - timedelta(days=30)
    
    # Get platform accounts
    platform_accounts = ClientPlatformAccount.objects.filter(
        client=client,
        is_active=True
    ).select_related(
        'platform_connection__platform_type'
    )
    
    # Get client groups this client belongs to
    client_groups = client.groups.filter(is_active=True)
    
    # Get client budgets
    client_budgets = Budget.objects.filter(
        Q(client=client) | Q(client_group__in=client_groups),
        is_active=True
    ).select_related('client', 'client_group')
    
    # Get performance metrics for the client
    metrics = GoogleAdsMetrics.objects.filter(
        campaign__client_account__in=platform_accounts,
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
        campaign__client_account__in=platform_accounts,
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
    impressions_change = ((impressions - comparison_impressions) / comparison_impressions) * 100.0
    clicks_change = ((clicks - comparison_clicks) / comparison_clicks) * 100.0
    cost_change = ((cost - comparison_cost) / comparison_cost) * 100.0
    conversions_change = ((conversions - comparison_conversions) / comparison_conversions) * 100.0
    
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
        campaign__client_account__in=platform_accounts,
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
    
    # Get budget utilization data
    total_budget = 0.0
    total_spend = cost
    budget_data = []
    
    for budget in client_budgets:
        # Calculate budget utilization - explicit float conversion
        budget_amount = float(budget.amount)
        total_budget += budget_amount
        
        # Calculate days elapsed in budget period
        start_date = max(budget.start_date, period_start)
        end_date = min(budget.end_date, period_end)
        
        if start_date <= end_date:
            budget_days = (budget.end_date - budget.start_date).days + 1
            elapsed_days = (today - budget.start_date).days + 1 if today >= budget.start_date else 0
            elapsed_days = min(elapsed_days, budget_days)
            
            # Explicit float calculations
            expected_spend = (budget_amount * float(elapsed_days)) / float(budget_days) if budget_days > 0 else 0.0
            spent_percentage = (cost / budget_amount * 100.0) if budget_amount > 0 else 0.0
            expected_percentage = (expected_spend / budget_amount * 100.0) if budget_amount > 0 else 0.0
            
            # Determine status
            variance = ((cost / expected_spend) - 1.0) * 100.0 if expected_spend > 0 else 0.0
            status = 'on-track'
            if variance < -15:
                status = 'underspend'
            elif variance > 15:
                status = 'overspend'
            
            budget_data.append({
                'id': budget.id,
                'name': budget.name,
                'amount': budget_amount,
                'spent': cost,
                'expected': expected_spend,
                'spent_percentage': spent_percentage,
                'expected_percentage': expected_percentage,
                'variance': variance,
                'status': status,
                'start_date': budget.start_date,
                'end_date': budget.end_date,
                'days_elapsed': elapsed_days,
                'total_days': budget_days,
                'days_remaining': budget_days - elapsed_days
            })
    
    # Calculate overall budget utilization
    budget_utilization = (total_spend / total_budget * 100.0) if total_budget > 0 else 0.0
    
    # Get device performance data (placeholder for now)
    device_data = {
        'mobile': {
            'percentage': 64.2,
            'clicks': 5612,
            'ctr': 3.42,
            'conversion_rate': 3.85,
            'cpc': 1.38,
            'cpa': 35.84
        },
        'desktop': {
            'percentage': 23.8,
            'clicks': 2080,
            'ctr': 3.75,
            'conversion_rate': 4.52,
            'cpc': 1.58,
            'cpa': 34.95
        },
        'tablet': {
            'percentage': 12.0,
            'clicks': 1049,
            'ctr': 3.28,
            'conversion_rate': 3.72,
            'cpc': 1.35,
            'cpa': 36.29
        }
    }
    
    # Get platform distribution data
    platform_distribution = []
    platform_spend = {}
    
    for account in platform_accounts:
        platform_slug = account.platform_connection.platform_type.slug
        platform_name = account.platform_connection.platform_type.name
        
        # Get metrics for this account
        account_metrics = GoogleAdsMetrics.objects.filter(
            campaign__client_account=account,
            date_start__gte=period_start,
            date_end__lte=period_end
        ).aggregate(
            # Explicit output field
            account_cost=Coalesce(Sum('cost'), Value(0), output_field=DecimalField(max_digits=10, decimal_places=2))
        )
        
        account_spend = float(account_metrics['account_cost'] or 0)
        
        if platform_slug not in platform_spend:
            platform_spend[platform_slug] = {
                'name': platform_name,
                'slug': platform_slug,
                'spend': 0.0
            }
        
        platform_spend[platform_slug]['spend'] += account_spend
    
    # Calculate percentages - explicit float
    total_platform_spend = sum(platform['spend'] for platform in platform_spend.values())
    
    platform_labels = []
    platform_data = []
    platform_colors = []
    
    # Define colors for platforms
    platform_color_map = {
        'google-ads': 'rgba(66, 133, 244, 0.8)',
        'facebook-ads': 'rgba(59, 89, 152, 0.8)',
        'linkedin-ads': 'rgba(0, 119, 181, 0.8)',
        'twitter-ads': 'rgba(29, 161, 242, 0.8)',
        'default': 'rgba(108, 117, 125, 0.8)'
    }
    
    for slug, data in platform_spend.items():
        percentage = (data['spend'] / total_platform_spend * 100.0) if total_platform_spend > 0 else 0.0
        platform_distribution.append({
            'name': data['name'],
            'slug': slug,
            'spend': data['spend'],
            'percentage': percentage
        })
        
        platform_labels.append(data['name'])
        platform_data.append(data['spend'])
        platform_colors.append(platform_color_map.get(slug, platform_color_map['default']))
    
    # Get top performing campaigns
    campaigns = GoogleAdsCampaign.objects.filter(
        client_account__in=platform_accounts
    )
    
    top_campaigns = []
    for campaign in campaigns:
        # Get metrics for this campaign
        campaign_metrics = GoogleAdsMetrics.objects.filter(
            campaign=campaign,
            date_start__gte=period_start,
            date_end__lte=period_end
        ).first()
        
        if campaign_metrics:
            # Calculate derived metrics - explicit float conversion
            campaign_conversions = float(campaign_metrics.conversions or 0)
            campaign_clicks = int(campaign_metrics.clicks or 0)
            campaign_cost = float(campaign_metrics.cost or 0)
            
            conversion_rate = (campaign_conversions / campaign_clicks * 100.0) if campaign_clicks > 0 else 0.0
            cpa = (campaign_cost / campaign_conversions) if campaign_conversions > 0 else 0.0
            
            # Get platform info
            platform_slug = campaign.client_account.platform_connection.platform_type.slug
            platform_name = campaign.client_account.platform_connection.platform_type.name
            
            top_campaigns.append({
                'id': campaign.id,
                'name': campaign.name,
                'type': campaign.campaign_type or 'Standard',
                'platform_slug': platform_slug,
                'platform_name': platform_name,
                'status': campaign.status,
                'conversions': campaign_conversions,
                'conversion_rate': conversion_rate,
                'cost': campaign_cost,
                'cpa': cpa,
                'account_id': campaign.client_account.id
            })
    
    # Sort by conversions and limit to top 5
    top_campaigns.sort(key=lambda x: x['conversions'], reverse=True)
    top_campaigns = top_campaigns[:5]
    
    # Get geographic performance (placeholder data)
    geo_performance = [
        {'region': 'California', 'clicks': 1485, 'conversions': 68, 'conversion_rate': 4.58},
        {'region': 'New York', 'clicks': 1236, 'conversions': 53, 'conversion_rate': 4.29},
        {'region': 'Texas', 'clicks': 952, 'conversions': 41, 'conversion_rate': 4.31},
        {'region': 'Florida', 'clicks': 873, 'conversions': 39, 'conversion_rate': 4.47},
        {'region': 'Illinois', 'clicks': 712, 'conversions': 31, 'conversion_rate': 4.35},
        {'region': 'Others', 'clicks': 3483, 'conversions': 124, 'conversion_rate': 3.56}
    ]
    
    # Get recent activity (placeholder)
    recent_activity = [
        {
            'title': 'Budget threshold alert',
            'description': f'Campaign is approaching 90% of monthly budget',
            'timestamp': 'March 5, 2025',
            'type': 'budget',
            'icon': 'exclamation-triangle'
        },
        {
            'title': 'Campaign optimization implemented',
            'description': 'Bid adjustments and keyword optimizations for Search campaigns',
            'timestamp': 'March 1, 2025',
            'type': 'optimization',
            'icon': 'gear'
        },
        {
            'title': 'Performance improvement',
            'description': 'Conversion rate increased by 15% in the last 7 days',
            'timestamp': 'February 28, 2025',
            'type': 'performance',
            'icon': 'graph-up'
        },
        {
            'title': 'New campaign created',
            'description': 'Campaign "Spring Promotion 2025" created',
            'timestamp': 'February 25, 2025',
            'type': 'campaign',
            'icon': 'plus'
        }
    ]
    
    context = {
        'client': client,
        'platform_accounts': platform_accounts,
        'client_groups': client_groups,
        'client_budgets': client_budgets,
        'budget_data': budget_data,
        'budget_utilization': budget_utilization,
        'total_budget': total_budget,
        
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
        
        # Device data
        'device_data': device_data,
        
        # Platform distribution
        'platform_distribution': platform_distribution,
        'platform_labels': json.dumps(platform_labels),
        'platform_data': json.dumps(platform_data),
        'platform_colors': json.dumps(platform_colors),
        
        # Top campaigns
        'top_campaigns': top_campaigns,
        
        # Geographic performance
        'geo_performance': geo_performance,
        
        # Recent activity
        'recent_activity': recent_activity,
        
        'page_title': f'{client.name} Dashboard'
    }
    
    return render(request, 'client_dashboard.html', context)