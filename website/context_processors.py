def tenant_context(request):
    """Adds tenant-related context variables to all templates"""
    context = {
        'all_user_tenants': [],
        'selected_tenant': None,
        'all_clients': []  # This will hold all active clients for the selected tenant
    }
    
    # Only add these for authenticated users
    if request.user.is_authenticated:
        from website.models import Tenant, Client, ClientGroup
        from django.db.models import Prefetch
        
        # Get all tenants the user has access to
        all_user_tenants = Tenant.objects.filter(users=request.user, is_active=True)
        context['all_user_tenants'] = all_user_tenants
        
        # Get selected tenant from session
        selected_tenant_id = request.session.get('selected_tenant_id')
        
        # If no tenant is selected but user has tenants, select the first one
        if not selected_tenant_id and all_user_tenants.exists():
            selected_tenant_id = all_user_tenants.first().id
            request.session['selected_tenant_id'] = selected_tenant_id
        
        # Now that we have a tenant ID (if available), get the tenant and its clients
        if selected_tenant_id:
            try:
                selected_tenant = all_user_tenants.get(id=selected_tenant_id)
                context['selected_tenant'] = selected_tenant
                
                # Add active clients for the selected tenant
                active_clients = Client.objects.filter(
                    tenant=selected_tenant,
                    is_active=True
                ).prefetch_related(
                    Prefetch('groups', queryset=ClientGroup.objects.filter(is_active=True))
                ).order_by('name')
                
                context['all_clients'] = active_clients
                
            except Tenant.DoesNotExist:
                # If the selected tenant doesn't exist, fall back to the first tenant
                if all_user_tenants.exists():
                    context['selected_tenant'] = all_user_tenants.first()
                    request.session['selected_tenant_id'] = context['selected_tenant'].id
                    
                    # Get active clients for the fallback tenant
                    active_clients = Client.objects.filter(
                        tenant=context['selected_tenant'],
                        is_active=True
                    ).prefetch_related(
                        Prefetch('groups', queryset=ClientGroup.objects.filter(is_active=True))
                    ).order_by('name')
                    
                    context['all_clients'] = active_clients
    
    return context