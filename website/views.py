from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.views.decorators.csrf import ensure_csrf_cookie
from .models import Tenant, Client, PlatformType, PlatformConnection, ClientPlatformAccount, Budget, BudgetAlert, BudgetAllocation, SpendSnapshot, GoogleAdsDailyMetrics, GoogleAdsCampaign, Competitor, CampaignTag, CampaignTagAssignment
from .forms import SignUpForm, TenantForm, ClientForm, CompetitorForm
from django.utils import timezone
from django.conf import settings
from django.urls import reverse
from django.http import HttpResponseRedirect
import google.oauth2.credentials
import google_auth_oauthlib.flow
import logging
import os
import datetime
import json
import calendar

logger = logging.getLogger(__name__)
from django.http import JsonResponse
from .forms import PlatformSettingsForm, ClientGroup, ClientGroupForm, Budget, BudgetAlertForm, BudgetAlert, BudgetAllocation, BudgetAllocationForm, BudgetForm
from .services import get_platform_service
from django.db.models import Count, Q, Prefetch

@login_required
def home(request):
    """
    Home view with enhanced tenant and client management
    """
    # Initialize context
    context = {
        'total_clients_count': 0,
        'active_clients_count': 0,
        'all_clients': []
    }

    # Get all tenants for this user
    all_user_tenants = Tenant.objects.filter(users=request.user, is_active=True)

    # If user has no tenants, just return the empty context
    if not all_user_tenants.exists():
        return render(request, 'home.html', context)

    # Get selected tenant from session or use the first tenant
    selected_tenant_id = request.session.get('selected_tenant_id')
    
    # If no tenant is selected or the selected tenant isn't in the user's tenants,
    # select the first tenant
    selected_tenant = None
    if selected_tenant_id:
        try:
            selected_tenant = all_user_tenants.get(id=selected_tenant_id)
        except Tenant.DoesNotExist:
            selected_tenant = all_user_tenants.first()
            request.session['selected_tenant_id'] = selected_tenant.id
    else:
        selected_tenant = all_user_tenants.first()
        request.session['selected_tenant_id'] = selected_tenant.id

    # Now that we definitely have a selected tenant, get its clients
    if selected_tenant:
        # Prefetch groups and performance goals to avoid N+1 queries
        active_clients = Client.objects.filter(
            tenant_id=selected_tenant.id, 
            is_active=True
        ).prefetch_related(
            Prefetch('groups', queryset=ClientGroup.objects.filter(is_active=True)),
            'platform_accounts__google_ads_campaigns',
            'performance_goals'
        )
        
        # Use the new performance service for better data aggregation
        from .services.performance_service import PerformanceDataService
        performance_service = PerformanceDataService(selected_tenant)
        
        # Check for date range parameters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        
        if start_date and end_date:
            try:
                start_date_obj = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date_obj = datetime.datetime.strptime(end_date, '%Y-%m-%d').date()
                date_range_days = (end_date_obj - start_date_obj).days + 1
                clients_with_metrics = performance_service.get_all_clients_performance_data_for_range(
                    start_date_obj, end_date_obj
                )
            except ValueError:
                # Fallback to default if dates are invalid
                clients_with_metrics = performance_service.get_all_clients_performance_data(date_range_days=30)
        else:
            # Default to last 30 days
            clients_with_metrics = performance_service.get_all_clients_performance_data(date_range_days=30)
        
        # Count total clients separately to avoid fetching unnecessary data
        all_clients_count = Client.objects.filter(tenant_id=selected_tenant.id).count()
        
        # Update context with client data
        context['all_clients'] = clients_with_metrics
        context['total_clients_count'] = all_clients_count
        context['active_clients_count'] = len(clients_with_metrics)
        
        # Add the selected tenant and all user tenants to context
        context['selected_tenant'] = selected_tenant
        context['all_user_tenants'] = all_user_tenants
        
        # Get current date for display
        context['now'] = timezone.now()

    # Check if this is an AJAX request for refreshing data
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        # Log the AJAX request for debugging
        logger.info(f"AJAX request received for home view. Accept: {request.headers.get('Accept')}")
        
        try:
            # Return the full page HTML - the client will extract what it needs
            response = render(request, 'home.html', context)
            response['X-Ajax-Response'] = 'true'  # Add a header to identify this as an AJAX response
            return response
        except Exception as e:
            # Log any errors that occur during rendering
            logger.error(f"Error processing AJAX request: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'An error occurred while refreshing data'
            }, status=500)
    
    # For regular requests, return the full page
    return render(request, 'home.html', context)


