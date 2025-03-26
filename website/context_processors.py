def tenant_context(request):
    """Adds tenant-related context variables to all templates"""
    context = {
        'all_user_tenants': [],
        'selected_tenant': None,
        'all_clients': []  # Changed from 'active_clients' to 'all_clients'
    }
    
    # Only add these for authenticated users
    if request.user.is_authenticated:
        from website.models import Tenant, Client
        
        # Get all tenants the user has access to
        all_user_tenants = Tenant.objects.filter(users=request.user, is_active=True)
        context['all_user_tenants'] = all_user_tenants
        
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        if selected_tenant_id:
            try:
                selected_tenant = all_user_tenants.get(id=selected_tenant_id)
                context['selected_tenant'] = selected_tenant
                
                # Add active clients for the selected tenant
                active_clients = Client.objects.filter(
                    tenant=selected_tenant,
                    is_active=True
                ).order_by('name')
                context['all_clients'] = active_clients  # Changed from 'active_clients' to 'all_clients'
                
            except Tenant.DoesNotExist:
                if all_user_tenants.exists():
                    # Fallback to first tenant if selected one doesn't exist
                    context['selected_tenant'] = all_user_tenants.first()
                    request.session['selected_tenant_id'] = context['selected_tenant'].id
                    
                    # Get active clients for the fallback tenant
                    active_clients = Client.objects.filter(
                        tenant=context['selected_tenant'],
                        is_active=True
                    ).order_by('name')
                    context['all_clients'] = active_clients  # Changed from 'active_clients' to 'all_clients'
        elif all_user_tenants.exists():
            # Default to first tenant if none selected
            context['selected_tenant'] = all_user_tenants.first()
            request.session['selected_tenant_id'] = context['selected_tenant'].id
            
            # Get active clients for the default tenant
            active_clients = Client.objects.filter(
                tenant=context['selected_tenant'],
                is_active=True
            ).order_by('name')
            context['all_clients'] = active_clients  # Changed from 'active_clients' to 'all_clients'
    
    return context