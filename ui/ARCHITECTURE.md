# CAPA Automation UI - Architecture Documentation

## System Overview

The CAPA Automation UI is a full-stack web application for managing ROSA (Red Hat OpenShift Service on AWS) clusters using Cluster API (CAPI) and Cluster API Provider AWS (CAPA). The system provides a modern, visual interface for cluster lifecycle management, testing, and monitoring.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's Browser                               │
│                      (http://localhost:3000)                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  React Frontend │
                    │   (Port 3000)   │
                    │                 │
                    │  - React 18     │
                    │  - Tailwind CSS │
                    │  - Axios        │
                    │  - React Router │
                    └────────┬────────┘
                             │
                    HTTP/REST │ WebSocket
                             │
                    ┌────────▼────────┐
                    │ FastAPI Backend │
                    │   (Port 8000)   │
                    │                 │
                    │  - Python 3.12  │
                    │  - Pydantic     │
                    │  - Uvicorn      │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
     ┌──────▼─────┐   ┌─────▼──────┐   ┌────▼─────┐
     │  Ansible   │   │ OpenShift  │   │   AWS    │
     │ Playbooks  │   │  Cluster   │   │  (ROSA)  │
     │            │   │   (MCE)    │   │          │
     └────────────┘   └────────────┘   └──────────┘
```

## Component Architecture

### Frontend Layer (React Application)

```
ui/frontend/
├── src/
│   ├── pages/                    # Main application pages
│   │   ├── CAPADashboard.jsx    # MCE environment dashboard
│   │   ├── MinikubeDashboard.jsx # Minikube environment
│   │   ├── WhatCanIHelp.js      # AI-powered assistant
│   │   ├── Dashboard.js         # Legacy main dashboard
│   │   └── ...
│   │
│   ├── components/              # Reusable UI components
│   │   ├── environments/        # Environment-specific components
│   │   │   ├── MCEEnvironment.jsx
│   │   │   └── MinikubeEnvironment.jsx
│   │   │
│   │   ├── sections/           # Page sections
│   │   │   ├── TestSuiteSection.jsx      # Playbook runner
│   │   │   ├── RosaHcpClustersSection.jsx # Cluster management
│   │   │   └── TaskSummarySection.jsx     # Activity tracking
│   │   │
│   │   ├── sidebar/           # Navigation components
│   │   │   └── CapaSidebar.jsx          # Main sidebar
│   │   │
│   │   ├── modals/            # Dialog components
│   │   │   ├── RosaProvisionModal.jsx   # Cluster provisioning
│   │   │   ├── CredentialsModal.jsx     # Credential management
│   │   │   └── YamlEditorModal.js       # YAML editor
│   │   │
│   │   └── cards/             # Display cards
│   │       ├── StatusCard.jsx
│   │       └── ComponentStatusCard.jsx
│   │
│   ├── store/                 # State management
│   │   └── AppContext.js      # React Context API
│   │
│   ├── config/               # Configuration
│   │   └── api.js            # API endpoints
│   │
│   └── styles/              # Styling
│       └── themes.js         # Theme configuration
│
└── public/                   # Static assets
```

### Backend Layer (FastAPI Application)

```
ui/backend/
├── app.py                          # Main FastAPI application
├── config.py                       # Configuration management
├── logger.py                       # Logging setup
├── health.py                       # Health check endpoints
├── monitoring.py                   # Performance monitoring
│
├── Services/
│   ├── ai_assistant_service.py     # AI chat integration
│   ├── email_notification_service.py # Email notifications
│   └── slack_notification_service.py # Slack notifications
```

## Data Flow Architecture

### 1. Environment Verification Flow

```
┌──────────┐      Verify       ┌──────────┐     Run Ansible    ┌──────────┐
│  React   │─────Click──────────▶│ FastAPI  │────Task File──────▶│ Ansible  │
│   UI     │                     │ Backend  │                    │ Engine   │
└─────┬────┘                     └────┬─────┘                    └────┬─────┘
      │                               │                               │
      │    Job Status Polling         │     Job Updates              │
      │◀──────────────────────────────┤◀──────────────────────────────┤
      │                               │                               │
      │    Verification Results       │                               │
      │◀──────────────────────────────┤                               │
      │                               │                               │
      ▼                               ▼                               ▼
  Display                         Job Queue                    Execute Tasks
  Results                         Management                    & Return Logs
```

### 2. Cluster Provisioning Flow

```
┌──────────┐    Fill Form    ┌──────────┐   Generate YAML   ┌──────────┐
│   User   │────────────────▶│ Provision│──────────────────▶│   YAML   │
│          │                 │  Modal   │                   │  Editor  │
└──────────┘                 └────┬─────┘                   └────┬─────┘
                                  │                              │
                                  │         Review & Edit        │
                                  │◀─────────────────────────────┤
                                  │                              │
                                  ▼                              │
                            ┌──────────┐                         │
                            │ Backend  │◀────Submit YAML─────────┘
                            │   API    │
                            └────┬─────┘
                                 │
                        Execute Ansible
                          Playbook
                                 │
                                 ▼
                          ┌──────────┐
                          │  Create  │
                          │ ROSA HCP │
                          │ Cluster  │
                          └──────────┘
```

### 3. Playbook Execution Flow

```
┌──────────┐   Select     ┌──────────┐    POST API     ┌──────────┐
│   User   │─Playbook────▶│TestSuite │────/run────────▶│ Backend  │
│          │              │ Section  │                 │   API    │
└──────────┘              └────┬─────┘                 └────┬─────┘
                               │                            │
                               │       Job ID               │
                               │◀───────────────────────────┤
                               │                            │
                               │                            ▼
                               │                      ┌──────────┐
                               │                      │ Execute  │
                               │                      │ Ansible  │
                               │                      │ Playbook │
                               │                      └────┬─────┘
                               │                           │
                               │   Poll Job Status         │
                               │   (Every 1 second)        │
                               │◀──────────────────────────┤
                               │                           │
                               │   Stream Logs             │
                               │◀──────────────────────────┤
                               │                           │
                               ▼                           ▼
                         Display Output              Return Results
                         Real-time
```

## State Management

### React Context Architecture

```
┌────────────────────────────────────────────────────────────┐
│                      AppProvider                           │
│                  (Global State Container)                  │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           ApiStatusContext                          │  │
│  │  - OCP cluster status                               │  │
│  │  - MCE features & components                        │  │
│  │  - Last verification timestamp                      │  │
│  │  - Loading states                                   │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐  │
│  │      RecentOperationsContext                        │  │
│  │  - Task history                                     │  │
│  │  - Operation status tracking                        │  │
│  │  - Real-time updates                                │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐  │
│  │           AppContext (Main)                         │  │
│  │  - User preferences                                 │  │
│  │  - Active environment                               │  │
│  │  - Navigation state                                 │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
└────────────────────────────────────────────────────────────┘
                           │
                           │ Provides context to
                           ▼
        ┌──────────────────────────────────────┐
        │     All Child Components             │
        │  - Pages                             │
        │  - Sections                          │
        │  - Modals                            │
        └──────────────────────────────────────┘
```

## API Architecture

### Backend API Endpoints

```
FastAPI Backend (Port 8000)
│
├── /api/health                      # Health check
│
├── /api/credentials                 # Credential management
│   ├── GET  - Fetch current credentials
│   └── POST - Save credentials
│
├── /api/ansible/run-playbook        # Execute Ansible playbooks
│   └── POST - Start playbook execution
│       ├── playbook: str
│       ├── description: str
│       ├── extra_vars: dict
│       └── yaml_override: str (optional)
│
├── /api/ansible/run-task            # Execute Ansible tasks
│   └── POST - Run single task file
│
├── /api/jobs                        # Job management
│   ├── GET     - List all jobs
│   ├── GET /:id - Get job details
│   └── GET /:id/logs - Stream job logs
│
├── /api/test-suites                 # Test suite management
│   ├── GET /list - List available playbooks
│   └── POST /run - Execute test suite
│
├── /api/rosa-hcp                    # ROSA cluster management
│   ├── GET /clusters - List clusters
│   ├── POST /provision - Create cluster
│   └── DELETE /:name - Delete cluster
│
├── /api/provisioning                # Provisioning utilities
│   └── POST /generate-yaml - Generate cluster YAML
│
├── /api/notification-settings       # Notification configuration
│   ├── GET  - Get settings
│   └── POST - Update settings
```

### WebSocket Endpoints

```
WebSocket Server (Port 8000)
│
├── /ws/jobs/:job_id                 # Real-time job updates
│   └── Streams: Job status, logs, progress
│
└── /ws/terminal                     # Interactive terminal
    └── Streams: Command execution, output
```

## Theme System

The UI supports multiple environment themes with consistent styling:

```
Theme Configuration (themes.js)
│
├── MCE Theme (Default)
│   ├── Primary: Cyan/Blue gradient (#2684FF → Cyan)
│   ├── Accent: Blue-600
│   └── Style: Professional, enterprise-focused
│
└── Minikube Theme
    ├── Primary: Purple/Violet gradient (#8B5CF6 → Purple)
    ├── Accent: Violet-600
    └── Style: Developer-friendly, local development
```

## Security Architecture

### Credential Management

```
┌──────────────────────────────────────────────────────┐
│               Credential Storage                      │
├──────────────────────────────────────────────────────┤
│                                                       │
│  Frontend (React)                                    │
│  └── Session Storage (temporary)                    │
│      └── Active credentials for UI display          │
│                                                       │
│  Backend (FastAPI)                                   │
│  └── vars/user_vars.yml                             │
│      ├── OCP_HUB_API_URL                            │
│      ├── OCP_HUB_CLUSTER_USER                       │
│      ├── OCP_HUB_CLUSTER_PASSWORD                   │
│      ├── AWS_ACCESS_KEY_ID                          │
│      ├── AWS_SECRET_ACCESS_KEY                      │
│      ├── OCM_CLIENT_ID                              │
│      └── OCM_CLIENT_SECRET                          │
│                                                       │
│  Environment Variables (Production)                  │
│  └── Docker secrets / K8s secrets                   │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### API Security

- CORS configuration for frontend-backend communication
- Pydantic validation for all API inputs
- Secret sanitization in logs
- No credentials stored in browser localStorage
- Secure credential injection for Ansible playbooks

## Performance Optimizations

### Frontend

1. **Code Splitting**
   - React.lazy() for route-based splitting
   - Dynamic imports for large components

2. **State Management**
   - Context API with selective re-rendering
   - Memoization for expensive computations
   - Debounced API calls

3. **Asset Optimization**
   - Webpack compression
   - Tree shaking for unused code
   - Image optimization

### Backend

1. **Async Operations**
   - Async/await for I/O operations
   - Background job processing
   - Non-blocking Ansible execution

2. **Caching**
   - Job status caching
   - Cluster list caching
   - Credential caching

3. **Resource Management**
   - Connection pooling
   - Proper cleanup of background tasks
   - Memory-efficient log streaming

## Deployment Architecture

### Development Mode

```
┌─────────────────────────────────────────────────────┐
│              Developer Machine                       │
├─────────────────────────────────────────────────────┤
│                                                      │
│  Terminal 1:  npm start (Port 3000)                 │
│  └── React dev server with hot reload              │
│                                                      │
│  Terminal 2:  uvicorn app:app --reload (Port 8000) │
│  └── FastAPI server with auto-reload               │
│                                                      │
│  Browser: http://localhost:3000                     │
│                                                      │
└─────────────────────────────────────────────────────┘
```

### Docker Deployment

```
┌─────────────────────────────────────────────────────┐
│            Docker Compose Stack                      │
├─────────────────────────────────────────────────────┤
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  Frontend Container                        │    │
│  │  - nginx                                   │    │
│  │  - Built React app                         │    │
│  │  - Port: 3000                              │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  Backend Container                         │    │
│  │  - Python 3.12                             │    │
│  │  - FastAPI + Uvicorn                       │    │
│  │  - Ansible                                 │    │
│  │  - Port: 8000                              │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  Shared Volumes                            │    │
│  │  - ./vars (credentials)                    │    │
│  │  - ./playbooks                             │    │
│  │  - ./templates                             │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Technology Stack Summary

### Frontend Technologies
- **React 18** - UI framework
- **React Router 6** - Client-side routing
- **Tailwind CSS 3** - Utility-first styling
- **Heroicons** - Icon library
- **Axios** - HTTP client
- **Socket.io Client** - Real-time communication
- **React Flow** - Diagram visualization
- **DND Kit** - Drag-and-drop functionality

### Backend Technologies
- **FastAPI** - Modern Python web framework
- **Uvicorn** - ASGI server
- **Pydantic** - Data validation
- **Python 3.12** - Programming language
- **Ansible** - Automation engine
- **SQLite** - Embedded database

### Infrastructure
- **Docker** - Containerization
- **Docker Compose** - Multi-container orchestration
- **nginx** - Web server (production)
- **Webpack** - Module bundler

### External Services
- **OpenShift (MCE)** - Kubernetes cluster management
- **AWS** - Cloud infrastructure
- **ROSA** - Red Hat OpenShift on AWS
- **OpenShift Cluster Manager (OCM)** - Cluster provisioning API

## Key Features by Component

### CAPA Dashboard (MCE Environment)
- Environment verification and health checks
- CAPI/CAPA component management
- ROSA HCP cluster provisioning
- Cluster lifecycle management
- Playbook execution
- Test automation
- Real-time job monitoring

### Minikube Dashboard
- Local Kubernetes cluster management
- Minikube setup and configuration
- Component installation
- Testing and validation

### AI Assistant
- Natural language cluster management
- Interactive chat interface
- Context-aware suggestions
- Automated task execution

### Playbooks Section
- Categorized playbook library
- One-click execution
- Real-time log streaming
- Provisioning option modals
- Job history tracking

### Test Suite Dashboard
- Test result visualization
- Historical test data
- Pass/fail analytics

## Integration Points

```
┌─────────────────────────────────────────────────────┐
│                  External Systems                    │
├─────────────────────────────────────────────────────┤
│                                                      │
│  OpenShift Hub Cluster                              │
│  └── MCE Operators                                  │
│      ├── cluster-api                                │
│      ├── cluster-api-provider-aws                   │
│      └── hypershift-operator                        │
│                                                      │
│  AWS Cloud                                          │
│  └── ROSA Service                                   │
│      ├── EC2 instances                              │
│      ├── VPC networking                             │
│      ├── IAM roles                                  │
│      └── S3 storage                                 │
│                                                      │
│  OpenShift Cluster Manager (OCM)                    │
│  └── APIs                                           │
│      ├── Cluster provisioning                       │
│      ├── Version management                         │
│      └── Quota management                           │
│                                                      │
│  Notification Services (Optional)                   │
│  ├── Slack webhooks                                 │
│  └── Email (SMTP)                                   │
│                                                      │
└─────────────────────────────────────────────────────┘
```

## Future Architecture Considerations

### Scalability
- Microservices architecture for backend
- Kubernetes deployment
- Redis for job queue management
- PostgreSQL for production database

### Monitoring
- Prometheus metrics collection
- Grafana dashboards
- Distributed tracing with Jaeger
- Centralized logging with ELK stack

### High Availability
- Load balancing with multiple backend instances
- Session persistence
- Database replication
- Health check endpoints

---

**Document Version:** 1.0
**Last Updated:** 2026-03-03
**Maintained By:** CAPA Automation Team