@login_required
def bulk_refresh_google_ads_data(request):
    """
    API endpoint to start background bulk refresh of Google Ads data
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        
        if not selected_tenant_id:
            return JsonResponse({
                'success': False,
                'message': 'No tenant selected'
            }, status=400)
        
        # Get the tenant and verify user access
        try:
            tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user, is_active=True)
        except Tenant.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Tenant not found or access denied'
            }, status=403)
        
        # Parse request parameters
        force_refresh = request.POST.get('force_refresh', 'false').lower() == 'true'
        date_range_days = int(request.POST.get('date_range_days', 30))
        
        # Initialize background task service
        from .services.background_task_service import BackgroundTaskService
        task_service = BackgroundTaskService(tenant)
        
        logger.info(f"Starting background bulk refresh for tenant {tenant.name} (user: {request.user.username}, force: {force_refresh})")
        
        # Start background task
        task = task_service.start_bulk_refresh_task(
            created_by=request.user,
            force_refresh=force_refresh,
            date_range_days=date_range_days
        )
        
        logger.info(f"Background task created: {task.task_id}")
        
        # Return task information
        return JsonResponse({
            'success': True,
            'message': 'Background refresh started',
            'task_id': task.task_id,
            'task_status': task.status,
            'estimated_duration': task.estimated_duration,
            'force_refresh': force_refresh,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error starting background refresh: {error_msg}")
        
        return JsonResponse({
            'success': False,
            'message': f'Failed to start background refresh: {error_msg}',
            'timestamp': timezone.now().isoformat()
        }, status=500)


@login_required
def get_data_freshness_info(request):
    """
    API endpoint to get data freshness information for the current tenant
    """
    try:
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        # Get the tenant and verify user access
        try:
            tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user, is_active=True)
        except Tenant.DoesNotExist:
            return JsonResponse({'error': 'Tenant not found or access denied'}, status=403)
        
        # Get freshness info
        from .services.performance_service import PerformanceDataService
        performance_service = PerformanceDataService(tenant)
        freshness_info = performance_service.get_data_freshness_info()
        
        return JsonResponse({
            'success': True,
            'freshness_info': freshness_info,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting data freshness info: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@login_required
def get_task_status(request, task_id):
    """
    API endpoint to get background task status
    """
    try:
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        # Get the tenant and verify user access
        try:
            tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user, is_active=True)
        except Tenant.DoesNotExist:
            return JsonResponse({'error': 'Tenant not found or access denied'}, status=403)
        
        # Initialize background task service
        from .services.background_task_service import BackgroundTaskService
        task_service = BackgroundTaskService(tenant)
        
        # Get task status
        task_status = task_service.get_task_status(task_id)
        
        if 'error' in task_status:
            return JsonResponse(task_status, status=404)
        
        return JsonResponse({
            'success': True,
            'task': task_status,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting task status: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@login_required
def get_active_tasks(request):
    """
    API endpoint to get all active background tasks
    """
    try:
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        # Get the tenant and verify user access
        try:
            tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user, is_active=True)
        except Tenant.DoesNotExist:
            return JsonResponse({'error': 'Tenant not found or access denied'}, status=403)
        
        # Initialize background task service
        from .services.background_task_service import BackgroundTaskService
        task_service = BackgroundTaskService(tenant)
        
        # Get active tasks
        active_tasks = task_service.get_active_tasks()
        
        return JsonResponse({
            'success': True,
            'active_tasks': active_tasks,
            'count': len(active_tasks),
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting active tasks: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@login_required
def sync_client_data(request, client_id):
    """
    API endpoint to sync data for a specific client
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        # Get the tenant and verify user access
        try:
            tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user, is_active=True)
        except Tenant.DoesNotExist:
            return JsonResponse({'error': 'Tenant not found or access denied'}, status=403)
        
        # Get the client and verify it belongs to the tenant
        try:
            client = Client.objects.get(id=client_id, tenant=tenant, is_active=True)
        except Client.DoesNotExist:
            return JsonResponse({'error': 'Client not found or access denied'}, status=404)
        
        # Initialize performance service
        from .services.performance_service import PerformanceDataService
        performance_service = PerformanceDataService(tenant)
        
        # Sync the client data
        result = performance_service.sync_client_performance_data(client)
        
        return JsonResponse({
            'success': result['success'],
            'message': result['message'],
            'accounts_synced': result['accounts_synced'],
            'accounts_failed': result['accounts_failed'],
            'client_name': client.name,
            'timestamp': timezone.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error syncing client {client_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)


@login_required
def get_client_budget(request, client_id):
    """
    API endpoint to get budget information for a specific client with date range support
    """
    try:
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        # Get the tenant and verify user access
        try:
            tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user, is_active=True)
        except Tenant.DoesNotExist:
            return JsonResponse({'error': 'Tenant not found or access denied'}, status=403)
        
        # Get the client and verify it belongs to the tenant
        try:
            client = Client.objects.get(id=client_id, tenant=tenant, is_active=True)
        except Client.DoesNotExist:
            return JsonResponse({'error': 'Client not found or access denied'}, status=404)
        
        # Parse date range parameters
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        range_type = request.GET.get('range_type', 'last_30_days')
        
        # Default to current date if no range provided
        if not start_date_str or not end_date_str:
            end_date = timezone.now().date()
            start_date = end_date - datetime.timedelta(days=30)
        else:
            try:
                start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'error': 'Invalid date format'}, status=400)
        
        # Get all budgets that overlap with the selected date range
        overlapping_budgets = Budget.objects.filter(
            client=client,
            is_active=True,
            start_date__lte=end_date,
            end_date__gte=start_date
        ).order_by('start_date')
        
        if overlapping_budgets.exists():
            # Calculate pro-rated budget amounts and spending for the selected date range
            total_budget_amount = 0
            total_expected_spend = 0
            total_actual_spend = 0
            budget_details = []
            
            for budget in overlapping_budgets:
                # Calculate overlap dates
                overlap_start = max(budget.start_date, start_date)
                overlap_end = min(budget.end_date, end_date)
                overlap_days = (overlap_end - overlap_start).days + 1
                
                if overlap_days <= 0:
                    continue
                
                # Calculate pro-rated budget amount for this overlap period
                budget_total_days = (budget.end_date - budget.start_date).days + 1
                prorated_budget = (float(budget.amount) * overlap_days) / budget_total_days
                
                # Calculate expected spend for this period
                days_elapsed_in_overlap = min(overlap_days, (timezone.now().date() - overlap_start).days + 1)
                days_elapsed_in_overlap = max(0, days_elapsed_in_overlap)
                expected_spend_for_period = (prorated_budget * days_elapsed_in_overlap) / overlap_days
                
                # Calculate actual spend for this overlap period
                actual_spend_for_period = calculate_spend_for_date_range(client, overlap_start, overlap_end)
                
                total_budget_amount += prorated_budget
                total_expected_spend += expected_spend_for_period
                total_actual_spend += actual_spend_for_period
                
                budget_details.append({
                    'budget_id': budget.id,
                    'budget_name': budget.name,
                    'frequency': budget.frequency,
                    'overlap_start': overlap_start.isoformat(),
                    'overlap_end': overlap_end.isoformat(),
                    'overlap_days': overlap_days,
                    'prorated_budget': round(prorated_budget, 2),
                    'expected_spend': round(expected_spend_for_period, 2),
                    'actual_spend': round(actual_spend_for_period, 2)
                })
            
            # Calculate percentages and pacing
            spend_percentage = (total_actual_spend / total_budget_amount) * 100 if total_budget_amount else 0
            expected_percentage = (total_expected_spend / total_budget_amount) * 100 if total_budget_amount else 0
            
            # Determine pacing status
            if spend_percentage <= expected_percentage * 1.1:
                pacing_status = 'on-pace'
            elif spend_percentage <= expected_percentage * 1.3:
                pacing_status = 'behind-pace'
            else:
                pacing_status = 'over-pace'
            
            return JsonResponse({
                'success': True,
                'has_budget': True,
                'date_range': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'range_type': range_type
                },
                'budget': {
                    'total_budget_amount': round(total_budget_amount, 2),
                    'current_spend': round(total_actual_spend, 2),
                    'expected_spend': round(total_expected_spend, 2),
                    'spend_percentage': round(spend_percentage, 1),
                    'expected_percentage': round(expected_percentage, 1),
                    'pacing_status': pacing_status,
                    'budget_details': budget_details
                }
            })
        else:
            return JsonResponse({
                'success': True,
                'has_budget': False,
                'date_range': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'range_type': range_type
                },
                'message': 'No budgets found for the selected date range'
            })
        
    except Exception as e:
        logger.error(f"Error getting budget for client {client_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def set_client_budget(request, client_id):
    """
    API endpoint to set budget for a specific client using existing Budget model
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        # Get the tenant and verify user access
        try:
            tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user, is_active=True)
        except Tenant.DoesNotExist:
            return JsonResponse({'error': 'Tenant not found or access denied'}, status=403)
        
        # Get the client and verify it belongs to the tenant
        try:
            client = Client.objects.get(id=client_id, tenant=tenant, is_active=True)
        except Client.DoesNotExist:
            return JsonResponse({'error': 'Client not found or access denied'}, status=404)
        
        # Parse the budget data from request
        try:
            data = json.loads(request.body)
            budget_amount = float(data.get('budget', 0))
            frequency = data.get('frequency', 'monthly')
            
            if budget_amount <= 0:
                return JsonResponse({'error': 'Budget must be greater than 0'}, status=400)
        except (json.JSONDecodeError, ValueError, TypeError):
            return JsonResponse({'error': 'Invalid budget data'}, status=400)
        
        # Calculate date range based on frequency
        current_date = timezone.now().date()
        
        if frequency == 'monthly':
            start_date = current_date.replace(day=1)
            # Calculate end of month
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - datetime.timedelta(days=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1, day=1) - datetime.timedelta(days=1)
        elif frequency == 'quarterly':
            # Calculate start of quarter
            quarter_start_month = ((current_date.month - 1) // 3) * 3 + 1
            start_date = current_date.replace(month=quarter_start_month, day=1)
            # Calculate end of quarter
            end_month = quarter_start_month + 2
            if end_month > 12:
                end_date = start_date.replace(year=start_date.year + 1, month=end_month - 12, day=1) - datetime.timedelta(days=1)
            else:
                end_date = start_date.replace(month=end_month + 1, day=1) - datetime.timedelta(days=1)
        else:
            # Default to monthly
            start_date = current_date.replace(day=1)
            end_date = start_date.replace(month=start_date.month + 1, day=1) - datetime.timedelta(days=1)
        
        # Check if there's already an active budget for this period
        existing_budget = Budget.objects.filter(
            client=client,
            tenant=tenant,
            is_active=True,
            start_date__lte=current_date,
            end_date__gte=current_date
        ).first()
        
        if existing_budget:
            # Update existing budget
            existing_budget.amount = budget_amount
            existing_budget.frequency = frequency
            existing_budget.save()
            budget = existing_budget
            action = 'updated'
        else:
            # Create new budget
            budget = Budget.objects.create(
                tenant=tenant,
                client=client,
                name=f"{client.name} - {current_date.strftime('%B %Y')} Budget",
                amount=budget_amount,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                created_by=request.user
            )
            action = 'created'
        
        return JsonResponse({
            'success': True,
            'message': f'Budget of ${budget_amount:,.2f} {action} for {client.name}',
            'budget': {
                'id': budget.id,
                'amount': float(budget.amount),
                'start_date': budget.start_date.isoformat(),
                'end_date': budget.end_date.isoformat(),
                'frequency': budget.frequency
            },
            'action': action
        })
        
    except Exception as e:
        logger.error(f"Error setting budget for client {client_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def switch_tenant(request, tenant_id):
    """
    View to handle switching between tenants
    """
    # Ensure the user has access to the tenant
    tenant = get_object_or_404(Tenant, id=tenant_id, users=request.user)
    
    # Store the selected tenant in session
    request.session['selected_tenant_id'] = tenant_id
    
    # Redirect back to home
    return redirect('home')

def login_user(request):
    """Handle user login"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            
            # After successful login, set up the default tenant
            user_tenants = Tenant.objects.filter(users=user, is_active=True)
            if user_tenants.exists():
                # Set the first tenant as selected if none is already selected
                if not request.session.get('selected_tenant_id'):
                    request.session['selected_tenant_id'] = user_tenants.first().id
            
            return redirect('home')
        else:
            messages.error(request, "Invalid username or password.")
    
    return render(request, 'login.html')

def logout_user(request):
    """Handle user logout"""
    logout(request)
    return redirect('login')

def register_user(request):
    """Handle user registration with automatic tenant creation"""
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            # Save the user
            user = form.save()
            username = form.cleaned_data['username']
            password = form.cleaned_data['password1']
            
            # Create a tenant for the new user using their first/last name or username
            tenant_name = f"{form.cleaned_data['first_name']} {form.cleaned_data['last_name']}".strip()
            if not tenant_name:
                tenant_name = username
                
            # Create the tenant and associate it with the user
            tenant = Tenant.objects.create(name=f"{tenant_name}'s Agency")
            tenant.users.add(user)
            
            # Set the newly created tenant as the selected tenant in session
            request.session['selected_tenant_id'] = tenant.id
            
            # Authenticate and log in the user
            authenticated_user = authenticate(username=username, password=password)
            login(request, authenticated_user)
            
            messages.success(request, "You have registered successfully! We've created your agency account.")
            return redirect('home')
    else:
        form = SignUpForm()
        
    return render(request, 'register.html', {'form': form})

@staff_member_required(login_url='login')
def create_tenant(request):
    """
    View for creating a new tenant (admin-only)
    """
    if request.method == 'POST':
        form = TenantForm(request.POST, request.FILES)
        if form.is_valid():
            # Save the tenant and associate the current user
            tenant = form.save(created_by=request.user)
            
            # Set the new tenant as the selected tenant in session
            request.session['selected_tenant_id'] = tenant.id
            
            messages.success(request, f"Tenant '{tenant.name}' created successfully!")
            return redirect('home')
    else:
        form = TenantForm()
    
    context = {
        'form': form,
        'page_title': 'Create New Tenant'
    }
    return render(request, 'create_tenant.html', context)
@login_required
def create_client(request):
    """
    View for creating a new client under the selected tenant
    """
    # Get the selected tenant from session
    selected_tenant_id = request.session.get('selected_tenant_id')
    
    # Ensure a tenant is selected
    if not selected_tenant_id:
        messages.error(request, "Please select a tenant first.")
        return redirect('home')
    
    # Get the tenant and verify the user has access to it
    tenant = get_object_or_404(Tenant, id=selected_tenant_id, users=request.user)
    
    if request.method == 'POST':
        form = ClientForm(request.POST, request.FILES)
        if form.is_valid():
            # Create client but don't save to DB yet
            client = form.save(commit=False)
            # Associate with the tenant
            client.tenant = tenant
            # Now save to DB
            client.save()
            
            messages.success(request, f"Client '{client.name}' created successfully!")
            return redirect('home')
    else:
        form = ClientForm()
    
    context = {
        'form': form,
        'tenant': tenant,
        'page_title': 'Create New Client'
    }
    return render(request, 'create_client.html', context)

@login_required
def client_detail(request, client_id):
    """
    View for viewing client details with optimized database queries.
    Includes platform connections, client groups, budgets, and competitors.
    """
    # Use select_related to fetch tenant in the same query
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    
    # Make sure the session has the correct tenant selected
    request.session['selected_tenant_id'] = client.tenant.id
    
    # Get all platform accounts for this client (both active and inactive)
    # - select_related fetches the related objects in a single query
    client_platform_accounts = ClientPlatformAccount.objects.filter(
        client=client
    ).select_related(
        'platform_connection', 
        'platform_connection__platform_type',
        'platform_connection__connected_user'
    )
    
    # Get only active platform accounts for the dashboard section
    active_platform_accounts = [account for account in client_platform_accounts if account.is_active]
    
    # Group accounts by platform type, with active accounts first
    grouped_accounts = {}
    for account in sorted(client_platform_accounts, key=lambda x: (not x.is_active, x.platform_client_name)):
        platform_type = account.platform_connection.platform_type
        if platform_type.slug not in grouped_accounts:
            grouped_accounts[platform_type.slug] = {
                'platform_type': platform_type,
                'accounts': []
            }
        grouped_accounts[platform_type.slug]['accounts'].append(account)
    
    # Get only active groups that this client belongs to
    # - prefetch_related optimizes the many-to-many relationship
    active_client_groups = client.groups.filter(
        is_active=True
    ).prefetch_related('clients')
    
    # Get client budgets (direct and from groups)
    from django.db.models import Q
    client_budgets = Budget.objects.filter(
        Q(client=client) | Q(client_group__in=active_client_groups),
        is_active=True
    ).select_related('client', 'client_group').order_by('end_date')[:5]  # Limit to 5 most recent
    
    # Get client competitors
    competitors = Competitor.objects.filter(
        client=client,
        is_active=True
    ).order_by('name')
    
    # Check for custom and auto-generated groups
    has_custom_groups = active_client_groups.filter(is_auto_generated=False).exists()
    has_auto_groups = active_client_groups.filter(is_auto_generated=True).exists()
    
    # Check if tenant has Google Ads connections
    # Using a more efficient query with exists()
    has_google_ads_connection = PlatformConnection.objects.filter(
        tenant=client.tenant,
        platform_type__slug='google-ads',
        is_active=True
    ).exists()
    
    # Get the Google Ads connection for the tenant if it exists
    google_ads_connection = None
    if has_google_ads_connection:
        google_ads_connection = PlatformConnection.objects.filter(
            tenant=client.tenant,
            platform_type__slug='google-ads',
            is_active=True
        ).first()
    
    # Get available platform types for this tenant
    available_platforms = PlatformType.objects.filter(
        is_available=True
    ).order_by('position', 'name')
    
    # Check which platforms are connected for this tenant
    # Use values_list() to fetch only the ids we need
    connected_platform_ids = PlatformConnection.objects.filter(
        tenant=client.tenant,
        is_active=True
    ).values_list('platform_type_id', flat=True)
    
    # Prepare the platforms with connection status
    tenant_platforms = []
    for platform in available_platforms:
        is_connected = platform.id in connected_platform_ids
        
        # Check if client has accounts for this platform
        has_client_accounts = any(
            account.platform_connection.platform_type_id == platform.id 
            for account in active_platform_accounts
        )
        
        tenant_platforms.append({
            'id': platform.id,
            'name': platform.name,
            'slug': platform.slug,
            'description': platform.description,
            'icon_class': platform.icon_class,
            'is_connected': is_connected,
            'has_client_accounts': has_client_accounts
        })
    
    # Check if we have any accounts directly
    has_accounts = client_platform_accounts.exists()
    
    # Get Google Ads platform type for the add account button
    google_ads_platform_type = None
    try:
        google_ads_platform_type = PlatformType.objects.get(slug='google-ads')
    except PlatformType.DoesNotExist:
        pass
    
    context = {
        'client': client,
        'active_client_groups': active_client_groups,
        'has_custom_groups': has_custom_groups,
        'has_auto_groups': has_auto_groups,
        'grouped_accounts': grouped_accounts,
        'has_google_ads_connection': has_google_ads_connection,
        'google_ads_connection': google_ads_connection,
        'has_accounts': has_accounts,
        'platform_accounts': active_platform_accounts,
        'client_groups': active_client_groups,
        'client_budgets': client_budgets,
        'competitors': competitors,
        'tenant_platforms': tenant_platforms,
        'google_ads_platform_type': google_ads_platform_type,
        'page_title': client.name
    }
    return render(request, 'client_detail.html', context)

@login_required
def edit_client(request, client_id):
    """
    View for editing an existing client
    """
    # Get the client and verify the user has access through the tenant
    # Use select_related to fetch tenant in the same query
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    
    # Make sure the session has the correct tenant selected
    request.session['selected_tenant_id'] = client.tenant.id
    
    if request.method == 'POST':
        form = ClientForm(request.POST, request.FILES, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, f"Client '{client.name}' updated successfully!")
            return redirect('client_detail', client_id=client.id)
    else:
        form = ClientForm(instance=client)
    
    context = {
        'form': form,
        'client': client,
        'page_title': f'Edit {client.name}'
    }
    return render(request, 'edit_client.html', context)

@login_required
def archive_client(request, client_id):
    """
    View for archiving (soft-deleting) a client
    """
    # Get the client and verify the user has access through the tenant
    client = get_object_or_404(Client, id=client_id, tenant__users=request.user)
    
    # Soft delete by setting is_active to False and recording archive timestamp
    client.is_active = False
    client.archived_at = timezone.now()
    client.save(update_fields=['is_active', 'archived_at'])  # Only update necessary fields
    
    messages.success(request, f"Client '{client.name}' has been archived.")
    return redirect('home')

@login_required
def archived_clients_api(request):
    """API endpoint to get archived clients for the selected tenant"""
    # Get the selected tenant from session
    selected_tenant_id = request.session.get('selected_tenant_id')
    
    if not selected_tenant_id:
        return JsonResponse({'status': 'error', 'message': 'No tenant selected'})
    
    # Get the tenant and verify the user has access to it
    try:
        tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user)
    except Tenant.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Tenant not found'})
    
    # Get archived clients, ordered by most recently archived
    archived_clients = Client.objects.filter(
        tenant=tenant,
        is_active=False,
        archived_at__isnull=False
    ).order_by('-archived_at')  # Using the archived_at field to sort
    
    # Format client data for JSON response
    client_data = []
    for client in archived_clients:
        client_data.append({
            'id': client.id,
            'name': client.name,
            'logo': client.logo.url if client.logo and client.logo.name else None,
            'archived_at': client.archived_at.strftime('%b %d, %Y %H:%M') if client.archived_at else "",
            'created_at': client.created_at.strftime('%b %d, %Y')
        })
    
    return JsonResponse({
        'status': 'success',
        'clients': client_data
    })

