# AI Agent Implementation in CAPA Automation UI

A comprehensive technical guide explaining how AI agents are integrated, implemented, and used throughout the CAPA Automation UI.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Components](#components)
- [Implementation Details](#implementation-details)
- [Data Flow](#data-flow)
- [Context Management](#context-management)
- [API Integration](#api-integration)
- [UI Components](#ui-components)
- [Advanced Features](#advanced-features)
- [Development Guide](#development-guide)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Overview

The CAPA Automation UI leverages AI agents powered by Anthropic's Claude to provide intelligent cluster management capabilities. The AI assistant is deeply integrated into the application, providing context-aware help, troubleshooting, and cluster management through natural language conversations.

### Key Capabilities

- **Natural Language Processing**: Understand user intent from conversational queries
- **Context-Aware Responses**: Access to real-time cluster data and job logs
- **Intelligent Troubleshooting**: Analyze logs and identify specific errors
- **Actionable Suggestions**: Provide clickable follow-up actions
- **Multi-Modal Display**: Floating widget and inline chat modes

## Architecture

### High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend                            │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │         AIAssistantChat Component                  │    │
│  │  - User input capture                              │    │
│  │  - Message display                                 │    │
│  │  - Context gathering                               │    │
│  │  - Suggestion handling                             │    │
│  └────────────────┬───────────────────────────────────┘    │
│                   │                                          │
└───────────────────┼──────────────────────────────────────────┘
                    │
                    │ HTTP POST /api/ai-assistant/chat
                    │ { message, context, history }
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend                             │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │         AIAssistantService                         │    │
│  │  - System prompt injection                         │    │
│  │  - Context summarization                           │    │
│  │  - Conversation history                            │    │
│  │  - Response processing                             │    │
│  └────────────────┬───────────────────────────────────┘    │
│                   │                                          │
└───────────────────┼──────────────────────────────────────────┘
                    │
                    │ Claude API Request
                    │ { model, system, messages }
                    │
                    ▼
┌─────────────────────────────────────────────────────────────┐
│              Anthropic Claude API                            │
│                                                              │
│  - Model: claude-3-5-sonnet-20241022                       │
│  - NLP Processing                                           │
│  - Intent Recognition                                       │
│  - Response Generation                                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow

```
User Query
    │
    ▼
AIAssistantChat.jsx
    │
    ├── 1. Capture user input
    ├── 2. Fetch cluster context
    │   └── GET /api/rosa/clusters
    ├── 3. Prepare message payload
    │   ├── User message
    │   ├── Cluster context
    │   └── Conversation history (last 5 messages)
    │
    ▼
POST /api/ai-assistant/chat
    │
    ▼
ai_assistant_service.py
    │
    ├── 1. Build context summary
    │   ├── Active clusters list
    │   ├── Job logs (if available)
    │   └── Resource status
    ├── 2. Inject system prompt
    │   └── Define assistant role and behavior
    ├── 3. Call Claude API
    │   └── Send: system + messages
    ├── 4. Extract suggestions
    │   └── Parse response for actions
    │
    ▼
Response to Frontend
    │
    ├── response: AI message text
    └── suggestions: [clickable actions]
    │
    ▼
Display in Chat UI
```

## Components

### 1. Frontend Component: `AIAssistantChat.jsx`

**Location**: `ui/frontend/src/components/chat/AIAssistantChat.jsx`

**Responsibilities**:
- User interface for chat interaction
- Message state management
- Context gathering from API endpoints
- Theme-aware styling (MCE vs Minikube)
- Two display modes: floating widget and inline

**Key Features**:
```jsx
// Display modes
inline = false  // Floating chat widget (bottom-right corner)
inline = true   // Full-width embedded chat component

// Theme support
theme = 'mce'      // Blue/cyan gradient
theme = 'minikube' // Purple/violet gradient
```

### 2. Backend Service: `ai_assistant_service.py`

**Location**: `ui/backend/ai_assistant_service.py`

**Responsibilities**:
- Interface with Anthropic Claude API
- System prompt management
- Context preparation and sanitization
- Conversation history management (last 5 messages)
- Suggestion extraction from responses

**Key Configuration**:
```python
# Model selection
model = "claude-3-5-sonnet-20241022"

# Token limits
max_tokens = 1024  # Response length limit

# Context window
history_length = 5  # Last 5 messages
```

### 3. API Endpoint: `/api/ai-assistant/chat`

**Location**: `ui/backend/app.py`

**Request Format**:
```json
{
  "message": "What clusters are running?",
  "context": {
    "clusters": [
      {
        "name": "prod-cluster-01",
        "namespace": "ns-prod-cluster-01",
        "status": "ready"
      }
    ],
    "job_logs": [
      {
        "job_id": "job-123",
        "status": "failed",
        "cluster_name": "test-cluster",
        "logs": "Error: IAM role not found..."
      }
    ]
  },
  "history": [
    {"role": "user", "content": "Previous question"},
    {"role": "assistant", "content": "Previous answer"}
  ]
}
```

**Response Format**:
```json
{
  "response": "You have 1 cluster:\n- prod-cluster-01 (namespace: ns-prod-cluster-01, status: ready)",
  "suggestions": [
    "Tell me more about prod-cluster-01",
    "Provision new cluster"
  ]
}
```

## Implementation Details

### Frontend Implementation

#### 1. Message State Management

```jsx
const [messages, setMessages] = useState([
  {
    role: 'assistant',
    content: "Hi! I'm your CAPA cluster assistant...",
    timestamp: new Date(),
  },
]);
```

**Message Structure**:
- `role`: 'user' | 'assistant'
- `content`: Message text
- `timestamp`: Creation time
- `suggestions`: Optional action buttons (assistant only)
- `isError`: Error indicator (optional)

#### 2. Context Gathering

The frontend automatically gathers context before sending messages:

```jsx
// Fetch current cluster state
const clustersResponse = await fetch('http://localhost:8000/api/rosa/clusters');
const clustersData = await clustersResponse.json();

// Build context object
const context = {
  clusters: clustersData.clusters || [],
  history: messages.slice(-5), // Last 5 messages
};
```

#### 3. Message Sending Flow

```jsx
const sendMessage = async () => {
  // 1. Add user message to UI immediately
  setMessages(prev => [...prev, userMessage]);

  // 2. Show loading indicator
  setIsLoading(true);

  // 3. Gather context
  const context = await gatherContext();

  // 4. Send to backend
  const response = await fetch('/api/ai-assistant/chat', {
    method: 'POST',
    body: JSON.stringify({ message, context })
  });

  // 5. Display assistant response
  setMessages(prev => [...prev, assistantMessage]);

  // 6. Hide loading indicator
  setIsLoading(false);
};
```

#### 4. Quick Actions

Pre-defined quick action buttons for common queries:

```jsx
const quickActions = [
  'What clusters are running?',
  'Troubleshoot failed cluster',
  'Explain ROSA HCP',
  'How to provision cluster?',
];
```

#### 5. Suggestion Handling

Assistant responses can include clickable suggestions:

```jsx
{message.suggestions && message.suggestions.length > 0 && (
  <div className="mt-3 space-y-2">
    {message.suggestions.map((suggestion, idx) => (
      <button
        onClick={() => setInput(suggestion)}
        className="block w-full text-left..."
      >
        {suggestion}
      </button>
    ))}
  </div>
)}
```

### Backend Implementation

#### 1. System Prompt Engineering

The system prompt defines the assistant's personality, capabilities, and behavior:

```python
self.system_prompt = """You are an AI assistant specialized in
Red Hat OpenShift Service on AWS (ROSA) and Cluster API (CAPI) operations.

CRITICAL INSTRUCTION - READ CAREFULLY:
When the user asks "What clusters are running?" you MUST:
1. Look at the "Current cluster context" section
2. Find the line "Active clusters: [number]"
3. Find lines starting with "  - " containing cluster details
4. COPY the cluster name, namespace, and status into your response
5. NEVER just say "You have 1 cluster(s)" without the name

Your role is to help users:
- List running clusters with their full details
- Analyze provisioning job logs to identify specific errors
- Troubleshoot failed clusters by examining real error messages
- Provide targeted fixes based on actual errors
- Explain CAPI and ROSA concepts

Common error patterns to look for:
- "AWS credentials" or "AccessDenied" → AWS credential issue
- "NetworkNotReady" or "VPC creation failed" → Network problem
- "RoleNotReady" or "IAM role" → IAM role issue
- "secret not found" → rosa-creds-secret missing
- "Unauthorized" or "login failed" → OpenShift Hub login issue
"""
```

#### 2. Context Building

The service builds a comprehensive context summary from the provided data:

```python
def _build_context_summary(self, context: Dict[str, Any]) -> str:
    summary_parts = ["Current cluster context:"]

    # Add cluster information
    clusters = context.get("clusters", [])
    if clusters:
        summary_parts.append(f"\nActive clusters: {len(clusters)}")
        for cluster in clusters[:5]:  # First 5 clusters
            name = cluster.get("name", "unnamed")
            namespace = cluster.get("namespace", "unknown")
            status = cluster.get("status", "unknown")
            summary_parts.append(f"  - {name} (namespace: {namespace}): {status}")

    # Add job logs for troubleshooting
    job_logs = context.get("job_logs", [])
    if job_logs:
        summary_parts.append("\n\nRecent provisioning job logs:")
        for log_entry in job_logs[:3]:  # Last 3 jobs
            job_id = log_entry.get("job_id", "unknown")
            status = log_entry.get("status", "unknown")
            cluster_name = log_entry.get("cluster_name", "unknown")
            logs = log_entry.get("logs", "")

            summary_parts.append(f"\nJob {job_id} for cluster '{cluster_name}' - Status: {status}")
            if logs:
                # Include last 20 lines for context
                log_lines = logs.split("\n")[-20:]
                summary_parts.append("Log excerpt:")
                summary_parts.append("\n".join(log_lines))

    return "\n".join(summary_parts)
```

#### 3. API Call to Claude

```python
async def chat(self, message: str, context: Dict[str, Any], history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    # Build context summary
    context_summary = self._build_context_summary(context)

    # Build conversation history
    messages = []
    if history:
        for msg in history[-5:]:  # Last 5 messages
            messages.append({"role": msg.get("role"), "content": msg.get("content")})

    # Add current user message with context
    user_prompt = f"{context_summary}\n\nUser question: {message}"
    messages.append({"role": "user", "content": user_prompt})

    # Call Claude API
    response = self.client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        system=self.system_prompt,
        messages=messages,
    )

    assistant_message = response.content[0].text

    # Extract suggestions
    suggestions = self._extract_suggestions(assistant_message, context)

    return {"response": assistant_message, "suggestions": suggestions}
```

#### 4. Suggestion Extraction

The service analyzes responses to extract actionable suggestions:

```python
def _extract_suggestions(self, message: str, context: Dict[str, Any]) -> List[str]:
    suggestions = []
    clusters = context.get("clusters", [])

    # If listing clusters, offer details
    if clusters and ("cluster" in message.lower() or "running" in message.lower()):
        suggestions.append("What is the cluster name?")
        if len(clusters) > 0:
            cluster_name = clusters[0].get("name", "cluster")
            suggestions.append(f"Tell me more about {cluster_name}")
        suggestions.append("Provision new cluster")

    # Common action patterns
    if "provision" in message.lower():
        suggestions.append("How do I provision a new cluster?")

    if "delete" in message.lower() or "remove" in message.lower():
        suggestions.append("How do I safely delete a cluster?")

    if "error" in message.lower() or "fail" in message.lower():
        suggestions.append("Show me cluster error logs")
        suggestions.append("Troubleshoot failed cluster")

    return suggestions[:3]  # Max 3 suggestions
```

## Data Flow

### Complete Request-Response Cycle

#### Step 1: User Input

```
User types: "What clusters are running?"
    │
    ▼
Frontend captures input
```

#### Step 2: Context Gathering

```jsx
// Fetch cluster data
GET /api/rosa/clusters

Response:
{
  "clusters": [
    {
      "name": "prod-cluster-01",
      "namespace": "ns-prod-cluster-01",
      "status": "ready",
      "region": "us-east-1",
      "version": "4.14.0"
    }
  ]
}
```

#### Step 3: Request to Backend

```json
POST /api/ai-assistant/chat

Request Body:
{
  "message": "What clusters are running?",
  "context": {
    "clusters": [
      {
        "name": "prod-cluster-01",
        "namespace": "ns-prod-cluster-01",
        "status": "ready"
      }
    ]
  },
  "history": []
}
```

#### Step 4: Backend Processing

```python
# 1. Build context summary
context_summary = """
Current cluster context:

Active clusters: 1
  - prod-cluster-01 (namespace: ns-prod-cluster-01): ready
"""

# 2. Create prompt with context
user_prompt = """
Current cluster context:

Active clusters: 1
  - prod-cluster-01 (namespace: ns-prod-cluster-01): ready

User question: What clusters are running?
"""

# 3. Call Claude API
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    system=system_prompt,
    messages=[{"role": "user", "content": user_prompt}]
)
```

#### Step 5: Claude Response

```
"You have 1 cluster:
- prod-cluster-01 (namespace: ns-prod-cluster-01, status: ready)

This cluster is currently in a ready state and running in namespace
ns-prod-cluster-01. Would you like to know more details about this cluster?"
```

#### Step 6: Suggestion Extraction

```python
# Analyze response and extract suggestions
suggestions = [
    "Tell me more about prod-cluster-01",
    "Provision new cluster",
    "What is the cluster name?"
]
```

#### Step 7: Response to Frontend

```json
{
  "response": "You have 1 cluster:\n- prod-cluster-01 (namespace: ns-prod-cluster-01, status: ready)\n\nThis cluster is currently in a ready state...",
  "suggestions": [
    "Tell me more about prod-cluster-01",
    "Provision new cluster"
  ]
}
```

#### Step 8: Display in UI

```jsx
// Add assistant message to chat
setMessages(prev => [...prev, {
  role: 'assistant',
  content: response.response,
  timestamp: new Date(),
  suggestions: response.suggestions
}]);
```

## Context Management

### Types of Context

#### 1. Cluster Context

Provides real-time cluster information:

```python
{
  "clusters": [
    {
      "name": "cluster-name",
      "namespace": "ns-cluster-name",
      "status": "ready | installing | failed | uninstalling",
      "region": "us-east-1",
      "version": "4.14.0"
    }
  ]
}
```

#### 2. Job Logs Context

For troubleshooting failed operations:

```python
{
  "job_logs": [
    {
      "job_id": "job-1234567890",
      "status": "failed",
      "cluster_name": "test-cluster",
      "logs": """
TASK [Create IAM roles] *******
fatal: [localhost]: FAILED! => {
  "msg": "AWS credential error: AccessDenied"
}
"""
    }
  ]
}
```

#### 3. Resource Status Context

Kubernetes resource states:

```python
{
  "resource_status": {
    "rosacontrolplane": "RCP/prod-cluster-01: Ready",
    "awsrosamachinepool": "ARMP/prod-pool: 3/3 ready",
    "secret": "rosa-creds-secret: Found"
  }
}
```

#### 4. Conversation History

Maintains context across messages:

```python
{
  "history": [
    {"role": "user", "content": "What clusters are running?"},
    {"role": "assistant", "content": "You have 1 cluster: prod-cluster-01"},
    {"role": "user", "content": "Tell me more about it"},
    {"role": "assistant", "content": "prod-cluster-01 is a ROSA HCP cluster..."},
    {"role": "user", "content": "Can I delete it?"}
  ][-5:]  # Last 5 messages only
}
```

### Context Sanitization

The backend automatically sanitizes sensitive data:

```python
def _sanitize_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
    """Remove sensitive data from context before sending to Claude API"""

    # Never include these in context
    excluded_keys = [
        'AWS_ACCESS_KEY_ID',
        'AWS_SECRET_ACCESS_KEY',
        'OCM_CLIENT_SECRET',
        'password',
        'token'
    ]

    # Sanitize logs
    if 'job_logs' in context:
        for log_entry in context['job_logs']:
            if 'logs' in log_entry:
                # Remove credential lines
                log_entry['logs'] = self._redact_credentials(log_entry['logs'])

    return context
```

## API Integration

### Claude API Configuration

#### Environment Setup

```bash
# Backend .env file
ANTHROPIC_API_KEY=sk-ant-api03-...
```

#### Client Initialization

```python
import anthropic

class AIAssistantService:
    def __init__(self):
        # Use API key from environment
        self.client = anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )
```

#### API Request Structure

```python
response = self.client.messages.create(
    # Model selection
    model="claude-3-5-sonnet-20241022",

    # Response length limit
    max_tokens=1024,

    # System prompt (defines behavior)
    system=self.system_prompt,

    # Conversation history
    messages=[
        {"role": "user", "content": "What clusters are running?"},
        {"role": "assistant", "content": "You have 1 cluster..."},
        {"role": "user", "content": "Tell me more"}
    ]
)
```

#### Response Structure

```python
# Claude API response
{
    "id": "msg_01...",
    "type": "message",
    "role": "assistant",
    "content": [
        {
            "type": "text",
            "text": "You have 1 cluster:\n- prod-cluster-01..."
        }
    ],
    "model": "claude-3-5-sonnet-20241022",
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 487,
        "output_tokens": 156
    }
}

# Extract text
assistant_message = response.content[0].text
```

### Error Handling

#### Frontend Error Handling

```jsx
try {
  const response = await fetch('/api/ai-assistant/chat', {...});
  const data = await response.json();

  setMessages(prev => [...prev, {
    role: 'assistant',
    content: data.response,
    suggestions: data.suggestions
  }]);

} catch (error) {
  // Show error message in chat
  setMessages(prev => [...prev, {
    role: 'assistant',
    content: 'Sorry, I encountered an error. Please try again.',
    isError: true
  }]);
}
```

#### Backend Error Handling

```python
try:
    response = self.client.messages.create(...)
    return {"response": response.content[0].text, "suggestions": [...]}

except anthropic.APIError as e:
    return {
        "response": f"I encountered an error: {str(e)}. Please try again.",
        "suggestions": []
    }
```

## UI Components

### 1. Floating Chat Widget

**Usage**: Default mode for non-intrusive assistance

```jsx
<AIAssistantChat inline={false} theme="mce" />
```

**Features**:
- Bottom-right floating button
- Click to expand chat window
- Persists across page navigation
- z-index: 9999 (always on top)

**Visual**:
```
┌─────────────────────────────────┐
│  Page Content                   │
│                                 │
│                                 │
│                                 │
│                          ┌────┐ │
│                          │ 💫 │ │ ← Floating button
│                          └────┘ │
└─────────────────────────────────┘
```

### 2. Inline Chat Component

**Usage**: Embedded full-width chat interface

```jsx
<AIAssistantChat inline={true} theme="mce" />
```

**Features**:
- Full-width embedded component
- 600px fixed height
- Scrollable message area
- Integrated into page layout

**Visual**:
```
┌─────────────────────────────────┐
│  Page Header                    │
├─────────────────────────────────┤
│                                 │
│  ┌───────────────────────────┐ │
│  │  Chat Messages            │ │
│  │                           │ │
│  │  User: Hello              │ │
│  │  AI: Hi! How can I help?  │ │
│  │                           │ │
│  ├───────────────────────────┤ │
│  │  Quick Actions            │ │
│  ├───────────────────────────┤ │
│  │  Input [Send]             │ │
│  └───────────────────────────┘ │
│                                 │
└─────────────────────────────────┘
```

### 3. Message Bubbles

**User Message**:
```jsx
<div className="bg-blue-600 text-white rounded-lg px-4 py-2">
  <p>{message.content}</p>
  <p className="text-xs opacity-70">{timestamp}</p>
</div>
```

**Assistant Message**:
```jsx
<div className="bg-gray-100 text-gray-900 rounded-lg px-4 py-2">
  <p>{message.content}</p>
  <p className="text-xs opacity-70">{timestamp}</p>

  {/* Suggestions */}
  {suggestions.map(suggestion => (
    <button onClick={() => setInput(suggestion)}>
      {suggestion}
    </button>
  ))}
</div>
```

**Welcome Message** (First message):
```jsx
<div className="bg-gradient-to-r from-blue-50 to-cyan-50 border-2 border-blue-200">
  <div className="flex items-center gap-2 border-b">
    <span>🤖</span>
    <span>Welcome!</span>
  </div>
  <p>{message.content}</p>
</div>
```

### 4. Loading Indicator

Animated dots while waiting for response:

```jsx
{isLoading && (
  <div className="flex gap-1">
    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
  </div>
)}
```

### 5. Quick Action Chips

Pre-defined questions as clickable chips:

```jsx
<div className="flex gap-2 overflow-x-auto">
  {quickActions.map(action => (
    <button
      onClick={() => setInput(action)}
      className="px-3 py-1 text-xs bg-gray-100 border rounded-full hover:bg-gray-200"
    >
      {action}
    </button>
  ))}
</div>
```

## Advanced Features

### 1. Multi-Turn Conversations

The assistant maintains conversation history for context-aware responses:

**Example Conversation**:
```
User: "What clusters are running?"
AI:   "You have 1 cluster: prod-cluster-01"

User: "Tell me more about it"
      ↑ AI understands "it" refers to prod-cluster-01

AI:   "prod-cluster-01 is a ROSA HCP cluster running in us-east-1..."

User: "Can I delete it?"
      ↑ AI still knows "it" = prod-cluster-01

AI:   "Yes, you can delete prod-cluster-01. Would you like me to..."
```

### 2. Intelligent Error Analysis

The assistant can analyze actual log output and identify specific errors:

**User**: "My cluster failed to provision. What's wrong?"

**AI Process**:
1. Receives job logs in context
2. Scans for error patterns
3. Identifies specific error (e.g., "IAM role not found")
4. Provides targeted fix

**Response**:
```
I analyzed the provisioning logs and found the issue:

❌ Error: AWS IAM role not found
Line 47: "fatal: [localhost]: FAILED! => IAM role 'rosa-installer-role' does not exist"

Solution:
Enable "Create ROSA Role Config" in the provisioning form to automatically
create the required IAM roles, or create them manually using:
  rosa create account-roles --mode auto

Would you like me to retry with automatic role creation?
```

### 3. Actionable Suggestions

Responses include clickable follow-up actions:

```
AI: "You have 3 clusters. 2 are ready and 1 failed."

Suggestions:
[Tell me more about the failed cluster]
[How do I fix the failed cluster?]
[Show me cluster error logs]
```

### 4. Theme Awareness

The chat UI adapts to different environments:

**MCE Environment** (Blue/Cyan):
- Primary: #2684FF
- Gradient: from-blue-600 to-cyan-600
- User bubbles: bg-blue-600

**Minikube Environment** (Purple/Violet):
- Primary: #8B5CF6
- Gradient: from-purple-600 to-violet-600
- User bubbles: bg-purple-600

## Development Guide

### Adding the AI Assistant to a Page

#### Option 1: Floating Widget

```jsx
import { AIAssistantChat } from '../components/chat/AIAssistantChat';

function MyPage() {
  return (
    <div>
      {/* Your page content */}

      {/* Floating AI assistant */}
      <AIAssistantChat inline={false} theme="mce" />
    </div>
  );
}
```

#### Option 2: Inline Chat

```jsx
import { AIAssistantChat } from '../components/chat/AIAssistantChat';

function MyPage() {
  return (
    <div>
      <h1>AI Assistant</h1>

      {/* Full-width embedded chat */}
      <AIAssistantChat inline={true} theme="mce" />
    </div>
  );
}
```

### Customizing System Prompt

Edit `ui/backend/ai_assistant_service.py`:

```python
self.system_prompt = """
Your custom system prompt here.

Define:
- Assistant's role and expertise
- Required response format
- Error patterns to look for
- Common troubleshooting steps
"""
```

### Adding New Context Types

#### 1. Frontend - Gather Context

```jsx
// In AIAssistantChat.jsx sendMessage()
const customContext = await fetch('/api/my-custom-context');
const customData = await customContext.json();

context.custom_field = customData;
```

#### 2. Backend - Process Context

```python
# In ai_assistant_service.py _build_context_summary()
custom_data = context.get("custom_field", {})
if custom_data:
    summary_parts.append("\n\nCustom Information:")
    summary_parts.append(f"Field: {custom_data.get('field')}")
```

### Extending Suggestion Logic

```python
# In ai_assistant_service.py _extract_suggestions()
def _extract_suggestions(self, message: str, context: Dict[str, Any]) -> List[str]:
    suggestions = []

    # Add custom suggestion logic
    if "my_keyword" in message.lower():
        suggestions.append("Custom suggestion based on keyword")

    # Analyze context
    if context.get("custom_field"):
        suggestions.append("Action based on context")

    return suggestions[:3]  # Max 3
```

## Testing

### Unit Testing

#### Frontend Tests

```jsx
// AIAssistantChat.test.jsx
import { render, screen, fireEvent } from '@testing-library/react';
import { AIAssistantChat } from './AIAssistantChat';

describe('AIAssistantChat', () => {
  test('renders welcome message', () => {
    render(<AIAssistantChat inline={true} theme="mce" />);
    expect(screen.getByText(/I'm your CAPA cluster assistant/)).toBeInTheDocument();
  });

  test('sends message on button click', async () => {
    render(<AIAssistantChat inline={true} theme="mce" />);

    const input = screen.getByPlaceholderText(/Ask me anything/);
    const button = screen.getByRole('button');

    fireEvent.change(input, { target: { value: 'Test message' } });
    fireEvent.click(button);

    // Verify API call was made
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/ai-assistant/chat',
      expect.objectContaining({
        method: 'POST'
      })
    );
  });
});
```

#### Backend Tests

```python
# test_ai_assistant_service.py
import pytest
from ai_assistant_service import AIAssistantService

@pytest.fixture
def ai_service():
    return AIAssistantService()

def test_context_summary_building(ai_service):
    context = {
        "clusters": [
            {"name": "test-cluster", "namespace": "ns-test", "status": "ready"}
        ]
    }

    summary = ai_service._build_context_summary(context)

    assert "Active clusters: 1" in summary
    assert "test-cluster" in summary
    assert "ns-test" in summary

def test_suggestion_extraction(ai_service):
    message = "You have 1 cluster: prod-cluster"
    context = {"clusters": [{"name": "prod-cluster"}]}

    suggestions = ai_service._extract_suggestions(message, context)

    assert len(suggestions) <= 3
    assert any("more about" in s for s in suggestions)
```

### Integration Testing

```python
# test_ai_integration.py
async def test_full_chat_flow():
    # 1. Send message
    response = await client.post("/api/ai-assistant/chat", json={
        "message": "What clusters are running?",
        "context": {
            "clusters": [
                {"name": "test", "namespace": "ns-test", "status": "ready"}
            ]
        }
    })

    # 2. Verify response
    data = response.json()
    assert "test" in data["response"]
    assert "ns-test" in data["response"]
    assert len(data["suggestions"]) > 0
```

## Troubleshooting

### Common Issues

#### 1. "API key not found" Error

**Problem**: Missing or invalid Anthropic API key

**Solution**:
```bash
# Set environment variable
export ANTHROPIC_API_KEY=sk-ant-api03-...

# Or add to .env file
echo "ANTHROPIC_API_KEY=sk-ant-api03-..." >> ui/backend/.env
```

#### 2. Chat Widget Not Appearing

**Problem**: Component not imported or z-index issues

**Solution**:
```jsx
// Ensure component is imported
import { AIAssistantChat } from '../components/chat/AIAssistantChat';

// Check z-index if hidden behind other elements
<AIAssistantChat inline={false} theme="mce" />
// Widget uses z-index: 9999 by default
```

#### 3. Context Not Updating

**Problem**: Stale cluster data in responses

**Solution**:
```jsx
// Verify context fetch is working
const clustersResponse = await fetch('http://localhost:8000/api/rosa/clusters');
console.log('Cluster context:', await clustersResponse.json());

// Check API endpoint is running
curl http://localhost:8000/api/rosa/clusters
```

#### 4. Slow Response Times

**Problem**: Large context or long conversations

**Solution**:
```python
# Reduce context size
history = messages[-5:]  # Only last 5 messages

# Limit log excerpt size
log_lines = logs.split("\n")[-20:]  # Only last 20 lines

# Use smaller model for simple queries
model = "claude-3-haiku-20240307"  # Faster, cheaper
```

#### 5. Inconsistent Answers

**Problem**: Insufficient context or unclear questions

**Solution**:
```python
# Improve system prompt
self.system_prompt = """
CRITICAL INSTRUCTION:
Always include cluster names, namespaces, and status in responses.
Never provide vague answers without specific details.
"""

# Add more context
context = {
    "clusters": [...],
    "resource_status": {...},  # Add resource info
    "job_logs": [...]          # Add relevant logs
}
```

### Debug Mode

Enable debug logging to see what's sent to Claude:

```python
# In ai_assistant_service.py
async def chat(self, ...):
    context_summary = self._build_context_summary(context)

    # DEBUG: Print context
    print(f"📝 [CONTEXT SUMMARY SENT TO CLAUDE]:\n{context_summary}\n")

    user_prompt = f"{context_summary}\n\nUser question: {message}"
    print(f"💬 [FULL PROMPT TO CLAUDE]:\n{user_prompt}\n")

    response = self.client.messages.create(...)

    # DEBUG: Print response
    print(f"🤖 [CLAUDE RESPONSE]:\n{response.content[0].text}\n")
```

### Testing Without API Key

For development without a real API key:

```python
# Mock AI service for testing
class MockAIAssistantService:
    async def chat(self, message, context, history=None):
        # Return mock responses
        if "cluster" in message.lower():
            return {
                "response": "You have 1 cluster: mock-cluster (namespace: ns-mock, status: ready)",
                "suggestions": ["Tell me more", "Provision new cluster"]
            }
        return {
            "response": f"Mock response to: {message}",
            "suggestions": []
        }
```

---

**Document Version:** 1.0
**Last Updated:** 2026-03-03
**Maintained By:** CAPA Automation Team
