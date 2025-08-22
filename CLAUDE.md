# Pulse Development Guidelines

## Environment Configuration
```bash
# Required Railway Environment Variables
ENVIRONMENT=production  # Critical for enabling production mode
DEBUG=False
SECRET_KEY=your_secret_key

# Database Configuration
DB_ENGINE=django.db.backends.postgresql
DB_NAME=railway
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=your_host
DB_PORT=5432

# Google OAuth Configuration
GOOGLE_OAUTH_CLIENT_ID=your_google_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_google_client_secret
GOOGLE_ADS_DEVELOPER_TOKEN=your_developer_token
```

## Development Commands
```bash
# Run development server
python manage.py runserver

# Run tests
python manage.py test
python manage.py test website.tests.TestClassName.test_method_name

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Custom management commands
python manage.py init_platforms
python manage.py create_default_groups
```

## Coding Standards
- **Imports**: Standard library → third-party → Django → local applications, alphabetized in groups
- **Naming**: snake_case for variables/functions, CamelCase for classes, UPPER_CASE for constants
- **Type Hints**: Document in docstrings using Google-style format
- **Error Handling**: Use specific exception types, meaningful error messages, and logging
- **Documentation**: Google-style docstrings for all classes and non-trivial functions
- **Line Length**: Keep lines under 100 characters when possible
- **Indentation**: 4 spaces, no tabs
- **Separation of Concerns**: Use Django models, views, services architecture pattern
- **DRY Principle**: Abstract reusable logic into service classes or utility functions