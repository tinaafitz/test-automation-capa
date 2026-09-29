# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Review Standards

This project is reviewed as part of a multi-codebase architecture expertise space. See the parent workspace CLAUDE.md (`/Users/tinafitzgerald/acm_dev/ai_dev/CLAUDE.md`) for:
- **95% confidence threshold** for findings
- **Architectural patterns focus** (test patterns, async handling, integration testing)
- **Deep security analysis** via threat modeling
- **Executive + detailed output** for mixed audiences

This document covers project-specific test automation guidance.

## Quick Reference

**Tech Stack**: Python 3.11+, pytest, boto3, Kubernetes client

**Key Commands**:
```bash
pip install -r requirements.txt    # Install dependencies
pytest                             # Run all tests
pytest -v                          # Verbose output
pytest tests/test_example.py       # Run specific test file
pytest -k "rosa"                   # Run tests matching pattern
```

## Project Purpose

Automated testing framework for **Cluster API Provider AWS (CAPA)** with focus on **ROSA HCP** (Red Hat OpenShift Service on AWS - Hosted Control Plane) cluster lifecycle management.

This framework tests:
- CAPA cluster provisioning on AWS
- ROSA HCP cluster creation and configuration
- Control plane and data plane operations
- Cluster upgrades and day-2 operations
- Integration with AWS IAM, networking, and security

## Architecture Overview

**Test Organization**:
- `tests/` — Test cases organized by feature/component
- `conftest.py` — pytest fixtures (cluster provisioning, AWS credentials, cleanup)
- Fixtures manage AWS resources: VPCs, security groups, EC2 instances, EKS clusters

**Key Testing Patterns**:
- **Fixture-Based Lifecycle**: `conftest.py` fixtures create/destroy infrastructure
- **Integration Tests**: Tests against real AWS services (not mocked)
- **Async Operations**: Cluster provisioning is long-running; tests poll for readiness
- **Cleanup & Rollback**: Fixtures teardown all resources even on test failure

## Review Focus

When analyzing this codebase:

1. **Test Fixtures & Cleanup**: Ensuring proper resource teardown to avoid AWS cost leaks
2. **Error Handling**: Transient AWS API failures, timeouts, proper retry logic
3. **Async Test Patterns**: Polling loops, timeouts, condition checks for long operations
4. **Cost Management**: Test parallelization, resource reuse, cleanup on failure
5. **AWS Integration**: Credential handling, region management, multi-account scenarios
6. **Cluster Lifecycle Coverage**: Provision → validate → upgrade → delete workflows

## Known Patterns

- **AWS Cleanup**: Fixtures must clean up all created resources (VPCs, security groups, instances, clusters)
- **Polling Loops**: Tests poll for cluster readiness with exponential backoff
- **Tagging Strategy**: All resources tagged with test ID for tracking and cleanup
- **Parallel Execution**: Tests run in parallel; fixtures isolate resources by test ID
- **Long-Running Operations**: Cluster provisioning can take 30+ minutes; tests must handle timeouts gracefully

## Important Notes

- **Cost Implications**: Tests provision real AWS resources; parallelization reduces cost/time tradeoff
- **Credential Management**: Relies on AWS credentials (env vars or IAM role)
- **Region Isolation**: Tests create VPCs in specific regions to avoid quota issues
- **Flakiness**: AWS API transient errors are common; robust retry logic required
- **E2E Scope**: These are integration tests; unit tests for business logic should be in main codebase

## Integration with CAPA

These tests validate CAPA functionality in production-like scenarios:
- Tests run against actual Cluster API and Provider AWS deployments
- Tests verify ROSA HCP cluster creation through CAPA
- Tests validate multi-AZ deployments and failover scenarios