@login_required
def unarchive_client(request, client_id):
    """API endpoint to unarchive a client"""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Method not allowed'}, status=405)
    
    # Get the client and verify the user has access through the tenant
    client = get_object_or_404(Client, id=client_id, tenant__users=request.user)
    
    # Make sure the client is actually archived
    if client.is_active:
        return JsonResponse({'status': 'error', 'message': 'Client is already active'})
    
    # Unarchive the client
    client.is_active = True
    client.archived_at = None
    client.save(update_fields=['is_active', 'archived_at'])
    
    return JsonResponse({
        'status': 'success',
        'message': f"Client '{client.name}' has been restored.",
        'client': {
            'id': client.id,
            'name': client.name,
            'logo': client.logo.url if client.logo and client.logo.name else None,
            'created_at': client.created_at.strftime('%b %d, %Y'),
            'is_active': client.is_active
        }
    })

@login_required
def connect_platform(request, client_id):
    """
    View to display available platforms for connection
    """
    # Get the client and verify the user has access through the tenant
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    
    # Make sure the session has the correct tenant selected
    request.session['selected_tenant_id'] = client.tenant.id
    
    # Get all available platform types
    all_platforms = PlatformType.objects.filter(is_available=True).order_by('position', 'name')
    
    # Check which ones are already connected for this tenant
    # Use values_list() to fetch only the ids we need
    connected_platform_ids = PlatformConnection.objects.filter(
        tenant=client.tenant,
        is_active=True
    ).values_list('platform_type_id', flat=True)
    
    # Prepare the platforms with connection status
    available_platforms = []
    for platform in all_platforms:
        available_platforms.append({
            'id': platform.id,
            'name': platform.name,
            'slug': platform.slug,
            'description': platform.description,
            'is_connected': platform.id in connected_platform_ids
        })
    
    context = {
        'client': client,
        'available_platforms': available_platforms,
        'page_title': 'Connect Platform'
    }
    return render(request, 'connect_platform.html', context)

@login_required
def initiate_platform_connection(request, client_id, platform_id):
    """
    Initiates the OAuth flow for a specific platform
    """
    # Get the client and verify the user has access through the tenant
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    platform = get_object_or_404(PlatformType, id=platform_id)
    
    # Store in session for the callback
    request.session['connecting_client_id'] = client_id
    request.session['connecting_platform_id'] = platform_id
    
    # Handle different platform types
    if platform.slug == 'google-ads':
        # Google Ads OAuth flow with environment-aware configuration
        if settings.ENVIRONMENT == 'production':
            # Use environment variables in production
            if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
                raise ValueError("Google OAuth credentials are not configured in environment variables")
                
            client_config = {
                "web": {
                    "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            }
            flow = google_auth_oauthlib.flow.Flow.from_client_config(
                client_config,
                scopes=settings.GOOGLE_OAUTH_SCOPES
            )
        else:
            # Use client secrets file in development
            flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET_PATH', 'google_client_secret.json'),
                scopes=settings.GOOGLE_OAUTH_SCOPES
            )
        
        # The redirect URI must match one of the authorized redirect URIs
        # for the OAuth 2.0 client, which you configured in the API Console
        callback_url = request.build_absolute_uri(reverse('oauth_callback'))
        flow.redirect_uri = callback_url
        
        # Generate the authorization URL and redirect the user
        authorization_url, state = flow.authorization_url(
            # Enable offline access to get a refresh token
            access_type='offline',
            # Enable incremental authorization
            include_granted_scopes='true',
            # Force to always prompt for consent
            prompt='consent'
        )
        
        # Store state for CSRF protection
        request.session['oauth_state'] = state
        
        return HttpResponseRedirect(authorization_url)
    
    # Add additional platform connections here (Facebook, LinkedIn, etc.)
    
    messages.error(request, f"Connection process for {platform.name} is not implemented yet.")
    return redirect('connect_platform', client_id=client_id)

@login_required
def oauth_callback(request):
    """
    Callback handler for OAuth flows
    """
    # Retrieve information from session
    client_id = request.session.get('connecting_client_id')
    platform_id = request.session.get('connecting_platform_id')
    state = request.session.get('oauth_state')
    
    if not client_id or not platform_id:
        messages.error(request, "Connection process was interrupted. Please try again.")
        return redirect('home')
    
    # Get the client and platform
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    platform = get_object_or_404(PlatformType, id=platform_id)
    
    # Handle callback for different platform types
    if platform.slug == 'google-ads':
        try:
            # Complete the OAuth flow and get credentials with environment-aware configuration
            if settings.ENVIRONMENT == 'production':
                # Use environment variables in production
                if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
                    raise ValueError("Google OAuth credentials are not configured in environment variables")
                    
                client_config = {
                    "web": {
                        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token"
                    }
                }
                flow = google_auth_oauthlib.flow.Flow.from_client_config(
                    client_config,
                    scopes=settings.GOOGLE_OAUTH_SCOPES,
                    state=state
                )
            else:
                # Use client secrets file in development
                flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
                    getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET_PATH', 'google_client_secret.json'),
                    scopes=settings.GOOGLE_OAUTH_SCOPES,
                    state=state
                )
            
            callback_url = request.build_absolute_uri(reverse('oauth_callback'))
            flow.redirect_uri = callback_url
            
            # Use the authorization response in the callback to get the tokens
            authorization_response = request.build_absolute_uri()
            flow.fetch_token(authorization_response=authorization_response)
            
            # Get credentials and store them
            credentials = flow.credentials
            
            # Save the connection
            connection = PlatformConnection(
                tenant=client.tenant,
                platform_type=platform,
                connected_user=request.user,
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                token_expiry=datetime.datetime.fromtimestamp(credentials.expiry.timestamp()) if credentials.expiry else None
            )
            connection.save()
            
            messages.success(request, f"Successfully connected to {platform.name}!")
            
            # Automatically sync Google Ads accounts for new connections
            if platform.slug == 'google-ads':
                try:
                    logger.info(f"Running automatic sync for new Google Ads connection {connection.id}")
                    messages.info(request, "Syncing Google Ads accounts... This may take a few seconds.")
                    
                    from .services.google_ads_account_service import GoogleAdsAccountService
                    service = GoogleAdsAccountService(client.tenant)
                    success = service.sync_accounts(connection)
                    
                    if success:
                        messages.success(request, "Google Ads accounts have been automatically synced and are ready to use!")
                    else:
                        messages.warning(request, "Account sync encountered issues. You may need to run manual sync.")
                        
                except Exception as e:
                    logger.error(f"Error in automatic sync during OAuth callback: {str(e)}")
                    messages.warning(request, "Account sync encountered an error. You may need to run manual sync.")
            
            # Clear OAuth session data
            if 'connecting_client_id' in request.session:
                del request.session['connecting_client_id']
            if 'connecting_platform_id' in request.session:
                del request.session['connecting_platform_id']
            if 'oauth_state' in request.session:
                del request.session['oauth_state']
                
            return redirect('client_detail', client_id=client_id)
            
        except Exception as e:
            messages.error(request, f"Error connecting to {platform.name}: {str(e)}")
            return redirect('connect_platform', client_id=client_id)
    
    # Add other platform OAuth callbacks here
    
    messages.error(request, f"OAuth callback for {platform.name} is not implemented yet.")
    return redirect('connect_platform', client_id=client_id)

@login_required
def manage_platform_connection(request, client_id, platform_id):
    """
    View to manage an existing platform connection
    """
    # Get the client and verify the user has access through the tenant
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    platform = get_object_or_404(PlatformType, id=platform_id)
    
    # Get the existing connection
    connection = get_object_or_404(
        PlatformConnection.objects.select_related('connected_user'), 
        tenant=client.tenant,
        platform_type=platform,
        is_active=True
    )
    
    # Handle different action requests
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'disconnect':
            # Soft delete the connection
            connection.is_active = False
            connection.save(update_fields=['is_active'])
            messages.success(request, f"Disconnected from {platform.name}.")
            return redirect('connect_platform', client_id=client_id)
        
        elif action == 'refresh':
            # Implement token refresh logic here based on platform
            messages.info(request, f"Token refresh for {platform.name} is not implemented yet.")
            return redirect('manage_platform_connection', client_id=client_id, platform_id=platform_id)
    
    context = {
        'client': client,
        'platform': platform,
        'connection': connection,
        'page_title': f'Manage {platform.name} Connection'
    }
    return render(request, 'manage_platform_connection.html', context)

@login_required
def tenant_platforms(request):
    """
    View for displaying and managing platform connections for a tenant
    """
    # Get the selected tenant from session
    selected_tenant_id = request.session.get('selected_tenant_id')
    
    # Ensure a tenant is selected
    if not selected_tenant_id:
        messages.error(request, "Please select a tenant first.")
        return redirect('home')
    
    # Get the tenant and verify the user has access to it
    tenant = get_object_or_404(Tenant, id=selected_tenant_id, users=request.user)
    
    # Get all available platform types
    all_platforms = PlatformType.objects.filter(is_available=True).order_by('position', 'name')
    
    # Get existing connections for this tenant
    tenant_connections = PlatformConnection.objects.filter(
        tenant=tenant,
        is_active=True
    ).select_related('platform_type', 'connected_user')
    
    # Get all client platform accounts for this tenant
    # Add this code to fetch the latest client platform associations
    client_platform_accounts = ClientPlatformAccount.objects.filter(
        client__tenant=tenant,
        is_active=True
    ).select_related(
        'client',
        'platform_connection__platform_type'
    ).order_by('-platform_connection__created_at')
    
    # Group by platform type
    grouped_client_accounts = {}
    for account in client_platform_accounts:
        platform_slug = account.platform_connection.platform_type.slug
        if platform_slug not in grouped_client_accounts:
            grouped_client_accounts[platform_slug] = []
        grouped_client_accounts[platform_slug].append(account)
    
    # Get Google Ads platform ID for "Connect Another Account" button
    google_ads_platform_id = None
    try:
        google_ads_platform = PlatformType.objects.get(slug='google-ads')
        google_ads_platform_id = google_ads_platform.id
    except PlatformType.DoesNotExist:
        pass
    
    # Get all Google Ads connections for the table display
    google_ads_connections = PlatformConnection.objects.filter(
        tenant=tenant,
        platform_type__slug='google-ads',
        is_active=True
    ).select_related('connected_user', 'platform_type').order_by('-created_at')
    
    # Create a set of connected platform type IDs
    connected_platform_ids = set()
    for conn in tenant_connections:
        connected_platform_ids.add(conn.platform_type_id)
    
    # Get unconnected platforms
    unconnected_platforms = [p for p in all_platforms if p.id not in connected_platform_ids]
    
    # Create a dictionary of platform_type_id -> latest_connection
    connected_platforms = {}
    for conn in tenant_connections:
        # Only store the most recent connection per platform (based on this ordering)
        if conn.platform_type_id not in connected_platforms:
            connected_platforms[conn.platform_type_id] = conn
    
    # Prepare platform data for display
    platform_data = []
    for platform in all_platforms:
        connection = connected_platforms.get(platform.id)
        platform_data.append({
            'platform_type': platform,
            'connection': connection,
            'is_connected': connection is not None,
            'status': connection.connection_status if connection else None,
            'account_name': connection.platform_account_name if connection else None,
            'last_synced': connection.last_synced if connection else None,
        })
    
    context = {
        'tenant': tenant,
        'platform_data': platform_data,
        'google_ads_connections': google_ads_connections,
        'google_ads_platform_id': google_ads_platform_id,
        'unconnected_platforms': unconnected_platforms,
        'client_platform_accounts': client_platform_accounts,
        'grouped_client_accounts': grouped_client_accounts,
        'page_title': 'Platform Connections'
    }
    return render(request, 'tenant_platforms.html', context)

