# CAPA Automation UI

A modern web interface for managing ROSA (Red Hat OpenShift Service on AWS) clusters using Cluster API (CAPI) and Cluster API Provider AWS (CAPA).

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![React](https://img.shields.io/badge/React-18.3.1-blue)
![Python](https://img.shields.io/badge/Python-3.12-green)
![License](https://img.shields.io/badge/license-Apache%202.0-blue)

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Screenshots](#screenshots)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Overview

CAPA Automation UI provides a visual, user-friendly interface for managing the complete lifecycle of ROSA HCP (Hosted Control Plane) clusters. Built with modern web technologies, it abstracts away the complexity of Cluster API while providing powerful automation capabilities.

### Key Capabilities

- **Environment Management**: Manage MCE (Multicluster Engine) and Minikube environments
- **Cluster Lifecycle**: Provision, configure, and delete ROSA HCP clusters
- **Test Automation**: Execute automated test suites and playbooks
- **Real-time Monitoring**: Live job tracking with streaming logs
- **AI Assistant**: Natural language cluster management interface
- **Multi-environment Support**: Switch between different Kubernetes environments

## Features

### MCE Environment Dashboard

- **Environment Verification**: Validate CAPI/CAPA components and configurations
- **Component Management**: View and manage cluster-api and hypershift operators
- **Credential Management**: Secure storage and management of cloud credentials
- **Health Monitoring**: Real-time cluster health and status checks

### ROSA HCP Cluster Management

- **Interactive Provisioning**: Form-based cluster creation with YAML preview
- **Cluster Listing**: View all managed clusters with status and details
- **Lifecycle Operations**: Create, configure, and delete clusters
- **Version Management**: Select OpenShift versions and channel groups

### Playbook Automation

- **Categorized Playbooks**: Organized by validation, configuration, provisioning, and cleanup
- **One-Click Execution**: Run Ansible playbooks directly from the UI
- **Real-time Output**: Stream playbook execution logs in real-time
- **Job History**: Track all automation tasks with status and timestamps

### Test Suite Dashboard

- **Test Execution**: Run test suites with configurable parameters
- **Results Tracking**: Historical test data with pass/fail analytics
- **Jira Integration**: Link test cases to Jira tickets

### AI-Powered Assistant

- **Natural Language**: Interact with clusters using conversational commands
- **Context Awareness**: Understands your environment and previous actions
- **Automated Workflows**: Execute complex multi-step operations
- **Learning System**: Improves suggestions based on usage patterns

## Screenshots

### MCE Environment Dashboard
Main dashboard showing environment health, CAPI/CAPA components, and quick actions.

### ROSA HCP Provisioning
Interactive form for creating new ROSA clusters with YAML preview and editing.

### Playbooks Section
Categorized playbook library with real-time execution and log streaming.

### Test Suite Dashboard
Test suite runner with configurable parameters and result tracking.

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Python 3.12+
- Docker (optional, for containerized deployment)
- Access to an OpenShift cluster with MCE installed
- AWS account with appropriate permissions
- OpenShift Cluster Manager (OCM) credentials

### 5-Minute Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/test-automation-capa.git
   cd test-automation-capa/ui
   ```

2. **Configure credentials**
   ```bash
   cp ../vars/user_vars.yml.example ../vars/user_vars.yml
   # Edit user_vars.yml with your credentials
   ```

3. **Start the backend**
   ```bash
   cd backend
   pip install -r requirements.txt
   python3.12 -m uvicorn app:app --reload --port 8000
   ```

4. **Start the frontend** (in a new terminal)
   ```bash
   cd frontend
   npm install
   npm start
   ```

5. **Open the UI**
   ```
   Navigate to http://localhost:3000
   ```

## Architecture

For detailed architecture documentation, see [ARCHITECTURE.md](./ARCHITECTURE.md).

### System Components

```
┌─────────────┐      HTTP/REST      ┌─────────────┐
│   React     │◀───────────────────▶│   FastAPI   │
│  Frontend   │     WebSocket       │   Backend   │
│ (Port 3000) │                     │ (Port 8000) │
└─────────────┘                     └──────┬──────┘
                                           │
                              ┌────────────┼────────────┐
                              │            │            │
                       ┌──────▼─────┐ ┌───▼────┐ ┌────▼────┐
                       │  Ansible   │ │OpenShift│ │   AWS   │
                       │ Playbooks  │ │  (MCE)  │ │ (ROSA)  │
                       └────────────┘ └─────────┘ └─────────┘
```

### Technology Stack

**Frontend:**
- React 18 with hooks
- Tailwind CSS for styling
- React Router for navigation
- Axios for API calls
- Socket.io for real-time updates

**Backend:**
- FastAPI web framework
- Uvicorn ASGI server
- Pydantic for validation
- Ansible for automation
- SQLite for job tracking

## Installation

### Development Installation

#### Frontend Setup

```bash
cd ui/frontend

# Install dependencies
npm install

# Start development server with hot reload
npm start

# The app will open at http://localhost:3000
```

#### Backend Setup

```bash
cd ui/backend

# Create virtual environment (recommended)
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the backend server
uvicorn app:app --reload --port 8000
```

### Docker Installation

```bash
cd ui

# Build and start all services
docker-compose up --build

# Access the UI at http://localhost:3000
```

### Production Installation

```bash
# Build frontend for production
cd ui/frontend
npm run build

# The build folder will contain optimized production files
# Serve with nginx or your preferred web server
```

## Configuration

### Environment Variables

Create `ui/backend/.env` for backend configuration:

```env
# Backend Configuration
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info

# Ansible Configuration
ANSIBLE_PLAYBOOK_DIR=/path/to/playbooks
ANSIBLE_VAULT_PASSWORD_FILE=/path/to/vault/password

# Notification Services (Optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

### Credential Configuration

Edit `vars/user_vars.yml`:

```yaml
# OpenShift Hub Cluster
OCP_HUB_API_URL: "https://api.your-cluster.example.com:6443"
OCP_HUB_CLUSTER_USER: "kubeadmin"
OCP_HUB_CLUSTER_PASSWORD: "your-password"

# AWS Credentials
AWS_REGION: "us-east-1"
AWS_ACCESS_KEY_ID: "your-access-key"
AWS_SECRET_ACCESS_KEY: "your-secret-key"
AWS_ACCOUNT_ID: "123456789012"

# OpenShift Cluster Manager
OCM_CLIENT_ID: "your-ocm-client-id"
OCM_CLIENT_SECRET: "your-ocm-client-secret"

# MCE Configuration
MCE_NAMESPACE: "multicluster-engine"
```

### Frontend Configuration

Edit `ui/frontend/src/config/api.js` for API endpoints:

```javascript
export const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export const API_ENDPOINTS = {
  ANSIBLE_RUN_PLAYBOOK: '/api/ansible/run-playbook',
  ANSIBLE_RUN_TASK: '/api/ansible/run-task',
  // ... other endpoints
};
```

## Usage

### Managing Environments

#### 1. Select Environment

Navigate to **Environments** in the sidebar to:
- View available MCE environments
- Check environment health status
- Set active credentials

#### 2. Verify Environment

Go to **Verify** section to:
- Run environment verification checks
- View CAPI/CAPA component status
- Validate credentials and connectivity

#### 3. Configure Environment

Visit **Configure** section to:
- Enable CAPI/CAPA components
- Configure hypershift operators
- Set up cluster management

### Provisioning ROSA HCP Clusters

#### Step-by-Step Provisioning

1. **Navigate to Provision**
   - Click **Provision** in the sidebar

2. **Fill Cluster Configuration**
   ```
   Cluster Name: my-rosa-cluster
   Domain Prefix: my-domain
   OpenShift Version: 4.14.0
   AWS Region: us-east-1
   Channel Group: stable
   ```

3. **Configure Networking** (Optional)
   - Enable "Create ROSA Network" for automatic VPC setup
   - Or provide existing VPC details

4. **Configure IAM** (Optional)
   - Enable "Create ROSA Role Config" for automatic role creation
   - Or use existing IAM roles

5. **Review YAML**
   - Click **Generate YAML** to preview
   - Edit YAML if needed
   - Click **Provision** to start

6. **Monitor Progress**
   - Real-time logs stream in the output panel
   - Check **Task Summary** for job status

### Running Playbooks

#### Execute Test Playbooks

1. **Navigate to Playbooks**
   - Click **Playbooks** in the sidebar

2. **Browse Categories**
   - **Validation**: Environment checks and verification
   - **Configuration**: Setup and configuration tasks
   - **Provisioning**: Cluster creation workflows
   - **Cleanup**: Deletion and cleanup operations

3. **Run a Playbook**
   - Click **Run** on any playbook
   - For provisioning playbooks, fill in cluster details
   - Monitor real-time output
   - View results in Task Summary

#### Playbook Examples

**Environment Verification:**
```
Playbook: validate-capa-environment.yml
Description: Verify CAPI/CAPA components
Category: Validation
```

**ROSA HCP Provision:**
```
Playbook: create_rosa_hcp_cluster.yml
Description: Provision ROSA HCP cluster
Category: Provisioning
Requires: Cluster configuration form
```

**Cluster Cleanup:**
```
Playbook: delete_rosa_hcp_cluster.yml
Description: Delete ROSA HCP cluster
Category: Cleanup
Requires: Cluster name
```

### Managing Clusters

#### View Clusters

Navigate to **ROSA HCP Clusters** to:
- See all managed clusters
- Check cluster status and health
- View cluster details

#### Delete Clusters

1. Select cluster from list
2. Click **Delete**
3. Confirm deletion
4. Monitor deletion progress

### Using the AI Assistant

#### Interactive Commands

Navigate to **What Can I Help** page:

```
You: "Create a ROSA cluster named demo-cluster"
AI: I'll help you create a ROSA cluster. Let me guide you through the configuration...

You: "Show me all running clusters"
AI: Here are your active ROSA clusters: [list]

You: "What's the status of my MCE environment?"
AI: Your MCE environment is healthy. All CAPI/CAPA components are running...
```

### Terminal Access

#### Execute Commands

Navigate to **Terminal** to:
- Run `oc` commands on your cluster
- Execute custom scripts
- View command output
- Access command history

Example commands:
```bash
oc get pods -n multicluster-engine
oc get rosacontrolplane --all-namespaces
rosa list clusters
```

## API Documentation

### REST API Endpoints

#### Health Check
```http
GET /api/health
```
Response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime": 3600
}
```

#### List Playbooks
```http
GET /api/test-suites/list
```
Response:
```json
{
  "success": true,
  "suites": [
    {
      "id": "validate-environment",
      "config": {
        "name": "Validate CAPA Environment",
        "description": "Verify CAPI/CAPA components",
        "tags": ["validation", "RHACM4K-12345"]
      }
    }
  ]
}
```

#### Run Playbook
```http
POST /api/test-suites/run
Content-Type: application/json

{
  "suite_name": "validate-environment",
  "extra_vars": {}
}
```
Response:
```json
{
  "success": true,
  "job_id": "job-1234567890",
  "message": "Playbook started successfully"
}
```

#### Get Job Status
```http
GET /api/jobs/{job_id}
```
Response:
```json
{
  "id": "job-1234567890",
  "status": "running",
  "progress": 45,
  "started_at": "2026-03-03T10:00:00Z"
}
```

#### Stream Job Logs
```http
GET /api/jobs/{job_id}/logs
```
Response:
```json
{
  "logs": [
    "PLAY [Validate CAPA Environment]",
    "TASK [Check CAPI controller]",
    "ok: [localhost]"
  ]
}
```

### WebSocket API

#### Job Updates
```javascript
const socket = io('http://localhost:8000');

socket.on('connect', () => {
  socket.emit('subscribe', { job_id: 'job-1234567890' });
});

socket.on('job_update', (data) => {
  console.log('Status:', data.status);
  console.log('Output:', data.output);
});
```

## Development

### Project Structure

```
ui/
├── frontend/                 # React application
│   ├── public/              # Static assets
│   ├── src/
│   │   ├── pages/           # Page components
│   │   ├── components/      # Reusable components
│   │   ├── store/           # State management
│   │   ├── config/          # Configuration
│   │   └── styles/          # Styling
│   └── package.json
│
├── backend/                 # FastAPI application
│   ├── app.py              # Main application
│   ├── config.py           # Configuration
│   ├── logger.py           # Logging setup
│   └── requirements.txt    # Python dependencies
│
├── docker-compose.yml      # Docker orchestration
└── README.md              # This file
```

### Development Workflow

1. **Create Feature Branch**
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make Changes**
   - Frontend changes in `ui/frontend/src/`
   - Backend changes in `ui/backend/`

3. **Test Locally**
   ```bash
   # Frontend
   cd ui/frontend && npm start

   # Backend
   cd ui/backend && uvicorn app:app --reload
   ```

4. **Code Quality**
   ```bash
   # Frontend linting
   npm run lint
   npm run format

   # Backend linting
   black .
   pylint .
   ```

5. **Commit Changes**
   ```bash
   git add .
   git commit -m "feat: Add new feature"
   git push origin feature/my-new-feature
   ```

### Adding New Components

#### Frontend Component

1. Create component file:
   ```jsx
   // ui/frontend/src/components/MyComponent.jsx
   import React from 'react';

   const MyComponent = ({ prop1, prop2 }) => {
     return (
       <div className="p-4 bg-white rounded-lg">
         {/* Component content */}
       </div>
     );
   };

   export default MyComponent;
   ```

2. Use in page:
   ```jsx
   import MyComponent from '../components/MyComponent';

   <MyComponent prop1="value" prop2={data} />
   ```

#### Backend Endpoint

1. Add endpoint to `app.py`:
   ```python
   @app.get("/api/my-endpoint")
   async def my_endpoint():
       return {"success": True, "data": [...]}
   ```

2. Call from frontend:
   ```javascript
   const response = await axios.get('http://localhost:8000/api/my-endpoint');
   const data = response.data;
   ```

### Theming

The UI supports custom themes. Edit `ui/frontend/src/styles/themes.js`:

```javascript
export const themes = {
  mce: {
    primary: '#2684FF',
    gradient: 'from-blue-600 to-cyan-500',
    // ... other colors
  },
  custom: {
    primary: '#FF6B6B',
    gradient: 'from-red-500 to-pink-500',
    // ... other colors
  },
};
```

## Testing

### Frontend Testing

```bash
cd ui/frontend

# Run unit tests
npm test

# Run with coverage
npm test -- --coverage

# Run specific test file
npm test -- MyComponent.test.js
```

### Backend Testing

```bash
cd ui/backend

# Run pytest
pytest

# Run with coverage
pytest --cov=.

# Run specific test
pytest tests/test_api.py::test_health_check
```

### Integration Testing

```bash
# Start both frontend and backend
cd ui
docker-compose up

# Run integration tests
npm run test:integration
```

### End-to-End Testing

```bash
# Run full automation test
cd ../
ansible-playbook end2end-test.yaml
```

## Deployment

### Docker Deployment

#### Build Images

```bash
cd ui

# Build all services
docker-compose build

# Build specific service
docker-compose build frontend
docker-compose build backend
```

#### Run Containers

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Production Deployment

#### Frontend (Nginx)

1. Build production bundle:
   ```bash
   cd ui/frontend
   npm run build
   ```

2. Configure nginx:
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       root /path/to/ui/frontend/build;
       index index.html;

       location / {
           try_files $uri /index.html;
       }

       location /api {
           proxy_pass http://localhost:8000;
       }
   }
   ```

#### Backend (Systemd)

1. Create service file `/etc/systemd/system/capa-backend.service`:
   ```ini
   [Unit]
   Description=CAPA Automation Backend
   After=network.target

   [Service]
   Type=simple
   User=capa
   WorkingDirectory=/path/to/ui/backend
   Environment="PATH=/path/to/venv/bin"
   ExecStart=/path/to/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

2. Start service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable capa-backend
   sudo systemctl start capa-backend
   ```

### Kubernetes Deployment

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: capa-ui
spec:
  replicas: 2
  selector:
    matchLabels:
      app: capa-ui
  template:
    metadata:
      labels:
        app: capa-ui
    spec:
      containers:
      - name: frontend
        image: capa-ui-frontend:latest
        ports:
        - containerPort: 3000
      - name: backend
        image: capa-ui-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: capa-secrets
              key: database-url
```

## Troubleshooting

### Common Issues

#### Port Already in Use

```bash
# Find process using port 3000
lsof -ti:3000 | xargs kill -9

# Find process using port 8000
lsof -ti:8000 | xargs kill -9
```

#### Module Not Found

```bash
# Clear node_modules and reinstall
cd ui/frontend
rm -rf node_modules package-lock.json
npm install
```

#### Python Dependencies

```bash
# Reinstall Python packages
cd ui/backend
pip uninstall -r requirements.txt -y
pip install -r requirements.txt
```

#### CORS Errors

Check backend CORS configuration in `ui/backend/app.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### WebSocket Connection Failed

1. Check backend is running on port 8000
2. Verify WebSocket URL in frontend config
3. Check browser console for errors

### Debug Mode

#### Frontend Debug

```bash
# Enable React DevTools
npm start

# View detailed error messages in browser console
```

#### Backend Debug

```bash
# Run with debug logging
uvicorn app:app --reload --log-level debug

# Enable Ansible verbose output
export ANSIBLE_VERBOSITY=3
```

### Logs

#### Frontend Logs
- Browser console: F12 → Console tab
- Build logs: Terminal running `npm start`

#### Backend Logs
- API logs: `ui/backend/logs/app.log`
- Ansible logs: `/tmp/ansible-*.log`
- Job logs: Retrieved via `/api/jobs/{job_id}/logs`

## Contributing

We welcome contributions! Please follow these guidelines:

### Code Style

- **Frontend**: ESLint + Prettier configuration
- **Backend**: Black formatter + PEP 8
- **Commits**: Conventional Commits format

### Pull Request Process

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit changes (`git commit -m 'feat: add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open Pull Request

### Development Guidelines

- Write tests for new features
- Update documentation
- Follow existing code patterns
- Add comments for complex logic

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details.

## Support

### Documentation
- [Architecture Guide](./ARCHITECTURE.md)
- [AI Assistant Guide](./AI_ASSISTANT_GUIDE.md)
- [API Reference](#api-documentation)
- [Development Guide](#development)

### Getting Help
- Open an issue for bugs
- Discussion forum for questions
- Slack channel: #capa-automation

### Roadmap
- Enhanced AI assistant capabilities
- Multi-cloud provider support
- Advanced analytics dashboard
- Cluster topology visualization

---

**Version:** 1.0.0
**Last Updated:** 2026-03-03
**Maintained By:** CAPA Automation Team
