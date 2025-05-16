from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django import forms
from .models import Tenant, Client, PlatformSettings, PlatformConnection, ClientPlatformAccount, ClientGroup, BudgetAllocation, BudgetAlert, Budget, GoogleAdsCampaign, Competitor

class SignUpForm(UserCreationForm):
    email = forms.EmailField(label="", widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}))
    first_name = forms.CharField(label="", max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}))
    last_name = forms.CharField(label="", max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}))

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super(SignUpForm, self).__init__(*args, **kwargs)

        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['username'].widget.attrs['placeholder'] = 'Username'
        self.fields['username'].label = ''
        self.fields['username'].help_text = '<span class="form-text text-muted"><small>Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.</small></span>'

        self.fields['password1'].widget.attrs['class'] = 'form-control'
        self.fields['password1'].widget.attrs['placeholder'] = 'Password'
        self.fields['password1'].label = ''
        self.fields['password1'].help_text = '<ul class="form-text text-muted small"><li>Your password can\'t be too similar to your other personal information.</li><li>Your password must contain at least 8 characters.</li><li>Your password can\'t be a commonly used password.</li><li>Your password can\'t be entirely numeric.</li></ul>'

        self.fields['password2'].widget.attrs['class'] = 'form-control'
        self.fields['password2'].widget.attrs['placeholder'] = 'Confirm Password'
        self.fields['password2'].label = ''
        self.fields['password2'].help_text = '<span class="form-text text-muted"><small>Enter the same password as before, for verification.</small></span>'

class TenantForm(forms.ModelForm):
    """
    Form for creating and managing tenants
    """
    description = forms.CharField(
        label='Description',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Optional: Brief description of the tenant',
            'rows': 3
        })
    )

    class Meta:
        model = Tenant
        fields = ['name', 'logo', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Tenant Name'
            })
        }

    def save(self, commit=True, created_by=None):
        """
        Custom save method to allow setting additional attributes
        """
        instance = super().save(commit=False)
        
        if commit:
            instance.save()
            
            # If a user is provided, add them to the tenant's users
            if created_by:
                instance.users.add(created_by)
        
        return instance

# Add to your forms.py file

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'name', 'description', 'logo', 
            'industry', 'company_size', 'revenue_range', 'geographic_focus',
            'business_model_types', 'marketing_maturity', 'website'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Client Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 3}),
            'industry': forms.Select(attrs={'class': 'form-select'}),
            'company_size': forms.Select(attrs={'class': 'form-select'}),
            'revenue_range': forms.Select(attrs={'class': 'form-select'}),
            'geographic_focus': forms.Select(attrs={'class': 'form-select'}),
            'marketing_maturity': forms.Select(attrs={'class': 'form-select'}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://example.com'})
        }


# Add a new form for competitors
class CompetitorForm(forms.ModelForm):
    class Meta:
        model = Competitor
        fields = ['name', 'website', 'description', 'strength', 'advantages']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Competitor Name'}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://competitor.com'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Brief description of the competitor', 'rows': 2}),
            'strength': forms.Select(attrs={'class': 'form-select'}),
            'advantages': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Key advantages or strengths of this competitor', 'rows': 3}),
        }


    class Meta:
        model = Client
        fields = [
            'name', 'description', 'logo', 
            'company_size', 'revenue_range', 'geographic_focus',
            'business_model_types', 'marketing_maturity'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Client Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 3}),
            'company_size': forms.Select(attrs={'class': 'form-select'}),
            'revenue_range': forms.Select(attrs={'class': 'form-select'}),
            'geographic_focus': forms.Select(attrs={'class': 'form-select'}),
            'marketing_maturity': forms.Select(attrs={'class': 'form-select'}),
        }