@login_required
def connect_platform_to_tenant(request, platform_id):
    """
    Initiates the OAuth flow for connecting a platform to a tenant
    """
    # Get the selected tenant from session
    selected_tenant_id = request.session.get('selected_tenant_id')
    
    # Ensure a tenant is selected
    if not selected_tenant_id:
        messages.error(request, "Please select a tenant first.")
        return redirect('home')
    
    # Get the tenant and verify the user has access to it
    tenant = get_object_or_404(Tenant, id=selected_tenant_id, users=request.user)
    platform = get_object_or_404(PlatformType, id=platform_id, is_available=True)
    
    # Store in session for the callback
    request.session['connecting_tenant_id'] = tenant.id
    request.session['connecting_platform_id'] = platform.id
    
    try:
        # Get the appropriate platform service
        platform_service = get_platform_service(tenant, platform.slug)
        
        # Create the callback URL
        callback_url = request.build_absolute_uri(reverse('tenant_oauth_callback'))
        
        # Initialize the OAuth flow
        authorization_url, state = platform_service.initialize_oauth_flow(callback_url)
        
        # Store state for CSRF protection
        request.session['oauth_state'] = state
        
        # Redirect to authorization URL
        return HttpResponseRedirect(authorization_url)
        
    except Exception as e:
        logger.error(f"Error initiating platform connection: {str(e)}")
        messages.error(request, f"Error connecting to {platform.name}: {str(e)}")
        return redirect('tenant_platforms')

@login_required
def tenant_oauth_callback(request):
    """
    Callback handler for OAuth flows when connecting platforms to tenants
    """
    # Retrieve information from session
    tenant_id = request.session.get('connecting_tenant_id')
    platform_id = request.session.get('connecting_platform_id')
    state = request.session.get('oauth_state')
    
    if not tenant_id or not platform_id or not state:
        messages.error(request, "Connection process was interrupted. Please try again.")
        return redirect('tenant_platforms')
    
    # Get the tenant and platform
    tenant = get_object_or_404(Tenant, id=tenant_id, users=request.user)
    platform = get_object_or_404(PlatformType, id=platform_id)
    
    try:
        # Get the appropriate platform service
        platform_service = get_platform_service(tenant, platform.slug)
        
        # Complete the OAuth flow
        authorization_response = request.build_absolute_uri()
        connection = platform_service.handle_oauth_callback(
            authorization_response=authorization_response,
            state=state,
            user=request.user
        )
        
        messages.success(request, f"Successfully connected to {platform.name}!")
        
    except Exception as e:
        logger.error(f"Error in OAuth callback: {str(e)}")
        messages.error(request, f"Error connecting to {platform.name}: {str(e)}")
    
    # Clear OAuth session data
    for key in ['connecting_tenant_id', 'connecting_platform_id', 'oauth_state']:
        if key in request.session:
            del request.session[key]
    
    return redirect('tenant_platforms')

@login_required
def manage_tenant_platform_connection(request, connection_id):
    """
    View to manage an existing platform connection
    """
    # Get the connection and verify access
    connection = get_object_or_404(
        PlatformConnection.objects.select_related('tenant', 'platform_type', 'connected_user'),
        id=connection_id,
        tenant__users=request.user
    )
    
    # Make sure the session has the correct tenant selected
    request.session['selected_tenant_id'] = connection.tenant.id
    
    # Get the platform service
    platform_service = get_platform_service(connection.tenant, connection.platform_type.slug)
    
    # Handle form actions
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'disconnect':
            try:
                # Disconnect from the platform
                platform_service.disconnect(connection)
                messages.success(request, f"Disconnected from {connection.platform_type.name}.")
                return redirect('tenant_platforms')
            except Exception as e:
                messages.error(request, f"Error disconnecting: {str(e)}")
        
        elif action == 'refresh':
            try:
                # Refresh the token
                success = platform_service.refresh_token(connection)
                if success:
                    messages.success(request, "Token refreshed successfully.")
                else:
                    messages.error(request, f"Failed to refresh token: {connection.status_message}")
                # Refresh the connection object
                connection.refresh_from_db()
            except Exception as e:
                messages.error(request, f"Error refreshing token: {str(e)}")
        
        elif action == 'test':
            try:
                # Test the connection
                account_info = platform_service.get_account_info(connection)
                if account_info:
                    messages.success(request, "Connection is working properly.")
                else:
                    messages.error(request, "Connection test failed. Please check the connection status.")
            except Exception as e:
                messages.error(request, f"Error testing connection: {str(e)}")
    
    # Get up-to-date account info if possible
    account_info = None
    if connection.is_active and connection.connection_status == 'active':
        try:
            account_info = platform_service.get_account_info(connection)
        except Exception:
            pass
    
    context = {
        'connection': connection,
        'account_info': account_info,
        'page_title': f'Manage {connection.platform_type.name} Connection'
    }
    return render(request, 'manage_tenant_platform.html', context)

@login_required
def add_competitor(request, client_id):
    """
    View for adding a competitor to a client
    """
    # Get the client and verify the user has access through the tenant
    client = get_object_or_404(
        Client, 
        id=client_id, 
        tenant__users=request.user
    )
    
    if request.method == 'POST':
        # Create a new Competitor object but don't save it yet
        competitor = Competitor(client=client)
        
        # Set fields from POST data
        competitor.name = request.POST.get('name', '')
        competitor.website = request.POST.get('website', '')
        competitor.description = request.POST.get('description', '')
        competitor.strength = request.POST.get('strength', 'medium')
        competitor.advantages = request.POST.get('advantages', '')
        
        # Validate data
        if not competitor.name:
            messages.error(request, "Competitor name is required.")
        else:
            # Save the competitor
            try:
                competitor.save()
                messages.success(request, f"Competitor '{competitor.name}' added successfully!")
            except Exception as e:
                messages.error(request, f"Error saving competitor: {str(e)}")
    
    return redirect('client_detail', client_id=client.id)

@login_required
def edit_competitor(request, client_id, competitor_id):
    """
    View for editing a competitor
    """
    # Get the client and verify the user has access through the tenant
    client = get_object_or_404(
        Client, 
        id=client_id, 
        tenant__users=request.user
    )
    
    # Get the competitor and verify it belongs to the client
    competitor = get_object_or_404(
        Competitor, 
        id=competitor_id, 
        client=client
    )
    
    if request.method == 'POST':
        form = CompetitorForm(request.POST, instance=competitor)
        if form.is_valid():
            form.save()
            messages.success(request, f"Competitor '{competitor.name}' updated successfully!")
        else:
            messages.error(request, "There was an error updating the competitor. Please check the form and try again.")
    
    return redirect('client_detail', client_id=client.id)


@login_required
def delete_competitor(request, client_id, competitor_id):
    """
    View for deleting a competitor
    """
    # Get the client and verify the user has access through the tenant
    client = get_object_or_404(
        Client, 
        id=client_id, 
        tenant__users=request.user
    )
    
    # Get the competitor and verify it belongs to the client
    competitor = get_object_or_404(
        Competitor, 
        id=competitor_id, 
        client=client
    )
    
    if request.method == 'POST':
        competitor_name = competitor.name
        
        # Mark as inactive instead of actual deletion
        competitor.is_active = False
        competitor.save()
        
        messages.success(request, f"Competitor '{competitor_name}' deleted successfully!")
    
    return redirect('client_detail', client_id=client.id)


@login_required
def add_client_platform_account(request, client_id, platform_id, account_id):
    """
    View to add a platform account to a client
    """
    # Get the client and verify the user has access through the tenant
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    
    # Get the platform type
    platform = get_object_or_404(PlatformType, id=platform_id)
    
    # Get the platform connection for this tenant
    connection = get_object_or_404(
        PlatformConnection,
        tenant=client.tenant,
        platform_type=platform,
        is_active=True
    )
    
    # Check if this account is already linked to this client
    existing_account = ClientPlatformAccount.objects.filter(
        client=client,
        platform_connection=connection,
        platform_client_id=account_id,
        is_active=True
    ).first()
    
    if existing_account:
        messages.info(request, f"Account is already linked to this client.")
        return redirect('client_detail', client_id=client.id)
    
    # Get account name from POST data if provided
    account_name = request.POST.get('account_name', f"Account {account_id}")
    
    # Create a new client platform account
    new_account = ClientPlatformAccount(
        client=client,
        platform_connection=connection,
        platform_client_id=account_id,
        platform_client_name=account_name
    )
    new_account.save()
    
    # Trigger a sync for the newly added account if it's a Google Ads account
    if platform.slug == 'google-ads':
        try:
            # Note: Account syncing is now handled by the account service
            # and is separate from campaign data syncing
            messages.success(request, f"Account '{account_name}' added successfully!")
        except Exception as e:
            logger.error(f"Error syncing data for new account: {str(e)}")
            messages.success(request, f"Account '{account_name}' added successfully! Data sync will happen later.")
    else:
        messages.success(request, f"Account '{account_name}' added successfully!")
    
    return redirect('client_detail', client_id=client.id)

@login_required
def remove_client_platform_account(request, account_id):
    """
    View to remove a platform account from a client
    """
    # Get the account and verify the user has access through the tenant
    account = get_object_or_404(
        ClientPlatformAccount.objects.select_related('client', 'platform_connection__platform_type'), 
        id=account_id, 
        client__tenant__users=request.user,
        is_active=True
    )
    
    client = account.client
    
    if request.method == 'POST':
        # Soft delete by marking as inactive
        account.is_active = False
        account.save(update_fields=['is_active'])
        
        messages.success(request, f"'{account.platform_client_name}' removed from {client.name}.")
        return redirect('client_detail', client_id=client.id)
    
    context = {
        'account': account,
        'client': client,
        'page_title': f'Remove Platform Account - {client.name}'
    }
    return render(request, 'remove_client_platform_account.html', context)


@login_required
def reactivate_client_platform_account(request, account_id):
    """
    View to reactivate a previously deactivated platform account
    """
    # Get the account and verify the user has access through the tenant
    account = get_object_or_404(
        ClientPlatformAccount.objects.select_related('client'), 
        id=account_id, 
        client__tenant__users=request.user
    )
    
    client = account.client
    
    if request.method == 'POST':
        # Reactivate by setting is_active to True
        account.is_active = True
        account.save(update_fields=['is_active'])
        
        messages.success(request, f"'{account.platform_client_name}' reactivated for {client.name}.")
        return redirect('client_detail', client_id=client.id)
    
    # If not POST, redirect to the client platform accounts page
    return redirect('client_detail', client_id=client.id)

@login_required
def client_groups(request):
    """
    View to display all client groups for the selected tenant
    """
    # Get the selected tenant from session
    selected_tenant_id = request.session.get('selected_tenant_id')
    
    # Ensure a tenant is selected
    if not selected_tenant_id:
        messages.error(request, "Please select a tenant first.")
        return redirect('home')
    
    # Get the tenant and verify the user has access to it
    tenant = get_object_or_404(Tenant, id=selected_tenant_id, users=request.user)
    
    # Get all active client groups for this tenant
    # Use annotate to calculate client count in the database instead of in Python
    groups = ClientGroup.objects.filter(
        tenant=tenant, 
        is_active=True
    ).prefetch_related(
        Prefetch('clients', queryset=Client.objects.filter(is_active=True))
    ).annotate(
        active_client_count=Count('clients', filter=Q(clients__is_active=True))
    )
    
    # Get all active clients for this tenant for the create form
    all_clients = Client.objects.filter(tenant=tenant, is_active=True)
    
    context = {
        'tenant': tenant,
        'groups': groups,
        'all_clients': all_clients,
        'page_title': 'Client Groups'
    }
    return render(request, 'client_groups.html', context)

