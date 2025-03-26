from django.urls import path
from . import views
from . import google_ads_views
from . import dashboard_views  # Import the new dashboard views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_user, name='login'),
    path('logout/', views.logout_user, name='logout'),
    path('register/', views.register_user, name='register'),
    
    # Dashboard URLs
    path('agency-dashboard/', dashboard_views.agency_dashboard, name='agency_dashboard'),
    
    # Tenant switching URL
    path('switch-tenant/<int:tenant_id>/', views.switch_tenant, name='switch_tenant'),
    
    # Tenant creation URL (admin-only)
    path('create-tenant/', views.create_tenant, name='create_tenant'),
    
    # Client management URLs
    path('create-client/', views.create_client, name='create_client'),
    path('client/<int:client_id>/', views.client_detail, name='client_detail'),
    path('client/<int:client_id>/edit/', views.edit_client, name='edit_client'),
    path('client/<int:client_id>/archive/', views.archive_client, name='archive_client'),
    path('client/<int:client_id>/dashboard/', dashboard_views.client_dashboard, name='client_dashboard'),  # Use new dashboard view
    
    # Tenant Platform Management URLs
    path('tenant/platforms/', views.tenant_platforms, name='tenant_platforms'),
    path('tenant/platform/<int:platform_id>/connect/', views.connect_platform_to_tenant, name='connect_platform_to_tenant'),
    path('tenant/oauth-callback/', views.tenant_oauth_callback, name='tenant_oauth_callback'),
    path('tenant/platform-connection/<int:connection_id>/', views.manage_tenant_platform_connection, name='manage_tenant_platform_connection'),
    
    # Client Platform URLs
    path('client/<int:client_id>/connect-platform/', views.connect_platform, name='connect_platform'),
    path('client/<int:client_id>/platform/<int:platform_id>/connect/', views.initiate_platform_connection, name='initiate_platform_connection'),
    path('client/<int:client_id>/platform/<int:platform_id>/manage/', views.manage_platform_connection, name='manage_platform_connection'),
    path('oauth-callback/', views.oauth_callback, name='oauth_callback'),
    path('client/<int:client_id>/add-google-ads/', views.add_client_google_ads, name='add_client_google_ads'),
    path('client-platform-account/<int:account_id>/remove/', views.remove_client_platform_account, name='remove_client_platform_account'),
    path('client-platform-account/<int:account_id>/reactivate/', views.reactivate_client_platform_account, name='reactivate_client_platform_account'),
    
    # Google Ads Data URLs
    path('client/<int:client_id>/google-ads/<int:account_id>/', google_ads_views.google_ads_campaigns, name='google_ads_campaigns'),
    path('client/<int:client_id>/google-ads/<int:account_id>/campaign/<int:campaign_id>/', google_ads_views.google_ads_campaign_detail, name='google_ads_campaign_detail'),
    path('client/<int:client_id>/google-ads/<int:account_id>/sync/', google_ads_views.sync_google_ads_data, name='sync_google_ads_data'),

    # Client Group URLs
    path('client-groups/', views.client_groups, name='client_groups'),
    path('client-groups/create/', views.create_client_group, name='create_client_group'),
    path('client-groups/<int:group_id>/edit/', views.edit_client_group, name='edit_client_group'),
    path('client-groups/<int:group_id>/delete/', views.delete_client_group, name='delete_client_group'),
    path('client-groups/<int:group_id>/remove-client/<int:client_id>/', views.remove_client_from_group, name='remove_client_from_group'),
    path('client-groups/<int:group_id>/clients-json/', views.client_group_clients_json, name='client_group_clients_json'),

    # Budget management URLs
    path('budgets/', views.budget_dashboard, name='budget_dashboard'),
    path('budgets/create/', views.create_budget, name='create_budget'),
    path('budgets/<int:budget_id>/', views.budget_detail, name='budget_detail'),
    path('budgets/<int:budget_id>/edit/', views.edit_budget, name='edit_budget'),
    path('budgets/<int:budget_id>/deactivate/', views.deactivate_budget, name='deactivate_budget'),
    path('budgets/<int:budget_id>/alerts/create/', views.create_budget_alert, name='create_budget_alert'),
    
    # Campaign Budget URLs
    path('client/<int:client_id>/campaign-budgets/', views.campaign_budget_dashboard, name='campaign_budget_dashboard'),
    path('client/<int:client_id>/account/<int:account_id>/campaign-budgets/', views.campaign_budget_dashboard, name='campaign_budget_dashboard_filtered'),
    
    # Budget API endpoints
    path('api/platform/<int:platform_id>/accounts/', views.platform_accounts_api, name='platform_accounts_api'),
    path('api/account/<int:account_id>/campaigns/', views.account_campaigns_api, name='account_campaigns_api'),
]