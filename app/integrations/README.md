# API Integration Layer Implementation

This directory contains the complete API integration layer for Project Enigma, implementing task 007-api-integration-layer.md.

## Architecture Overview

The API integration layer follows a clean architecture pattern with:

- **Abstract base interfaces** defining contracts for all implementations
- **Mock implementations** for development and testing
- **Real API implementations** using actual service APIs
- **Configuration-based switching** between mock and real APIs
- **Comprehensive error handling** with service-specific exceptions
- **Rate limiting** to prevent API abuse
- **Authentication management** with token validation

## Directory Structure

```
integrations/
├── __init__.py                 # Main module exports
├── README.md                   # This documentation
├── exceptions.py               # API-specific exception classes
├── auth_manager.py             # Authentication and credential management
├── rate_limiter.py             # Rate limiting for API calls
├── factory.py                  # Factory for creating API clients
├── base/                       # Abstract interface definitions
│   ├── __init__.py
│   ├── jira_interface.py       # JIRA API interface
│   ├── github_interface.py     # GitHub API interface
│   └── confluence_interface.py # Confluence API interface
├── mock/                       # Mock implementations
│   ├── __init__.py
│   ├── mock_jira.py           # Mock JIRA client
│   ├── mock_github.py         # Mock GitHub client
│   └── mock_confluence.py     # Mock Confluence client
└── real/                       # Real API implementations
    ├── __init__.py
    ├── real_jira.py           # Real JIRA client using python-jira
    ├── real_github.py         # Real GitHub client using PyGithub
    └── real_confluence.py     # Real Confluence client using atlassian-python-api
```

## Key Features

### 1. Configuration-Based API Switching

The system automatically switches between mock and real APIs based on the `use_mock_apis` setting:

```python
from app.integrations import create_api_clients

# Uses setting from environment
clients = create_api_clients()

# Force mock APIs
clients = create_api_clients(use_mock=True)

# Force real APIs
clients = create_api_clients(use_mock=False)
```

### 2. Authentication Management

The `AuthenticationManager` handles secure credential management:

```python
from app.integrations import AuthenticationManager

auth_manager = AuthenticationManager()

# Validate credentials format
is_valid, error = auth_manager.validate_credentials("jira")

# Test actual connection
result = await auth_manager.validate_connection("jira")

# Validate all services
results = await auth_manager.validate_all_connections()
```

### 3. Rate Limiting

Automatic rate limiting prevents API abuse:

```python
from app.integrations import get_rate_limiter

rate_limiter = get_rate_limiter()

# Rate limiting is handled automatically in API clients
# Manual usage:
await rate_limiter.acquire("github", "get_repos")

# Check rate limit status
status = rate_limiter.get_status("github")
```

### 4. Error Handling

Comprehensive error handling with service-specific exceptions:

```python
from app.integrations.exceptions import (
    JiraAuthenticationError,
    GitHubRateLimitError,
    ConfluencePageNotFoundError
)

try:
    tickets = await jira_client.get_tickets_by_fix_version("v2.0.0")
except JiraAuthenticationError:
    # Handle authentication issues
    pass
except JiraRateLimitError as e:
    # Handle rate limiting with retry_after
    await asyncio.sleep(e.retry_after)
```

## Usage Examples

### Basic Usage

```python
from app.integrations import create_api_clients

# Create all API clients
clients = create_api_clients()

# Use JIRA client
tickets = await clients.jira.get_tickets_by_fix_version("v2.0.0")

# Use GitHub client
branches = await clients.github.get_branches("owner/repo")

# Use Confluence client
page = await clients.confluence.create_deployment_page(
    space_key="DEV",
    release_version="v2.0.0",
    repositories=[{"name": "api-service", "pr_url": "..."}]
)
```

### Connection Validation

```python
from app.integrations import validate_api_connections

# Validate all connections
results = await validate_api_connections()

for service, result in results.items():
    if result["valid"]:
        print(f"{service}: Connected ✓")
    else:
        print(f"{service}: Error - {result['error_message']}")
```

### Individual Service Usage

```python
from app.integrations import get_api_factory

factory = get_api_factory()

# Create individual clients
jira_client = factory.create_client("jira")
github_client = factory.create_client("github", use_mock=False)
```

## Environment Configuration

The API integration layer uses these environment variables:

```bash
# API switching
ENIGMA_USE_MOCK_APIS=true

# JIRA configuration
ENIGMA_JIRA_BASE_URL=https://company.atlassian.net
ENIGMA_JIRA_USERNAME=user@company.com
ENIGMA_JIRA_TOKEN=your-api-token

# GitHub configuration
ENIGMA_GITHUB_TOKEN=ghp_your-token
ENIGMA_GITHUB_ORGANIZATION=your-org

# Confluence configuration
ENIGMA_CONFLUENCE_BASE_URL=https://company.atlassian.net/wiki
ENIGMA_CONFLUENCE_USERNAME=user@company.com
ENIGMA_CONFLUENCE_TOKEN=your-api-token
```

## Mock vs Real APIs

### Mock APIs

- **Purpose**: Development, testing, and demos
- **Data**: Realistic mock data for all operations
- **Behavior**: Simulates API delays and responses
- **No external dependencies**: Works without real API credentials

### Real APIs

- **Purpose**: Production usage
- **Authentication**: Uses actual API tokens
- **Rate limiting**: Respects service rate limits
- **Error handling**: Handles real API errors and edge cases

## Technical Requirements Fulfilled

This implementation addresses all requirements from task 007:

- ✅ **ITR001**: JIRA API Integration - Full JIRA REST API support
- ✅ **ITR002**: GitHub API Integration - Complete GitHub API coverage
- ✅ **ITR003**: Confluence API Integration - Comprehensive Confluence API
- ✅ **ITR004**: Mock API Implementation - Realistic mock implementations
- ✅ **ITR006**: Rate Limit Handling - Exponential backoff and retry logic
- ✅ **ITR007**: Authentication Manager - Secure credential management
- ✅ **ITR008**: API Error Handling - Service-specific error categories
- ✅ **NTR003**: Mock-to-Real API Switching - Configuration-based switching

## Integration with Project Enigma

The API integration layer is designed to integrate seamlessly with:

- **LangGraph Workflows**: Provides API clients for workflow nodes
- **FastAPI Backend**: Exposes connection validation endpoints
- **Configuration Management**: Uses centralized environment settings
- **Error Reporting**: Provides structured error information for UI

## Testing

The implementation includes comprehensive testing support:

- Mock APIs provide consistent test data
- Real API clients can be tested with actual services
- Rate limiting can be tested with controlled scenarios
- Error handling covers all failure modes

## Performance Considerations

- **Connection pooling**: Reuses API client instances
- **Rate limiting**: Prevents API abuse and service blocking
- **Async operations**: All API calls are asynchronous
- **Caching**: Authentication results are cached for performance
- **Error recovery**: Implements retry logic with exponential backoff

This API integration layer provides a robust, scalable foundation for Project Enigma's integration needs while maintaining flexibility for development and production environments.