@login_required
def create_client_group(request):
    """
    View for creating a new client group, handles both regular and AJAX requests
    """
    # Get the selected tenant from session
    selected_tenant_id = request.session.get('selected_tenant_id')
    
    # Ensure a tenant is selected
    if not selected_tenant_id:
        messages.error(request, "Please select a tenant first.")
        return redirect('home')
    
    # Get the tenant and verify the user has access to it
    tenant = get_object_or_404(Tenant, id=selected_tenant_id, users=request.user)
    
    if request.method == 'POST':
        # Handle different ways of receiving data
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # For AJAX requests, manually create the group
            try:
                name = request.POST.get('name')
                description = request.POST.get('description', '')
                color = request.POST.get('color', '#6c757d')
                icon_class = request.POST.get('icon_class', 'bi-collection')
                
                # Create the group
                group = ClientGroup.objects.create(
                    tenant=tenant,
                    name=name,
                    description=description,
                    color=color,
                    icon_class=icon_class
                )
                
                # Add clients to the group
                client_ids = request.POST.getlist('clients')
                if client_ids:
                    # Use bulk operations for better performance when adding many clients
                    clients = Client.objects.filter(id__in=client_ids, tenant=tenant)
                    group.clients.add(*clients)
                
                return JsonResponse({'status': 'success'})
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': str(e)})
        else:
            # For regular form submissions, use the form
            form = ClientGroupForm(request.POST, tenant=tenant)
            if form.is_valid():
                group = form.save(commit=False)
                group.tenant = tenant
                group.save()
                
                # Save the many-to-many relationships
                form.save_m2m()
                
                # Also explicitly add clients to ensure they're saved
                selected_clients = form.cleaned_data.get('clients', [])
                if selected_clients:
                    group.clients.add(*selected_clients)
                
                messages.success(request, f"Client group '{group.name}' created successfully!")
                return redirect('client_groups')
    else:
        form = ClientGroupForm(tenant=tenant)
    
    context = {
        'form': form,
        'tenant': tenant,
        'page_title': 'Create Client Group'
    }
    return render(request, 'create_client_group.html', context)

@login_required
def edit_client_group(request, group_id):
    """
    View for editing an existing client group, handles both regular and AJAX requests
    """
    # Get the group and verify the user has access through the tenant
    group = get_object_or_404(
        ClientGroup.objects.select_related('tenant').prefetch_related('clients'),
        id=group_id, 
        tenant__users=request.user
    )
    
    # Make sure the session has the correct tenant selected
    request.session['selected_tenant_id'] = group.tenant.id
    
    if request.method == 'POST':
        # Handle different ways of receiving data
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # For AJAX requests, manually update the group
            try:
                group.name = request.POST.get('name')
                group.description = request.POST.get('description', '')
                group.color = request.POST.get('color', '#6c757d')
                group.icon_class = request.POST.get('icon_class', 'bi-collection')
                # Use update_fields for more efficient update
                group.save(update_fields=['name', 'description', 'color', 'icon_class'])
                
                # Update clients - first clear existing relationships
                group.clients.clear()
                
                # Then add new clients
                client_ids = request.POST.getlist('clients')
                if client_ids:
                    # Get clients in a single query and add them in bulk
                    clients = Client.objects.filter(id__in=client_ids, tenant=group.tenant)
                    group.clients.add(*clients)
                
                return JsonResponse({'status': 'success'})
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': str(e)})
        else:
            # For regular form submissions, use the form
            form = ClientGroupForm(request.POST, instance=group, tenant=group.tenant)
            if form.is_valid():
                form.save()
                
                # Explicitly clear and add clients to ensure they're saved
                group.clients.clear()
                selected_clients = form.cleaned_data.get('clients', [])
                if selected_clients:
                    group.clients.add(*selected_clients)
                
                messages.success(request, f"Client group '{group.name}' updated successfully!")
                return redirect('client_groups')
    else:
        # Instead of rendering a separate page, redirect to client_groups with a parameter
        # to trigger opening the edit modal
        return redirect(f'/client-groups/?edit={group_id}')
    
    context = {
        'form': form,
        'group': group,
        'page_title': f'Edit {group.name}'
    }
    return render(request, 'edit_client_group.html', context)


@login_required
def delete_client_group(request, group_id):
    """
    View for soft-deleting a client group, handles both regular and AJAX requests
    """
    # Get the group and verify the user has access through the tenant
    group = get_object_or_404(ClientGroup, id=group_id, tenant__users=request.user)
    
    if request.method == 'POST':
        # Handle different ways of receiving data
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # For AJAX requests
            try:
                group.is_active = False
                # Use update_fields for more efficient update
                group.save(update_fields=['is_active'])
                return JsonResponse({'status': 'success'})
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': str(e)})
        else:
            # For regular form submissions
            group.is_active = False
            group.save(update_fields=['is_active'])
            
            messages.success(request, f"Client group '{group.name}' has been deleted.")
            return redirect('client_groups')
    
    context = {
        'group': group,
        'page_title': f'Delete {group.name}'
    }
    return render(request, 'delete_client_group.html', context)

@login_required
def client_group_clients_json(request, group_id):
    """
    AJAX view to get clients for a group
    """
    # Get the group and verify the user has access through the tenant
    group = get_object_or_404(ClientGroup, id=group_id, tenant__users=request.user)
    
    # Get all active clients for this tenant
    # Use values() to fetch only the fields we need
    all_clients = list(Client.objects.filter(
        tenant=group.tenant, 
        is_active=True
    ).values('id', 'name'))
    
    # Get client IDs in this group
    # Use values_list for more efficient query when we only need IDs
    group_client_ids = list(group.clients.values_list('id', flat=True))
    
    return JsonResponse({
        'status': 'success',
        'all_clients': all_clients,
        'group_clients': group_client_ids
    })

@login_required
def remove_client_from_group(request, group_id, client_id):
    """
    View for removing a client from a group, handles both regular and AJAX requests
    """
    # Get the group and client, and verify access
    group = get_object_or_404(
        ClientGroup.objects.select_related('tenant'),
        id=group_id, 
        tenant__users=request.user
    )
    client = get_object_or_404(Client, id=client_id, tenant=group.tenant)
    
    if request.method == 'POST':
        # Remove client from the group
        group.clients.remove(client)
        
        # Handle AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success'})
        
        # Regular form submission
        messages.success(request, f"'{client.name}' removed from '{group.name}' group.")
        return redirect('client_groups', group_id=group.id)
    
    context = {
        'group': group,
        'client': client,
        'page_title': f'Remove Client from {group.name}'
    }
    return render(request, 'remove_client_from_group.html', context)


# Views for budget management
@login_required
def budget_dashboard(request):
    """Main budget dashboard view"""
    # Get the selected tenant
    selected_tenant_id = request.session.get('selected_tenant_id')
    if not selected_tenant_id:
        messages.error(request, "Please select a tenant first.")
        return redirect('home')
    
    tenant = get_object_or_404(Tenant, id=selected_tenant_id, users=request.user)
    
    # Check for client filtering
    client_id = request.GET.get('client_id')
    client_filter = None
    
    if client_id:
        try:
            client_filter = Client.objects.get(id=client_id, tenant=tenant, is_active=True)
        except Client.DoesNotExist:
            messages.warning(request, f"Client with ID {client_id} not found.")
    
    # Get active budgets for this tenant (with optional client filter)
    budget_filter = {
        'tenant': tenant,
        'is_active': True,
        'end_date__gte': timezone.now().date()
    }
    
    if client_filter:
        budget_filter['client'] = client_filter
    
    active_budgets = Budget.objects.filter(**budget_filter).select_related('client', 'client_group', 'created_by')
    
    # Initialize counters for budget statuses
    on_track_count = 0
    underspend_count = 0
    overspend_count = 0
    
    # Calculate current spend for each budget
    for budget in active_budgets:
        # This would be replaced with actual spend data from your platforms
        budget.current_spend = calculate_current_spend(budget)
        budget_amount = float(budget.amount) if budget.amount else 0
        budget.spend_percentage = (budget.current_spend / budget_amount) * 100 if budget_amount else 0
        
        # Calculate expected spend based on time elapsed
        budget.expected_spend = float(budget.expected_spend_to_date)
        budget.expected_percentage = (budget.expected_spend / budget_amount) * 100 if budget_amount else 0
        
        # Calculate variance
        budget.variance = budget.current_spend - budget.expected_spend
        budget.variance_percentage = ((budget.current_spend / budget.expected_spend) * 100) - 100 if budget.expected_spend else 0
        
        # Determine status and increment appropriate counter
        if budget.variance_percentage > 10:
            budget.status = 'overspend'
            overspend_count += 1
        elif budget.variance_percentage < -10:
            budget.status = 'underspend'
            underspend_count += 1
        else:
            budget.status = 'on-track'
            on_track_count += 1
    
    # Calculate total for "needs attention" count
    needs_attention_count = overspend_count + underspend_count
    
    context = {
        'active_budgets': active_budgets,
        'active_budgets_count': active_budgets.count(),
        'on_track_count': on_track_count,
        'needs_attention_count': needs_attention_count,
        'overspend_count': overspend_count,
        'underspend_count': underspend_count,
        'page_title': 'Budget Dashboard',
        'client_filter': client_filter,
        'selected_tenant': tenant
    }
    return render(request, 'budget_dashboard.html', context)


def calculate_current_spend(budget):
    """
    Calculate actual spend for a budget
    This is a placeholder function - will need to be replaced with actual data retrieval
    """
    # Start with a total of 0
    total_spend = 0
    
    # Get today's date
    today = timezone.now().date()
    
    # Only calculate for budgets that have started
    if today < budget.start_date:
        return 0
    
    # Determine date range
    start_date = budget.start_date
    end_date = min(today, budget.end_date)
    
    # If budget is for a specific client
    if budget.client:
        # Get all platform accounts for this client
        platform_accounts = ClientPlatformAccount.objects.filter(
            client=budget.client,
            is_active=True
        )
        
        for account in platform_accounts:
            # Handle Google Ads accounts
            if account.platform_connection.platform_type.slug == 'google-ads':
                # Get campaign metrics for the date range
                campaign_metrics = GoogleAdsDailyMetrics.objects.filter(
                    campaign__client_account=account,
                    date__gte=start_date,
                    date__lte=end_date
                ).aggregate(total_cost=Sum('cost'))
                
                if campaign_metrics['total_cost']:
                    total_spend += float(campaign_metrics['total_cost'])
    
    # If budget is for a client group
    elif budget.client_group:
        # Get all clients in this group
        clients = budget.client_group.clients.filter(is_active=True)
        
        for client in clients:
            # Get platform accounts for each client
            platform_accounts = ClientPlatformAccount.objects.filter(
                client=client,
                is_active=True
            )
            
            for account in platform_accounts:
                # Handle Google Ads accounts
                if account.platform_connection.platform_type.slug == 'google-ads':
                    # Get campaign metrics
                    campaign_metrics = GoogleAdsDailyMetrics.objects.filter(
                        campaign__client_account=account,
                        date__gte=start_date,
                        date__lte=end_date
                    ).aggregate(total_cost=Sum('cost'))
                    
                    if campaign_metrics['total_cost']:
                        total_spend += float(campaign_metrics['total_cost'])
    
    return total_spend


def calculate_spend_for_date_range(client, start_date, end_date):
    """
    Calculate actual spend for a client within a specific date range
    """
    total_spend = 0
    
    # Get all platform accounts for this client
    platform_accounts = ClientPlatformAccount.objects.filter(
        client=client,
        is_active=True
    )
    
    for account in platform_accounts:
        # Handle Google Ads accounts
        if account.platform_connection.platform_type.slug == 'google-ads':
            # Get campaign metrics for the date range
            campaign_metrics = GoogleAdsDailyMetrics.objects.filter(
                campaign__client_account=account,
                date__gte=start_date,
                date__lte=end_date
            ).aggregate(total_cost=Sum('cost'))
            
            if campaign_metrics['total_cost']:
                total_spend += float(campaign_metrics['total_cost'])
    
    return total_spend


@login_required
def create_budget(request):
    """View for creating a new budget"""
    # Get the selected tenant
    selected_tenant_id = request.session.get('selected_tenant_id')
    if not selected_tenant_id:
        messages.error(request, "Please select a tenant first.")
        return redirect('home')
    
    tenant = get_object_or_404(Tenant, id=selected_tenant_id, users=request.user)
    
    if request.method == 'POST':
        form = BudgetForm(request.POST, tenant=tenant)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.tenant = tenant
            budget.created_by = request.user
            budget.save()
            
            # Handle budget allocations if provided
            if form.cleaned_data.get('allocations'):
                for allocation_data in form.cleaned_data['allocations']:
                    BudgetAllocation.objects.create(
                        budget=budget,
                        **allocation_data
                    )
            
            messages.success(request, f"Budget '{budget.name}' created successfully!")
            return redirect('budget_detail', budget_id=budget.id)
    else:
        # Initialize with default dates (current month)
        today = timezone.now().date()
        start_date = today.replace(day=1)  # First day of current month
        next_month = today.month + 1 if today.month < 12 else 1
        next_month_year = today.year if today.month < 12 else today.year + 1
        end_date = datetime.date(next_month_year, next_month, 1) - datetime.timedelta(days=1)  # Last day of current month
        
        form = BudgetForm(
            tenant=tenant, 
            initial={'start_date': start_date, 'end_date': end_date, 'frequency': 'monthly'}
        )
    
    context = {
        'form': form,
        'tenant': tenant,
        'page_title': 'Create Budget'
    }
    return render(request, 'create_budget.html', context)