class PlatformSettingsForm(forms.ModelForm):
    """
    Form for platform-specific settings
    """
    class Meta:
        model = PlatformSettings
        fields = ['settings']
        widgets = {
            'settings': forms.HiddenInput(),  # We'll handle this with custom fields
        }
    
    def __init__(self, *args, platform_type=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.platform_type = platform_type
        
        # Initialize with current settings if available
        current_settings = {}
        if self.instance and self.instance.pk:
            current_settings = self.instance.settings or {}
        
        # Add dynamic fields based on platform type
        if platform_type:
            if platform_type.slug == 'google-ads':
                self.fields['customer_id'] = forms.CharField(
                    label='Google Ads Customer ID',
                    required=False,
                    initial=current_settings.get('customer_id', ''),
                    help_text='Your Google Ads Customer ID (e.g., 123-456-7890)',
                    widget=forms.TextInput(attrs={'class': 'form-control'})
                )
                self.fields['auto_refresh'] = forms.BooleanField(
                    label='Automatically refresh token',
                    required=False,
                    initial=current_settings.get('auto_refresh', True),
                    help_text='Automatically refresh the token when it expires'
                )
            
            # Add fields for other platform types as needed
            # elif platform_type.slug == 'facebook-ads':
            #     ...
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Build settings JSON from form fields
        settings = {}
        
        if self.platform_type:
            if self.platform_type.slug == 'google-ads':
                settings['customer_id'] = cleaned_data.get('customer_id', '')
                settings['auto_refresh'] = cleaned_data.get('auto_refresh', True)
            
            # Add settings for other platform types as needed
            # elif self.platform_type.slug == 'facebook-ads':
            #     ...
        
        # Set the settings field
        cleaned_data['settings'] = settings
        
        return cleaned_data

class RefreshTokenForm(forms.Form):
    """
    Form for refreshing a platform connection token
    """
    connection_id = forms.IntegerField(widget=forms.HiddenInput())
    
    def __init__(self, *args, connection=None, **kwargs):
        super().__init__(*args, **kwargs)
        if connection:
            self.fields['connection_id'].initial = connection.id



# The ClientGoogleAdsForm has been removed as it's no longer needed
        
# Add to forms.py

class ClientGroupForm(forms.ModelForm):
    """
    Form for creating and managing client groups
    """
    class Meta:
        model = ClientGroup
        fields = ['name', 'description', 'icon_class', 'color']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Group Name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Description', 'rows': 3}),
            'icon_class': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'bi-collection'}),
            'color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color', 'value': '#6c757d'}),
        }
    
    # Define the clients field explicitly
    clients = forms.ModelMultipleChoiceField(
        queryset=Client.objects.none(),  # Initially empty, will be set in __init__
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'list-unstyled'}),
        label="Select clients to add to this group"
    )
    
    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        
        # If tenant is provided, filter clients by this tenant
        if tenant:
            self.fields['clients'].queryset = Client.objects.filter(tenant=tenant, is_active=True)
        elif self.instance and self.instance.pk:
            # If editing an existing group, use its tenant
            self.fields['clients'].queryset = Client.objects.filter(tenant=self.instance.tenant, is_active=True)
            
            # Set initial values for clients field
            self.fields['clients'].initial = self.instance.clients.all()
    

# Forms for budget management

class BudgetForm(forms.ModelForm):
    """Form for creating and editing budgets"""
    # Fields for selecting client or client group
    entity_type = forms.ChoiceField(
        choices=[('client', 'Client'), ('group', 'Client Group'), ('tenant', 'Tenant-wide')],
        widget=forms.RadioSelect,
        initial='client',
        required=True
    )
    
    class Meta:
        model = Budget
        fields = ['name', 'description', 'amount', 'start_date', 'end_date', 'frequency']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.tenant = kwargs.pop('tenant', None)
        super().__init__(*args, **kwargs)
        
        if self.tenant:
            # Add client dropdown
            self.fields['client'] = forms.ModelChoiceField(
                queryset=Client.objects.filter(tenant=self.tenant, is_active=True),
                required=False,
                empty_label="Select a client"
            )
            
            # Add client group dropdown
            self.fields['client_group'] = forms.ModelChoiceField(
                queryset=ClientGroup.objects.filter(tenant=self.tenant, is_active=True),
                required=False,
                empty_label="Select a client group"
            )
        
        # If this is an edit form, set the entity_type
        if self.instance.pk:
            if self.instance.client:
                self.initial['entity_type'] = 'client'
            elif self.instance.client_group:
                self.initial['entity_type'] = 'group'
            else:
                self.initial['entity_type'] = 'tenant'
    
    def clean(self):
        cleaned_data = super().clean()
        entity_type = cleaned_data.get('entity_type')
        client = cleaned_data.get('client')
        client_group = cleaned_data.get('client_group')
        
        if entity_type == 'client' and not client:
            self.add_error('client', 'Please select a client.')
        
        if entity_type == 'group' and not client_group:
            self.add_error('client_group', 'Please select a client group.')
        
        # Ensure start_date is before or equal to end_date
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            self.add_error('end_date', 'End date must be after start date.')
        
        return cleaned_data
    
    def save(self, commit=True):
        budget = super().save(commit=False)
        
        # Set client or client_group based on entity_type
        entity_type = self.cleaned_data.get('entity_type')
        
        if entity_type == 'client':
            budget.client = self.cleaned_data.get('client')
            budget.client_group = None
        elif entity_type == 'group':
            budget.client = None
            budget.client_group = self.cleaned_data.get('client_group')
        else:  # tenant-wide
            budget.client = None
            budget.client_group = None
        
        if commit:
            budget.save()
        
        return budget


class BudgetAllocationForm(forms.ModelForm):
    """Form for budget allocations"""
    class Meta:
        model = BudgetAllocation
        fields = ['platform_type', 'platform_account', 'campaign', 'amount', 'percentage']
    
    def __init__(self, *args, **kwargs):
        self.budget = kwargs.pop('budget', None)
        super().__init__(*args, **kwargs)
        
        if self.budget and self.budget.client:
            # Limit platform accounts to those of the client
            self.fields['platform_account'].queryset = ClientPlatformAccount.objects.filter(
                client=self.budget.client,
                is_active=True
            )
            
            # Limit campaigns based on the client's platform accounts
            platform_accounts = ClientPlatformAccount.objects.filter(
                client=self.budget.client,
                is_active=True
            )
            
            self.fields['campaign'].queryset = GoogleAdsCampaign.objects.filter(
                client_account__in=platform_accounts
            )


class BudgetAlertForm(forms.ModelForm):
    """Form for budget alerts"""
    class Meta:
        model = BudgetAlert
        fields = ['alert_type', 'threshold', 'is_email_enabled', 'is_dashboard_enabled']