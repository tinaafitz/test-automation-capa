# AI Assistant & Agent Usage Guide

A practical guide to understanding and using the AI-powered features in the CAPA Automation UI, including cost estimates and best practices.

## Table of Contents

- [Overview](#overview)
- [What is the AI Assistant?](#what-is-the-ai-assistant)
- [How It Works](#how-it-works)
- [Features & Capabilities](#features--capabilities)
- [Using the AI Assistant](#using-the-ai-assistant)
- [Cost Analysis](#cost-analysis)
- [Best Practices](#best-practices)
- [Security & Privacy](#security--privacy)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

## Overview

The CAPA Automation UI includes an AI-powered assistant that helps you manage ROSA clusters using natural language. Instead of navigating through menus and forms, you can simply tell the assistant what you want to do, and it will help you accomplish your task.

### Key Benefits

- **Natural Language Interface**: Talk to your infrastructure like you would to a colleague
- **Reduced Learning Curve**: No need to memorize commands or workflows
- **Contextual Assistance**: The AI understands your environment and history
- **Automated Workflows**: Execute complex multi-step operations with simple requests
- **24/7 Availability**: Get help anytime without waiting for human support

## What is the AI Assistant?

Think of the AI assistant as your personal DevOps expert who:

1. **Understands natural language** - You can ask questions in plain English
2. **Knows your environment** - It's aware of your clusters, configurations, and history
3. **Takes action** - It can execute tasks, not just answer questions
4. **Learns from context** - It remembers your conversation and preferences
5. **Provides guidance** - It offers suggestions and best practices

### Real-World Comparison

**Traditional Approach:**
```
1. Navigate to Provision page
2. Fill out 12 form fields
3. Review configuration
4. Generate YAML
5. Review YAML
6. Submit provisioning request
7. Navigate to monitoring page
8. Check status
```

**AI Assistant Approach:**
```
You: "Create a ROSA cluster named demo-cluster in us-east-1
     with OpenShift 4.14"

AI: I'll help you create that cluster. Let me set up the
    configuration and start provisioning...
    ✅ Cluster provisioning started!
```

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     User Input                          │
│        "Create a ROSA cluster named demo"               │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              AI Assistant Service                        │
│  - Natural Language Processing (NLP)                    │
│  - Intent Recognition                                   │
│  - Context Management                                   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Backend API Layer                          │
│  - Validate request                                     │
│  - Execute automation                                   │
│  - Return results                                       │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              Infrastructure                             │
│  - OpenShift (MCE)                                      │
│  - AWS (ROSA)                                           │
│  - Ansible Playbooks                                    │
└─────────────────────────────────────────────────────────┘
```

### Processing Flow

1. **User Input** → You type a natural language request
2. **NLP Processing** → AI converts your text to structured commands
3. **Context Analysis** → AI checks your environment and history
4. **Intent Recognition** → AI determines what action to take
5. **Validation** → AI verifies the request is safe and valid
6. **Execution** → AI runs the appropriate automation
7. **Response** → AI provides feedback and results

## Features & Capabilities

### 1. Cluster Management

**What You Can Do:**
- Create new ROSA HCP clusters
- List existing clusters
- Check cluster status
- Delete clusters
- Modify cluster configurations

**Example Commands:**
```
"Create a ROSA cluster named prod-cluster"
"Show me all my clusters"
"What's the status of my demo-cluster?"
"Delete the test-cluster"
"Scale demo-cluster to 5 nodes"
```

### 2. Environment Operations

**What You Can Do:**
- Verify environment health
- Configure CAPI/CAPA components
- Check component status
- Troubleshoot issues

**Example Commands:**
```
"Verify my MCE environment"
"Is CAPI properly configured?"
"Show me the status of hypershift"
"Configure CAPA for AWS"
"Why isn't my cluster provisioning working?"
```

### 3. Playbook Execution

**What You Can Do:**
- Run test suites
- Execute validation playbooks
- Trigger cleanup operations
- Monitor playbook progress

**Example Commands:**
```
"Run the environment validation playbook"
"Execute the ROSA HCP provision test"
"Clean up old clusters"
"Show me the last playbook results"
```

### 4. Information Queries

**What You Can Do:**
- Get cluster details
- View resource information
- Check logs and history
- Understand errors

**Example Commands:**
```
"What OpenShift versions are available?"
"Show me the configuration for demo-cluster"
"What went wrong with the last provisioning?"
"When was my environment last verified?"
```

### 5. Guided Workflows

**What You Can Do:**
- Get step-by-step guidance
- Learn best practices
- Troubleshoot issues
- Understand concepts

**Example Commands:**
```
"How do I create a production-ready cluster?"
"Walk me through setting up FIPS mode"
"What's the best way to configure networking?"
"Explain ROSA HCP architecture"
```

## Using the AI Assistant

### Getting Started

1. **Navigate to the AI Assistant**
   - Click "What Can I Help" in the sidebar
   - Or use the chat icon in any page header

2. **Start a Conversation**
   ```
   👋 Hello! How can I help with your ROSA clusters today?
   ```

3. **Ask Your Question**
   - Type naturally - don't worry about exact syntax
   - Be specific about what you want to achieve
   - Include relevant details (names, versions, regions)

### Example Conversations

#### Scenario 1: Creating a Cluster

```
You: I need to create a new ROSA cluster for testing

AI: I'd be happy to help you create a test cluster!
    Let me gather some information:

    - What would you like to name the cluster?
    - Which AWS region should I use?
    - Which OpenShift version do you prefer?

You: Name it test-cluster-01, use us-east-1, and
     OpenShift 4.14

AI: Perfect! I'll create a ROSA HCP cluster with:
    - Name: test-cluster-01
    - Region: us-east-1
    - Version: 4.14.0
    - Default networking (automatic VPC creation)
    - Default IAM roles (automatic creation)

    Should I proceed with these settings?

You: Yes, go ahead

AI: ✅ Starting cluster provisioning!

    📊 Status: Creating cluster test-cluster-01
    ⏱️ Estimated time: 15-20 minutes

    You can monitor progress in the Task Summary
    section. I'll notify you when it's ready!
```

#### Scenario 2: Troubleshooting

```
You: My cluster isn't provisioning. What's wrong?

AI: Let me check what's happening with your cluster.

    🔍 Analyzing recent operations...

    I found an issue with cluster "demo-cluster":

    ❌ Error: AWS IAM role not found
    Cause: The required IAM role wasn't created

    Solution: Enable "Create ROSA Role Config" in
    the provisioning form, or create the role manually.

    Would you like me to:
    1. Retry with automatic role creation
    2. Show you how to create roles manually
    3. Delete this failed cluster

You: Retry with automatic role creation

AI: ✅ Restarting cluster provisioning with automatic
    IAM role creation enabled. This should resolve
    the issue!
```

#### Scenario 3: Information Gathering

```
You: Show me all clusters and their status

AI: Here are your ROSA HCP clusters:

    ✅ prod-cluster-01
       Region: us-east-1
       Version: 4.14.0
       Status: Ready
       Created: 2 days ago

    ⏳ demo-cluster
       Region: us-west-2
       Version: 4.13.0
       Status: Installing (75% complete)
       Created: 45 minutes ago

    ❌ test-cluster-99
       Region: us-east-1
       Version: 4.14.0
       Status: Failed (IAM role error)
       Created: 1 hour ago

    Would you like details on any specific cluster?
```

### Tips for Better Results

#### ✅ DO:
- Be specific about names, versions, and regions
- Ask follow-up questions for clarification
- Provide context about what you're trying to achieve
- Use the AI for complex multi-step tasks

**Good Examples:**
```
"Create a production ROSA cluster in us-east-1 with
 OpenShift 4.14 and FIPS mode enabled"

"I need to test the log forwarding feature. Can you
 help me set that up?"

"What's the difference between creating a cluster
 with and without ROSA Network automation?"
```

#### ❌ DON'T:
- Use overly vague requests
- Expect the AI to guess missing information
- Assume the AI can access external systems directly

**Poor Examples:**
```
"Make a cluster"  (too vague - what name? what region?)

"Fix it"  (what needs fixing?)

"Do the thing we talked about yesterday"  (no conversation history)
```

## Cost Analysis

### AI Provider: Anthropic Claude

The AI assistant uses Anthropic's Claude API, which offers:
- High-quality natural language understanding
- Context-aware responses
- Safe and helpful outputs
- Transparent pricing

### Pricing Model (as of 2026)

Anthropic Claude charges per million tokens:

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|------------------------|
| Claude 3.5 Sonnet | $3.00 | $15.00 |
| Claude 3 Haiku | $0.25 | $1.25 |

**What's a token?**
- Roughly 4 characters of text
- A typical sentence is 10-20 tokens
- A paragraph is 50-100 tokens

### Real-World Cost Examples

#### Example 1: Simple Cluster Creation

**Conversation:**
```
You: Create a ROSA cluster named demo-cluster
AI: [Processes request and creates cluster]
```

**Token Usage:**
- Input: ~500 tokens (includes system context)
- Output: ~200 tokens (confirmation and status)

**Cost:** $0.00165 (less than a penny)

#### Example 2: Troubleshooting Session

**Conversation:**
```
You: My cluster isn't working. Can you help?
AI: [Analyzes logs and provides detailed troubleshooting]
You: Try solution #1
AI: [Executes solution and reports results]
You: That worked! What was the issue?
AI: [Explains root cause and prevention]
```

**Token Usage:**
- Input: ~2,500 tokens (multi-turn conversation)
- Output: ~1,500 tokens (detailed explanations)

**Cost:** $0.0165 (about 1.6 cents)

#### Example 3: Extended Support Session (30 minutes)

**Multiple operations including:**
- Creating 2 clusters
- Troubleshooting 1 issue
- Checking status 3 times
- Getting configuration help

**Token Usage:**
- Input: ~15,000 tokens
- Output: ~8,000 tokens

**Cost:** $0.165 (about 16 cents)

### Monthly Cost Projections

Based on typical usage patterns:

#### Light Usage (Individual Developer)
- 5-10 AI conversations per day
- Average 3 exchanges per conversation
- **Daily Cost:** ~$0.50
- **Monthly Cost:** ~$15

#### Medium Usage (Small Team, 5 people)
- 50 AI conversations per day
- Mix of simple and complex tasks
- **Daily Cost:** ~$2.50
- **Monthly Cost:** ~$75

#### Heavy Usage (Large Team, 20 people)
- 200 AI conversations per day
- Extensive troubleshooting and automation
- **Daily Cost:** ~$10
- **Monthly Cost:** ~$300

### Cost Optimization Strategies

#### 1. Use Haiku for Simple Tasks
Claude 3 Haiku costs 90% less than Sonnet:
```
Simple tasks (use Haiku):
- "List my clusters"
- "What's the status of demo-cluster?"
- "Delete test-cluster"

Complex tasks (use Sonnet):
- Multi-step troubleshooting
- Configuration planning
- Learning and guidance
```

#### 2. Be Concise
```
❌ Expensive:
"So I was thinking about creating a cluster, maybe in
 us-east-1, or possibly us-west-2, I'm not sure which
 is better, what do you think? Also I need to decide
 on the version, there's 4.13 and 4.14..."

✅ Cost-effective:
"Create a cluster in us-east-1 with OpenShift 4.14.
 What's the command?"
```

#### 3. Batch Operations
```
❌ Multiple conversations:
"Create cluster-01"
"Create cluster-02"
"Create cluster-03"

✅ Single conversation:
"Create three clusters: cluster-01, cluster-02, and
 cluster-03, all in us-east-1 with version 4.14"
```

#### 4. Use UI for Repetitive Tasks
- First time: Use AI to learn the process
- Subsequent times: Use the UI directly
- AI is best for exploration and troubleshooting

### Cost vs. Value

**Time Saved:**
- Average task without AI: 10-15 minutes
- Average task with AI: 2-3 minutes
- Time saved: 7-12 minutes per task

**Cost per Task:**
- AI-assisted: $0.01-0.05
- Human time at $50/hour: $5.83-12.50

**ROI: 100-500x** (AI saves far more in time than it costs)

## Best Practices

### 1. Start with Clear Goals

**Good:**
```
"I need to set up a production ROSA cluster with:
 - FIPS mode enabled
 - Log forwarding to CloudWatch
 - 3 availability zones
 - OpenShift 4.14

Can you guide me through this?"
```

**Better:**
```
"I'm preparing for a production deployment. I need FIPS
 compliance and centralized logging. Can you help me
 configure a ROSA cluster that meets these requirements?"
```

### 2. Provide Context

**Without context:**
```
You: "Why did it fail?"
AI: "I need more information. What failed?"
```

**With context:**
```
You: "I tried to create a cluster named prod-01 in
      us-east-1, but it failed with an IAM error.
      Why did it fail?"
AI: "The IAM role wasn't found. Let me help you
     create it..."
```

### 3. Verify Critical Operations

Always confirm before the AI executes destructive actions:

```
You: "Delete all test clusters"

AI: ⚠️  I found 3 clusters with 'test' in the name:
    - test-cluster-01
    - test-cluster-02
    - demo-test-env

    Are you sure you want to delete ALL of these?

You: "No, just test-cluster-01 and test-cluster-02"

AI: ✅ Confirmed. Deleting 2 clusters...
```

### 4. Learn and Graduate

Use the AI as a learning tool:

**Phase 1: Learning**
```
You: "How do I create a cluster with custom networking?"
AI: [Provides detailed explanation and steps]
```

**Phase 2: Assisted Execution**
```
You: "Create a cluster with custom VPC"
AI: [Creates cluster with your specified VPC]
```

**Phase 3: Independent**
```
You now know how to do it yourself via the UI
Save AI usage for troubleshooting and complex scenarios
```

### 5. Use for Troubleshooting

The AI excels at diagnosing issues:

```
You: "My cluster is stuck at 45% provisioning for 30 minutes"

AI: Let me check what's happening...

    🔍 Analysis:
    - Normal provisioning takes 15-20 minutes
    - Your cluster is taking longer than expected
    - Common cause: AWS capacity issues

    📊 Current status:
    - Control plane: Ready ✅
    - Workers: 1/3 nodes ready
    - Issue: EC2 instance launch failures

    💡 Recommendation:
    This is likely a temporary AWS capacity issue in
    the specific AZ. You can:
    1. Wait (usually resolves in 10-15 minutes)
    2. Delete and recreate in different AZs

    What would you like to do?
```

## Security & Privacy

### What the AI Can Access

✅ **The AI CAN access:**
- Your cluster names and configurations
- Playbook execution history
- Component status and health
- Your conversation history in this session

❌ **The AI CANNOT access:**
- Your AWS credentials (stored securely in backend)
- Other users' data or clusters
- External systems directly
- Conversation history after session ends

### Data Handling

1. **Credentials**: Never sent to AI service
   ```
   Backend extracts credentials → Executes action →
   Returns status (without credentials) → AI sees status
   ```

2. **Conversation Data**: Temporary storage
   ```
   Session starts → Data in memory → Session ends →
   Data deleted
   ```

3. **Logs**: Sanitized before AI processing
   ```
   Raw logs → Remove secrets/credentials →
   Safe logs → AI analyzes
   ```

### Privacy Controls

**Session Isolation:**
- Each user has separate AI session
- No data sharing between users
- Conversations don't persist

**Credential Protection:**
- Credentials stored in backend only
- AI never receives sensitive data
- All secrets sanitized from logs

**Audit Trail:**
- All AI actions logged
- Full transparency of what was executed
- Compliance-ready logging

## Troubleshooting

### Common Issues

#### AI Doesn't Understand My Request

**Problem:**
```
You: "Do the thing"
AI: "I'm not sure what you're referring to. Can you be
     more specific?"
```

**Solution:**
- Be explicit about what you want
- Include relevant names and parameters
- Provide context about your goal

#### AI Suggests Wrong Action

**Problem:**
```
You: "Create a cluster"
AI: [Starts creating with default settings you don't want]
```

**Solution:**
- Review AI's plan before confirming
- Provide all requirements upfront
- Use the "stop" or "cancel" command

#### AI Response is Too Slow

**Possible Causes:**
1. Complex analysis required
2. Network latency
3. Backend processing time

**Solutions:**
- Break complex requests into smaller parts
- Check your internet connection
- Verify backend is running

#### AI Gives Inconsistent Answers

**Cause:** Limited session context

**Solution:**
- Provide context in each message
- Reference previous operations explicitly
- Start new session for unrelated tasks

## FAQ

### General Questions

**Q: Do I need special training to use the AI assistant?**

A: No! Just type naturally as if you're talking to a colleague. The AI understands regular English.

---

**Q: Can the AI make mistakes?**

A: Yes, like any AI system. Always review critical operations before confirming. The AI will ask for confirmation on destructive actions.

---

**Q: What happens if I disagree with the AI's suggestion?**

A: You can always say "no" or "try a different approach." The AI will adapt to your feedback.

---

**Q: Can multiple people use the AI at the same time?**

A: Yes! Each user has their own independent AI session with no interference.

---

### Technical Questions

**Q: Which AI model is used?**

A: We use Anthropic Claude 3.5 Sonnet for complex tasks and Claude 3 Haiku for simple queries to optimize costs.

---

**Q: Is my data sent to external servers?**

A: Yes, your conversation text is sent to Anthropic's API, but credentials and sensitive data are filtered out first.

---

**Q: Can I use the AI offline?**

A: No, the AI requires an internet connection to function.

---

**Q: How long does the AI remember our conversation?**

A: The AI remembers context within your current session. When you close the browser or start a new session, the history is cleared.

---

### Cost Questions

**Q: Who pays for the AI usage?**

A: Your organization. The AI service requires an API key with associated billing.

---

**Q: Can I set a budget limit?**

A: Yes! In the backend configuration, you can set daily/monthly spending limits. The AI will notify you when approaching limits.

---

**Q: Are there any free alternatives?**

A: You can use the traditional UI without AI at no additional cost. The AI is an optional enhancement.

---

### Security Questions

**Q: Can the AI access my AWS account?**

A: No. The AI sends requests to the backend, which then uses your stored credentials. The AI itself never sees your credentials.

---

**Q: What if someone tricks the AI into deleting my clusters?**

A: The AI always asks for confirmation before destructive actions and logs all operations. You have full control.

---

**Q: Is the conversation encrypted?**

A: Yes, all communication uses HTTPS encryption.

---

## Summary

### Key Takeaways

1. **Easy to Use**: Just type naturally - no special syntax required
2. **Cost-Effective**: Typical usage costs $15-50/month per team
3. **Time Saver**: Reduces task time by 70-80%
4. **Secure**: Credentials never exposed to AI service
5. **Optional**: Can always use traditional UI if preferred

### Getting Started Checklist

- [ ] Navigate to "What Can I Help" page
- [ ] Try a simple command: "Show me my clusters"
- [ ] Create something: "Create a test cluster"
- [ ] Ask for help: "How do I enable FIPS mode?"
- [ ] Review your usage in Task Summary
- [ ] Explore advanced features

### Next Steps

1. **Try It Out**: Start with simple queries
2. **Learn from Examples**: Copy the conversation patterns above
3. **Provide Feedback**: Let us know what works and what doesn't
4. **Explore Features**: Discover new capabilities as you go
5. **Share Knowledge**: Help teammates learn best practices

---

**Questions or Feedback?**
- Open an issue on GitHub
- Contact the CAPA team
- Check the main README.md for more resources

**Version:** 1.0
**Last Updated:** 2026-03-03
**Author:** CAPA Automation Team