@login_required
def budget_detail(request, budget_id):
    """View for displaying detailed budget information"""
    # Get the budget and verify access
    budget = get_object_or_404(
        Budget.objects.select_related('tenant', 'client', 'client_group', 'created_by'),
        id=budget_id,
        tenant__users=request.user
    )
    
    # Make sure the session has the correct tenant
    request.session['selected_tenant_id'] = budget.tenant.id
    
    # Get budget allocations
    allocations = BudgetAllocation.objects.filter(budget=budget).select_related(
        'platform_type', 'platform_account', 'campaign'
    )
    
    # Get spend snapshots for historical data
    # Get last 30 days of data or all if less than 30 days exist
    days_to_fetch = min(30, (timezone.now().date() - budget.start_date).days + 1)
    if days_to_fetch > 0:
        date_from = timezone.now().date() - datetime.timedelta(days=days_to_fetch-1)
        snapshots = SpendSnapshot.objects.filter(
            budget=budget,
            date__gte=date_from
        ).order_by('date')
    else:
        snapshots = SpendSnapshot.objects.none()
    
    # Calculate current spend
    current_spend = calculate_current_spend(budget)
    
    # Convert Decimal to float for calculations with other floats
    budget_amount_float = float(budget.amount)
    
    # Calculate percentages
    spend_percentage = (current_spend / budget_amount_float) * 100 if budget_amount_float else 0
    
    # Calculate expected spend
    expected_spend = float(budget.expected_spend_to_date)
    expected_percentage = (expected_spend / budget_amount_float) * 100 if budget_amount_float else 0
    
    # Calculate variance
    variance = current_spend - expected_spend
    variance_percentage = ((current_spend / expected_spend) * 100) - 100 if expected_spend else 0
    
    # Determine status
    if variance_percentage > 10:
        status = 'overspend'
    elif variance_percentage < -10:
        status = 'underspend'
    else:
        status = 'on-track'
    
    # Get daily spend data for chart
    chart_data = []
    expected_data = []
    
    # If we have snapshots, use those
    if snapshots.exists():
        for snapshot in snapshots:
            chart_data.append({
                'date': snapshot.date.strftime('%Y-%m-%d'),
                'amount': float(snapshot.spend_amount)
            })
            expected_data.append({
                'date': snapshot.date.strftime('%Y-%m-%d'),
                'amount': float(snapshot.expected_amount)
            })
    else:
        # Generate expected spend curve
        current_date = max(budget.start_date, timezone.now().date() - datetime.timedelta(days=30))
        end_date = min(budget.end_date, timezone.now().date())
        
        while current_date <= end_date:
            days_elapsed = (current_date - budget.start_date).days + 1
            expected = (budget_amount_float * days_elapsed) / budget.days_in_period if budget.days_in_period else 0
            
            # Add dummy data point for actual spend (random variation around expected)
            import random
            variation = random.uniform(0.8, 1.2)  # Random multiplier between 0.8 and 1.2
            actual = expected * variation
            
            chart_data.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'amount': float(actual)
            })
            
            expected_data.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'amount': float(expected)
            })
            
            current_date += datetime.timedelta(days=1)
    
    # Get alerts for this budget
    alerts = BudgetAlert.objects.filter(budget=budget, is_active=True)
    
    
    time_elapsed_days = budget.days_elapsed
    time_elapsed_percentage = (time_elapsed_days / budget.days_in_period) * 100 if budget.days_in_period else 0
    
    # Calculate daily average spend
    daily_avg_spend = current_spend / time_elapsed_days if time_elapsed_days else 0
    daily_budget_amount = budget_amount_float / budget.days_in_period if budget.days_in_period else 0

    context = {
        'budget': budget,
        'allocations': allocations,
        'snapshots': snapshots,
        'current_spend': current_spend,
        'spend_percentage': spend_percentage,
        'expected_spend': expected_spend,
        'expected_percentage': expected_percentage,
        'variance': variance,
        'variance_percentage': variance_percentage,
        'status': status,
        'chart_data': json.dumps(chart_data),
        'expected_data': json.dumps(expected_data),
        'alerts': alerts,
        'page_title': f'Budget: {budget.name}',
        'time_elapsed_percentage': time_elapsed_percentage,
        'daily_avg_spend': daily_avg_spend,
        'daily_budget_amount': daily_budget_amount,
        'page_title': f'Budget: {budget.name}'
    }
    return render(request, 'budget_detail.html', context)


@login_required
def edit_budget(request, budget_id):
    """View for editing an existing budget"""
    # Get the budget and verify access
    budget = get_object_or_404(
        Budget.objects.select_related('tenant', 'client', 'client_group'),
        id=budget_id,
        tenant__users=request.user
    )
    
    # Make sure the session has the correct tenant
    request.session['selected_tenant_id'] = budget.tenant.id
    
    if request.method == 'POST':
        form = BudgetForm(request.POST, instance=budget, tenant=budget.tenant)
        if form.is_valid():
            form.save()
            
            # Update allocations (delete existing and create new)
            BudgetAllocation.objects.filter(budget=budget).delete()
            
            if form.cleaned_data.get('allocations'):
                for allocation_data in form.cleaned_data['allocations']:
                    BudgetAllocation.objects.create(
                        budget=budget,
                        **allocation_data
                    )
            
            messages.success(request, f"Budget '{budget.name}' updated successfully!")
            return redirect('budget_detail', budget_id=budget.id)
    else:
        form = BudgetForm(instance=budget, tenant=budget.tenant)
    
    context = {
        'form': form,
        'budget': budget,
        'page_title': f'Edit Budget: {budget.name}'
    }
    return render(request, 'edit_budget.html', context)


@login_required
def deactivate_budget(request, budget_id):
    """View for deactivating a budget"""
    # Get the budget and verify access
    budget = get_object_or_404(
        Budget,
        id=budget_id,
        tenant__users=request.user
    )
    
    if request.method == 'POST':
        # Deactivate the budget
        budget.is_active = False
        budget.save(update_fields=['is_active'])
        
        messages.success(request, f"Budget '{budget.name}' has been deactivated.")
        return redirect('budget_dashboard')
    
    context = {
        'budget': budget,
        'page_title': f'Deactivate Budget: {budget.name}'
    }
    return render(request, 'confirm_deactivate_budget.html', context)


@login_required
def create_budget_alert(request, budget_id):
    """View for creating a budget alert"""
    # Get the budget and verify access
    budget = get_object_or_404(
        Budget.objects.select_related('tenant'),
        id=budget_id,
        tenant__users=request.user
    )
    
    if request.method == 'POST':
        form = BudgetAlertForm(request.POST)
        if form.is_valid():
            alert = form.save(commit=False)
            alert.budget = budget
            alert.user = request.user
            alert.save()
            
            messages.success(request, "Budget alert created successfully!")
            return redirect('budget_detail', budget_id=budget.id)
    else:
        form = BudgetAlertForm()
    
    context = {
        'form': form,
        'budget': budget,
        'page_title': 'Create Budget Alert'
    }
    return render(request, 'create_budget_alert.html', context)

# API endpoints for dynamic form population

@login_required
def platform_accounts_api(request, platform_id):
    """API endpoint to get available Google Ads accounts for linking to clients"""
    try:
        # Check for force refresh parameter
        force_refresh = request.GET.get('refresh', 'false').lower() == 'true'
        
        # Get the selected tenant
        selected_tenant_id = request.session.get('selected_tenant_id')
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        # Verify user has access to tenant
        tenant = get_object_or_404(Tenant, id=selected_tenant_id, users=request.user)
        
        # Get the platform type
        try:
            platform_type = PlatformType.objects.get(id=platform_id)
        except PlatformType.DoesNotExist:
            return JsonResponse({'error': f'Platform type with ID {platform_id} not found'}, status=404)
        
        # Get active connections for this platform type
        connections = PlatformConnection.objects.filter(
            tenant=tenant,
            platform_type=platform_type,
            is_active=True
        )
        
        if not connections.exists():
            return JsonResponse({'accounts': [], 'message': 'No active connections for this platform'})
        
        # For Google Ads, fetch available accounts
        if platform_type.slug == 'google-ads':
            try:
                # Use the most recent active connection with valid tokens
                connection = connections.filter(connection_status='active').order_by('-created_at').first()
                if not connection:
                    # Fallback to most recent active connection
                    connection = connections.order_by('-created_at').first()
                
                logger.info(f"🔄 Getting Google Ads accounts for connection {connection.id}")
                
                # Initialize the new Google Ads client service
                from .services.google_ads_client_service import GoogleAdsClientService
                service = GoogleAdsClientService(connection)
                
                # Get full account hierarchy (with optional force refresh)
                hierarchy_result = service.get_accounts_with_hierarchy(force_refresh=force_refresh)
                
                # Handle empty responses
                if not hierarchy_result or not hierarchy_result.get('accounts'):
                    logger.info("No accounts found - returning empty list")
                    return JsonResponse({
                        'accounts': [],
                        'message': 'No Google Ads accounts found for this connection'
                    })
                
                # Extract accounts and check for managers
                accounts = hierarchy_result['accounts']
                has_managers = hierarchy_result.get('has_managers', False)
                
                from_cache = hierarchy_result.get('from_cache', False)
                total_accounts = hierarchy_result.get('total_accounts', len(accounts))
                
                logger.info(f"✅ Retrieved {len(accounts)} Google Ads accounts with hierarchy (has_managers: {has_managers}, from_cache: {from_cache})")
                
                # Return the full hierarchical structure
                return JsonResponse({
                    'accounts': accounts,
                    'has_managers': has_managers,
                    'from_cache': from_cache,
                    'total_accounts': total_accounts,
                    'connection': {
                        'platform_account_name': connection.platform_account_name,
                        'platform_account_email': connection.platform_account_email
                    }
                })
                
            except Exception as e:
                import traceback
                logger.error(f"Error fetching Google Ads accounts: {str(e)}")
                logger.error(traceback.format_exc())
                return JsonResponse({'error': str(e), 'accounts': []}, status=500)
        
        # Default response for other platforms
        return JsonResponse({'accounts': [], 'message': f'No implementation for platform: {platform_type.slug}'})
    
    except Exception as e:
        import traceback
        logger.error(f"Unexpected error in platform_accounts_api: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({'error': str(e), 'accounts': []}, status=500)

@login_required
def set_performance_goal(request, client_id):
    """API endpoint to set performance goals for a client"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        
        # Get the client and ensure user has access
        selected_tenant_id = request.session.get('selected_tenant_id')
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        client = get_object_or_404(
            Client, 
            id=client_id, 
            tenant_id=selected_tenant_id
        )
        
        # Get or create performance goals
        from .models import ClientPerformanceGoal
        goals, created = ClientPerformanceGoal.objects.get_or_create(
            client=client,
            defaults={'created_by': request.user}
        )
        
        # Update goals
        if 'ctr_goal' in data:
            goals.ctr_goal = data['ctr_goal'] if data['ctr_goal'] else None
        
        if 'conversion_rate_goal' in data:
            goals.conversion_rate_goal = data['conversion_rate_goal'] if data['conversion_rate_goal'] else None
            
        if 'cost_per_click_goal' in data:
            goals.cost_per_click_goal = data['cost_per_click_goal'] if data['cost_per_click_goal'] else None
            
        if 'cost_per_conversion_goal' in data:
            goals.cost_per_conversion_goal = data['cost_per_conversion_goal'] if data['cost_per_conversion_goal'] else None
            
        if 'use_global_goals' in data:
            goals.use_global_goals = bool(data['use_global_goals'])
        
        goals.save()
        
        # Get effective goals for response
        effective_goals = goals.get_effective_goals()
        
        return JsonResponse({
            'success': True,
            'message': 'Performance goals updated successfully',
            'goals': {
                'ctr_goal': float(effective_goals['ctr_goal']) if effective_goals['ctr_goal'] else None,
                'conversion_rate_goal': float(effective_goals['conversion_rate_goal']) if effective_goals['conversion_rate_goal'] else None,
                'cost_per_click_goal': float(effective_goals['cost_per_click_goal']) if effective_goals['cost_per_click_goal'] else None,
                'cost_per_conversion_goal': float(effective_goals['cost_per_conversion_goal']) if effective_goals['cost_per_conversion_goal'] else None,
                'use_global_goals': goals.use_global_goals,
                'source': effective_goals['source']
            }
        })
        
    except Exception as e:
        logger.error(f"Error setting performance goal: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_performance_goal(request, client_id):
    """API endpoint to get performance goals for a client"""
    try:
        # Get the client and ensure user has access
        selected_tenant_id = request.session.get('selected_tenant_id')
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        client = get_object_or_404(
            Client, 
            id=client_id, 
            tenant_id=selected_tenant_id
        )
        
        # Get performance goals
        from .models import ClientPerformanceGoal
        try:
            goals = ClientPerformanceGoal.objects.get(client=client)
            return JsonResponse({
                'success': True,
                'goals': {
                    'ctr_goal': float(goals.ctr_goal) if goals.ctr_goal else None,
                    'conversion_rate_goal': float(goals.conversion_rate_goal) if goals.conversion_rate_goal else None
                }
            })
        except ClientPerformanceGoal.DoesNotExist:
            return JsonResponse({
                'success': True,
                'goals': {
                    'ctr_goal': None,
                    'conversion_rate_goal': None
                }
            })
        
    except Exception as e:
        logger.error(f"Error getting performance goal: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_tenant_global_goals(request):
    """API endpoint to get global performance goals for the tenant"""
    try:
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        # Get the tenant and verify user access
        try:
            tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user, is_active=True)
        except Tenant.DoesNotExist:
            return JsonResponse({'error': 'Tenant not found or access denied'}, status=403)
        
        # Get or create global goals
        from .models import TenantPerformanceGoals
        global_goals, created = TenantPerformanceGoals.objects.get_or_create(
            tenant=tenant,
            defaults={'created_by': request.user}
        )
        
        return JsonResponse({
            'success': True,
            'goals': {
                'ctr_goal': float(global_goals.ctr_goal) if global_goals.ctr_goal else None,
                'conversion_rate_goal': float(global_goals.conversion_rate_goal) if global_goals.conversion_rate_goal else None,
                'cost_per_click_goal': float(global_goals.cost_per_click_goal) if global_goals.cost_per_click_goal else None,
                'cost_per_conversion_goal': float(global_goals.cost_per_conversion_goal) if global_goals.cost_per_conversion_goal else None,
                'goal_mode': global_goals.goal_mode
            },
            'created': created
        })
        
    except Exception as e:
        logger.error(f"Error getting global goals: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def set_tenant_global_goals(request):
    """API endpoint to set global performance goals for the tenant"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)
    
    try:
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        # Get the tenant and verify user access
        try:
            tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user, is_active=True)
        except Tenant.DoesNotExist:
            return JsonResponse({'error': 'Tenant not found or access denied'}, status=403)
        
        # Parse request data
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        
        # Get or create global goals
        from .models import TenantPerformanceGoals
        global_goals, created = TenantPerformanceGoals.objects.get_or_create(
            tenant=tenant,
            defaults={'created_by': request.user}
        )
        
        # Update goals
        if 'ctr_goal' in data and data['ctr_goal'] is not None:
            global_goals.ctr_goal = data['ctr_goal']
        elif 'ctr_goal' in data:
            global_goals.ctr_goal = None
            
        if 'conversion_rate_goal' in data and data['conversion_rate_goal'] is not None:
            global_goals.conversion_rate_goal = data['conversion_rate_goal']
        elif 'conversion_rate_goal' in data:
            global_goals.conversion_rate_goal = None
            
        if 'cost_per_click_goal' in data and data['cost_per_click_goal'] is not None:
            global_goals.cost_per_click_goal = data['cost_per_click_goal']
        elif 'cost_per_click_goal' in data:
            global_goals.cost_per_click_goal = None
            
        if 'cost_per_conversion_goal' in data and data['cost_per_conversion_goal'] is not None:
            global_goals.cost_per_conversion_goal = data['cost_per_conversion_goal']
        elif 'cost_per_conversion_goal' in data:
            global_goals.cost_per_conversion_goal = None
            
        if 'goal_mode' in data:
            global_goals.goal_mode = data['goal_mode']
        
        global_goals.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Global goals updated successfully',
            'goals': {
                'ctr_goal': float(global_goals.ctr_goal) if global_goals.ctr_goal else None,
                'conversion_rate_goal': float(global_goals.conversion_rate_goal) if global_goals.conversion_rate_goal else None,
                'cost_per_click_goal': float(global_goals.cost_per_click_goal) if global_goals.cost_per_click_goal else None,
                'cost_per_conversion_goal': float(global_goals.cost_per_conversion_goal) if global_goals.cost_per_conversion_goal else None,
                'goal_mode': global_goals.goal_mode
            }
        })
        
    except Exception as e:
        logger.error(f"Error setting global goals: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def platform_accounts_resync(request):
    """API endpoint to trigger manual resync of platform accounts"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        platform_id = data.get('platform_id')
        
        if not platform_id:
            return JsonResponse({'error': 'platform_id is required'}, status=400)
        
        # Get the selected tenant
        selected_tenant_id = request.session.get('selected_tenant_id')
        if not selected_tenant_id:
            return JsonResponse({'error': 'No tenant selected'}, status=400)
        
        # Verify user has access to tenant
        tenant = get_object_or_404(Tenant, id=selected_tenant_id, users=request.user)
        
        # Get the platform type
        try:
            platform_type = PlatformType.objects.get(id=platform_id)
        except PlatformType.DoesNotExist:
            return JsonResponse({'error': f'Platform type with ID {platform_id} not found'}, status=404)
        
        # Get active connections for this platform type
        connections = PlatformConnection.objects.filter(
            tenant=tenant,
            platform_type=platform_type,
            is_active=True
        )
        
        if not connections.exists():
            return JsonResponse({'error': 'No active connections found for this platform'}, status=404)
        
        # For Google Ads, run the sync using the new account service
        if platform_type.slug == 'google-ads':
            try:
                # Initialize new account service
                from .services.google_ads_account_service import GoogleAdsAccountService
                service = GoogleAdsAccountService(tenant)
                
                # Track sync results
                total_synced = 0
                successful_syncs = 0
                failed_syncs = 0
                
                # Process each connection
                for connection in connections:
                    logger.info(f"Starting resync for connection {connection.id}")
                    
                    try:
                        # Use the new service to sync accounts
                        success = service.sync_accounts(connection)
                        
                        if success:
                            successful_syncs += 1
                            logger.info(f"Successfully synced connection {connection.id}")
                        else:
                            failed_syncs += 1
                            logger.error(f"Failed to sync connection {connection.id}")
                        
                    except Exception as e:
                        failed_syncs += 1
                        logger.error(f"Failed to sync connection {connection.id}: {str(e)}")
                        
                    total_synced += 1
                
                # Check if any syncs were successful
                if successful_syncs > 0:
                    # Get updated account count
                    from .models import GoogleAdsAccount
                    account_count = GoogleAdsAccount.objects.filter(
                        platform_connection__in=connections,
                        sync_status='active'
                    ).count()
                    
                    logger.info(f"Resync completed: {successful_syncs} successful, {failed_syncs} failed")
                    
                    return JsonResponse({
                        'success': True,
                        'message': f'Successfully synced {successful_syncs} connection(s)',
                        'accounts_synced': account_count,
                        'connections_processed': total_synced,
                        'successful_syncs': successful_syncs,
                        'failed_syncs': failed_syncs
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'error': f'All {total_synced} sync attempts failed'
                    })
                    
            except Exception as e:
                logger.error(f"Error during Google Ads resync: {str(e)}")
                return JsonResponse({'error': f'Sync failed: {str(e)}'}, status=500)
        
        # For other platforms, return not implemented
        return JsonResponse({'error': f'Resync not implemented for platform: {platform_type.slug}'}, status=501)
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in platform_accounts_resync: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def account_campaigns_api(request, account_id):
    """API endpoint to get campaigns for an account"""
    # Verify access to account
    account = get_object_or_404(
        ClientPlatformAccount.objects.select_related('client__tenant'), 
        id=account_id,
        client__tenant__users=request.user
    )
    
    # Get campaigns for this account
    campaigns = []
    
    # Handle different platform types
    if account.platform_connection.platform_type.slug == 'google-ads':
        # Get Google Ads campaigns
        google_campaigns = GoogleAdsCampaign.objects.filter(
            client_account=account
        )
        
        campaigns = [{
            'id': campaign.id,
            'name': campaign.name,
            'status': campaign.status
        } for campaign in google_campaigns]
    
    return JsonResponse({'campaigns': campaigns})

@login_required
def campaign_budget_dashboard(request, client_id, account_id=None, campaign_id=None):
    """View for monitoring campaign-level budgets"""
    # Get the client and verify access
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    
    # Make sure the session has the correct tenant
    request.session['selected_tenant_id'] = client.tenant.id
    
    # Get filters
    accounts = ClientPlatformAccount.objects.filter(client=client, is_active=True)
    
    # If account_id is provided, filter by that account
    if account_id:
        account = get_object_or_404(ClientPlatformAccount, id=account_id, client=client)
        campaigns = GoogleAdsCampaign.objects.filter(client_account=account)
    else:
        campaigns = GoogleAdsCampaign.objects.filter(client_account__in=accounts)
    
    # If campaign_id is provided, filter to that campaign
    if campaign_id:
        campaigns = campaigns.filter(id=campaign_id)
    
    # Get budget data for these campaigns
    campaign_data = []
    
    for campaign in campaigns:
        # Find budget allocations for this campaign
        allocations = BudgetAllocation.objects.filter(
            campaign=campaign,
            budget__is_active=True
        ).select_related('budget')
        
        # If there are no explicit allocations, we'll just show the campaign's own budget
        if not allocations:
            # Get the campaign's daily budget and multiply by days in month for a rough monthly estimate
            if campaign.budget_amount:
                today = timezone.now().date()
                days_in_month = calendar.monthrange(today.year, today.month)[1]
                monthly_budget_estimate = float(campaign.budget_amount) * days_in_month
                
                # Get actual spend for the current month
                month_start = today.replace(day=1)
                spend_data = GoogleAdsDailyMetrics.objects.filter(
                    campaign=campaign,
                    date__gte=month_start,
                    date__lte=today
                ).aggregate(
                    total_spend=Sum('cost'),
                    total_days=Count('date', distinct=True)
                )
                
                total_spend = float(spend_data['total_spend'] or 0)
                spend_percentage = (total_spend / monthly_budget_estimate) * 100 if monthly_budget_estimate else 0
                
                # Calculate expected spend based on days elapsed
                days_elapsed = spend_data['total_days'] or 0
                expected_spend = (monthly_budget_estimate / days_in_month) * days_elapsed if days_in_month else 0
                expected_percentage = (expected_spend / monthly_budget_estimate) * 100 if monthly_budget_estimate else 0
                
                # Calculate pacing
                pacing = (total_spend / expected_spend) * 100 if expected_spend else 0
                
                campaign_data.append({
                    'campaign': campaign,
                    'allocation_type': 'campaign',
                    'budget_amount': monthly_budget_estimate,
                    'spend_amount': total_spend,
                    'spend_percentage': spend_percentage,
                    'expected_spend': expected_spend,
                    'expected_percentage': expected_percentage,
                    'pacing': pacing,
                    'status': get_status_from_pacing(pacing)
                })
        else:
            # Process each allocation
            for allocation in allocations:
                budget = allocation.budget
                allocated_amount = allocation.amount
                
                # Get date range for this budget
                start_date = budget.start_date
                end_date = budget.end_date
                today = timezone.now().date()
                
                if today < start_date or today > end_date:
                    continue  # Skip if today is outside budget period
                
                # Get actual spend for this campaign in the budget period
                spend_data = GoogleAdsDailyMetrics.objects.filter(
                    campaign=campaign,
                    date__gte=start_date,
                    date__lte=min(today, end_date)
                ).aggregate(
                    total_spend=Sum('cost'),
                    total_days=Count('date', distinct=True)
                )
                
                total_spend = float(spend_data['total_spend'] or 0)
                spend_percentage = (total_spend / allocated_amount) * 100 if allocated_amount else 0
                
                # Calculate expected spend based on days elapsed
                days_elapsed = (min(today, end_date) - start_date).days + 1
                days_in_period = (end_date - start_date).days + 1
                expected_spend = (allocated_amount / days_in_period) * days_elapsed if days_in_period else 0
                expected_percentage = (expected_spend / allocated_amount) * 100 if allocated_amount else 0
                
                # Calculate pacing
                pacing = (total_spend / expected_spend) * 100 if expected_spend else 0
                
                campaign_data.append({
                    'campaign': campaign,
                    'budget': budget,
                    'allocation_type': 'allocation',
                    'budget_amount': allocated_amount,
                    'spend_amount': total_spend,
                    'spend_percentage': spend_percentage,
                    'expected_spend': expected_spend,
                    'expected_percentage': expected_percentage,
                    'pacing': pacing,
                    'status': get_status_from_pacing(pacing)
                })
    
    context = {
        'client': client,
        'accounts': accounts,
        'selected_account': account_id,
        'campaigns': campaigns,
        'campaign_data': campaign_data,
        'page_title': 'Campaign Budgets'
    }
    return render(request, 'campaign_budget_dashboard.html', context)


def get_status_from_pacing(pacing):
    """Determine budget status from pacing percentage"""
    if pacing < 85:
        return 'underspend'
    elif pacing > 115:
        return 'overspend'
    else:
        return 'on-track'
    
@login_required
def client_dashboard(request, client_id):
    """
    Client dashboard view - centralized access point for client data
    """
    # Use select_related to fetch tenant in the same query
    client = get_object_or_404(
        Client.objects.select_related('tenant'),
        id=client_id, 
        tenant__users=request.user
    )
    
    # Update session with correct tenant
    request.session['selected_tenant_id'] = client.tenant.id
    
    # Get platform accounts with prefetching for efficiency
    platform_accounts = ClientPlatformAccount.objects.filter(
        client=client,
        is_active=True
    ).select_related(
        'platform_connection__platform_type'
    )
    
    # Get client groups this client belongs to
    client_groups = client.groups.filter(is_active=True)
    
    # Get relevant budget information
    client_budgets = Budget.objects.filter(
        Q(client=client) | Q(client_group__in=client_groups),
        is_active=True
    ).select_related('client', 'client_group')
    
    context = {
        'client': client,
        'platform_accounts': platform_accounts,
        'client_groups': client_groups,
        'client_budgets': client_budgets,
        'page_title': f'{client.name} Dashboard'
    }
    return render(request, 'client_dashboard.html', context)


def mockup(request):
    """
    Enhanced home view with dashboard preview features for Google Ads API approval
    """
    # Prepare context
    context = {
        'total_clients_count': 0,
        'active_clients_count': 0,
        'all_clients': []
    }

    # Add clients if a tenant is selected (tenant is now provided by context processor)
    selected_tenant_id = request.session.get('selected_tenant_id')
    if selected_tenant_id:
        # Prefetch groups to avoid N+1 queries when displaying client groups in the template
        active_clients = Client.objects.filter(
            tenant_id=selected_tenant_id, 
            is_active=True
        ).prefetch_related(
            Prefetch('groups', queryset=ClientGroup.objects.filter(is_active=True))
        )
        
        # Count total clients separately to avoid fetching unnecessary data
        all_clients_count = Client.objects.filter(tenant_id=selected_tenant_id).count()
        
        # Get platform connections for this tenant
        platform_connections = PlatformConnection.objects.filter(
            tenant_id=selected_tenant_id,
            is_active=True
        ).select_related('platform_type')
        
        # Count connections by platform type
        platform_counts = {}
        for connection in platform_connections:
            platform_type = connection.platform_type.name
            if platform_type in platform_counts:
                platform_counts[platform_type] += 1
            else:
                platform_counts[platform_type] = 1

        # Add to context
        context['all_clients'] = active_clients
        context['total_clients_count'] = all_clients_count
        context['active_clients_count'] = active_clients.count()
        context['platform_connections'] = platform_connections
        context['platform_counts'] = platform_counts
        context['page_title'] = 'Home'

    return render(request, 'mockup.html', context)


@login_required
def clients_api(request):
    """API endpoint to get clients for the selected tenant"""
    # Get the selected tenant from session
    selected_tenant_id = request.session.get('selected_tenant_id')
    
    if not selected_tenant_id:
        return JsonResponse({'status': 'error', 'message': 'No tenant selected'})
    
    # Get the tenant and verify the user has access to it
    try:
        tenant = Tenant.objects.get(id=selected_tenant_id, users=request.user)
    except Tenant.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Tenant not found'})
    
    # Get clients with prefetched groups
    clients = Client.objects.filter(
        tenant=tenant,
        is_active=True
    ).prefetch_related(
        Prefetch('groups', queryset=ClientGroup.objects.filter(is_active=True))
    )
    
    # Format client data for JSON response
    client_data = []
    for client in clients:
        groups_data = []
        for group in client.groups.all():
            groups_data.append({
                'id': group.id,
                'name': group.name,
                'color': group.color,
                'icon_class': group.icon_class
            })
        
        client_data.append({
            'id': client.id,
            'name': client.name,
            'logo': client.logo.url if client.logo and client.logo.name else None,
            'created_at': client.created_at.strftime('%b %d, %Y'),
            'is_active': client.is_active,
            'groups': groups_data
        })
    
    return JsonResponse({
        'status': 'success',
        'clients': client_data
    })
# Tag Management API Views
from django.views.decorators.http import require_http_methods
import json

@login_required
@require_http_methods(["GET"])
def get_campaign_tags(request, campaign_id):
    """API endpoint to get all tags for a campaign"""
    campaign = get_object_or_404(GoogleAdsCampaign, id=campaign_id)
    
    # Ensure user has access to the client account (security check)
    client_account = campaign.client_account
    if client_account.client.tenant not in request.user.tenants.all():
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
    
    # Get all tags for this campaign
    tag_assignments = CampaignTagAssignment.objects.filter(campaign=campaign).select_related('tag')
    
    tags = []
    for assignment in tag_assignments:
        tags.append({
            'id': assignment.tag.id,
            'name': assignment.tag.name,
            'color': assignment.tag.color,
            'assignment_id': assignment.id
        })
    
    return JsonResponse({'success': True, 'tags': tags})

@login_required
@require_http_methods(["POST"])
def add_tag_to_campaign(request, campaign_id, tag_id):
    """API endpoint to add a tag to a campaign"""
    campaign = get_object_or_404(GoogleAdsCampaign, id=campaign_id)
    
    # Ensure user has access (security check)
    client_account = campaign.client_account
    if client_account.client.tenant not in request.user.tenants.all():
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
    
    # Get the tenant from the client
    tenant = client_account.client.tenant
    
    # Get the tag, ensuring it belongs to the same tenant
    tag = get_object_or_404(CampaignTag, id=tag_id, tenant=tenant)
    
    # Check if the tag is already assigned to this campaign
    assignment_exists = CampaignTagAssignment.objects.filter(
        campaign=campaign,
        tag=tag
    ).exists()
    
    if assignment_exists:
        return JsonResponse({'success': True, 'already_exists': True})
    
    # Create the assignment
    assignment = CampaignTagAssignment.objects.create(
        campaign=campaign,
        tag=tag,
        created_by=request.user
    )
    
    return JsonResponse({
        'success': True,
        'already_exists': False,
        'assignment': {
            'id': assignment.id,
            'tag_id': tag.id,
            'campaign_id': campaign.id
        }
    })

@login_required
@require_http_methods(["DELETE"])
def remove_tag_from_campaign(request, campaign_id, tag_id):
    """API endpoint to remove a tag from a campaign"""
    campaign = get_object_or_404(GoogleAdsCampaign, id=campaign_id)
    
    # Ensure user has access (security check)
    client_account = campaign.client_account
    if client_account.client.tenant not in request.user.tenants.all():
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
    
    # Get the tenant from the client
    tenant = client_account.client.tenant
    
    # Get the tag, ensuring it belongs to the same tenant
    tag = get_object_or_404(CampaignTag, id=tag_id, tenant=tenant)
    
    # Check if the tag is assigned to this campaign
    try:
        assignment = CampaignTagAssignment.objects.get(
            campaign=campaign,
            tag=tag
        )
        assignment.delete()
        return JsonResponse({'success': True})
    except CampaignTagAssignment.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Tag is not assigned to this campaign'})

@login_required
@ensure_csrf_cookie
def create_tag(request):
    """API endpoint to create a new tag"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Only POST method is allowed'}, status=405)
    
    # Get data from the request - handle both JSON and form data
    try:
        if request.content_type and 'application/json' in request.content_type:
            try:
                if not request.body:
                    logger.error("Empty request body")
                    return JsonResponse({'success': False, 'error': 'No data provided'})
                
                # Try to decode as UTF-8 and handle potential encoding issues
                try:
                    body_str = request.body.decode('utf-8')
                except UnicodeDecodeError:
                    body_str = request.body.decode('latin-1')  # Fallback encoding
                
                data = json.loads(body_str)
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {str(e)}, body: {request.body[:100]}")
                return JsonResponse({'success': False, 'error': f'Invalid JSON data: {str(e)}'})
        else:
            # Handle form data
            data = request.POST.dict()
        
        # Log the received data for debugging
        logger.debug(f"Tag create request data: {data}")
        
        tag_name = data.get('name', '').strip()
        tag_color = data.get('color', '#6c757d')
        
        if not tag_name:
            return JsonResponse({'success': False, 'error': 'Tag name is required'})
        
        # Get the tenant from the user's selected tenant
        tenant_id = request.session.get('selected_tenant_id')
        if not tenant_id:
            logger.error("No tenant selected in session")
            return JsonResponse({'success': False, 'error': 'No tenant selected'}, status=400)
            
        try:
            tenant = Tenant.objects.get(id=tenant_id)
            # Verify user has access to this tenant
            if request.user not in tenant.users.all():
                logger.error(f"User {request.user.id} attempted to access unauthorized tenant {tenant_id}")
                return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        except Tenant.DoesNotExist:
            logger.error(f"Tenant not found: {tenant_id}")
            return JsonResponse({'success': False, 'error': 'Invalid tenant'}, status=404)
        
        # Check if a tag with this name already exists for this tenant
        if CampaignTag.objects.filter(tenant=tenant, name=tag_name).exists():
            return JsonResponse({'success': False, 'error': 'A tag with this name already exists'})
        
        # Create the tag
        tag = CampaignTag.objects.create(
            tenant=tenant,
            name=tag_name,
            color=tag_color,
            created_by=request.user
        )
        
        # Log successful tag creation
        logger.info(f"Tag created: {tag.id} - {tag.name} for tenant {tenant.id}")
        
        return JsonResponse({
            'success': True,
            'tag': {
                'id': tag.id,
                'name': tag.name,
                'color': tag.color
            }
        })
        
    except Exception as e:
        # Log the error and return a more descriptive error message
        logger.error(f"Error creating tag: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Failed to create tag: {str(e)}'}, status=500)

@login_required
@ensure_csrf_cookie
def manage_campaign_tag(request, campaign_id, tag_id):
    """
    API endpoint to add or remove a tag from a campaign.
    Handles both POST (add) and DELETE (remove) methods.
    """
    # Get the campaign and verify access
    campaign = get_object_or_404(GoogleAdsCampaign, id=campaign_id)
    
    # Ensure user has access (security check)
    client_account = campaign.client_account
    if client_account.client.tenant not in request.user.tenants.all():
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
    
    # Get the tenant from the client
    tenant = client_account.client.tenant
    
    # Get the tag, ensuring it belongs to the same tenant
    tag = get_object_or_404(CampaignTag, id=tag_id, tenant=tenant)
    
    # Handle the request based on the HTTP method
    if request.method == 'POST':
        # Add tag to campaign
        # Check if the tag is already assigned to this campaign
        assignment_exists = CampaignTagAssignment.objects.filter(
            campaign=campaign,
            tag=tag
        ).exists()
        
        if assignment_exists:
            return JsonResponse({'success': True, 'already_exists': True})
        
        # Create the assignment
        assignment = CampaignTagAssignment.objects.create(
            campaign=campaign,
            tag=tag,
            created_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'already_exists': False,
            'assignment': {
                'id': assignment.id,
                'tag_id': tag.id,
                'campaign_id': campaign.id
            }
        })
        
    elif request.method == 'DELETE':
        # Remove tag from campaign
        try:
            assignment = CampaignTagAssignment.objects.get(
                campaign=campaign,
                tag=tag
            )
            assignment.delete()
            return JsonResponse({'success': True})
        except CampaignTagAssignment.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Tag is not assigned to this campaign'})
    
    # If neither POST nor DELETE
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)

