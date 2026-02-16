#!/bin/bash
# ============================================================================
# Jenkins Pipeline Simulation Test
# ============================================================================
# This script simulates the exact commands that Jenkins will execute
# to validate the pipeline before running in production Jenkins.
#
# Usage: ./test-jenkins-pipeline.sh [--dry-run] [--skip-provision] [--skip-delete]
#
# Options:
#   --dry-run         Only show what would be executed
#   --skip-provision  Skip the provisioning test (suite 20)
#   --skip-delete     Skip the deletion test (suite 30)
# ============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Parse arguments
DRY_RUN=false
SKIP_PROVISION=false
SKIP_DELETE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-provision)
            SKIP_PROVISION=true
            shift
            ;;
        --skip-delete)
            SKIP_DELETE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--dry-run] [--skip-provision] [--skip-delete]"
            exit 1
            ;;
    esac
done

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
    echo -e "${BLUE}ℹ ${NC}$1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_section() {
    echo ""
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}$1${NC}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

run_command() {
    local description="$1"
    shift

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] $description"
        echo "  Command: $*"
    else
        log_info "$description"
        if "$@"; then
            log_success "Command completed successfully"
            return 0
        else
            local exit_code=$?
            log_error "Command failed with exit code: $exit_code"
            return $exit_code
        fi
    fi
}

check_file_exists() {
    local file="$1"
    if [ -f "$file" ]; then
        log_success "File exists: $file"
        return 0
    else
        log_error "File NOT found: $file"
        return 1
    fi
}

check_directory_exists() {
    local dir="$1"
    if [ -d "$dir" ]; then
        log_success "Directory exists: $dir"
        return 0
    else
        log_warning "Directory NOT found: $dir"
        return 1
    fi
}

# ============================================================================
# Validation Functions
# ============================================================================

validate_environment() {
    log_section "STEP 0: Environment Validation"

    local validation_failed=false

    log_info "Checking required files..."
    check_file_exists "Jenkinsfile" || validation_failed=true
    check_file_exists "picsAgentPod_capa.yaml" || validation_failed=true
    check_file_exists "run-test-suite.py" || validation_failed=true

    log_info "Checking test suite definitions..."
    check_file_exists "test-suites/10-configure-mce-environment.json" || validation_failed=true
    check_file_exists "test-suites/20-rosa-hcp-provision.json" || validation_failed=true
    check_file_exists "test-suites/30-rosa-hcp-delete.json" || validation_failed=true

    log_info "Checking required credentials (environment variables)..."

    # Check OCP credentials
    if [ -z "$OCP_HUB_API_URL" ]; then
        log_error "OCP_HUB_API_URL not set"
        validation_failed=true
    else
        log_success "OCP_HUB_API_URL is set"
    fi

    if [ -z "$OCP_HUB_CLUSTER_PASSWORD" ]; then
        log_error "OCP_HUB_CLUSTER_PASSWORD not set"
        validation_failed=true
    else
        log_success "OCP_HUB_CLUSTER_PASSWORD is set"
    fi

    # Check AWS credentials
    if [ -z "$AWS_ACCESS_KEY_ID" ]; then
        log_error "AWS_ACCESS_KEY_ID not set"
        validation_failed=true
    else
        log_success "AWS_ACCESS_KEY_ID is set"
    fi

    if [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        log_error "AWS_SECRET_ACCESS_KEY not set"
        validation_failed=true
    else
        log_success "AWS_SECRET_ACCESS_KEY is set"
    fi

    if [ -z "$AWS_ACCOUNT_ID" ]; then
        log_warning "AWS_ACCOUNT_ID not set (optional for some tests)"
    else
        log_success "AWS_ACCOUNT_ID is set"
    fi

    # Check OCM credentials
    if [ -z "$OCM_CLIENT_ID" ]; then
        log_warning "OCM_CLIENT_ID not set (required for provisioning)"
    else
        log_success "OCM_CLIENT_ID is set"
    fi

    if [ -z "$OCM_CLIENT_SECRET" ]; then
        log_warning "OCM_CLIENT_SECRET not set (required for provisioning)"
    else
        log_success "OCM_CLIENT_SECRET is set"
    fi

    if [ "$validation_failed" = true ]; then
        log_error "Environment validation failed!"
        echo ""
        echo "To set credentials, export them as environment variables:"
        echo "  export OCP_HUB_API_URL='https://api.example.com:6443'"
        echo "  export OCP_HUB_CLUSTER_PASSWORD='your-password'"
        echo "  export AWS_ACCESS_KEY_ID='AKIA...'"
        echo "  export AWS_SECRET_ACCESS_KEY='...'"
        echo "  export OCM_CLIENT_ID='...'"
        echo "  export OCM_CLIENT_SECRET='...'"
        echo ""
        echo "Or load from vars/user_vars.yml:"
        echo "  source <(python3 -c \"import yaml; f=open('vars/user_vars.yml'); d=yaml.safe_load(f); print('\\n'.join([f'export {k}=\\\"{v}\\\"' for k,v in d.items() if v]))\")"
        return 1
    fi

    log_success "Environment validation passed!"
}

# ============================================================================
# Test Stage Functions (matching Jenkinsfile stages)
# ============================================================================

test_stage_clone() {
    log_section "STAGE 1: Clone the CAPI/CAPA Repository (Simulated)"

    log_info "Jenkins will execute:"
    echo "  git clone -b main https://github.com/tinaafitz/test-automation-capa.git capa/"
    echo ""

    log_info "Current repository check:"
    run_command "Verify we're in the correct repository" git remote -v | grep -q "test-automation-capa"

    log_info "Simulating Jenkins working directory..."
    log_success "Jenkins will work in: capa/ subdirectory"
    log_success "Our test runs from: $(pwd)"
}

test_stage_configure() {
    log_section "STAGE 2: Configure CAPI/CAPA Environment (Suite 10)"

    local cmd=(
        ./run-test-suite.py 10-configure-mce-environment
        --format junit
        -vvv
        -e "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
        -e "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"
        -e "aws_account_id=${AWS_ACCOUNT_ID}"
    )

    log_info "Jenkins will execute:"
    echo "  ${cmd[*]}"
    echo ""

    if [ "$DRY_RUN" = false ]; then
        log_warning "This will actually configure CAPI/CAPA on the cluster!"
        read -p "Continue? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_warning "Skipped by user"
            return 0
        fi

        if "${cmd[@]}"; then
            log_success "Configuration test completed successfully"
        else
            log_error "Configuration test failed"
            return 1
        fi
    else
        log_info "[DRY RUN] Would execute configuration test"
    fi
}

test_stage_provision() {
    if [ "$SKIP_PROVISION" = true ]; then
        log_section "STAGE 3: Provision ROSA HCP Cluster (SKIPPED)"
        log_warning "Provisioning test skipped by --skip-provision flag"
        return 0
    fi

    log_section "STAGE 3: Provision ROSA HCP Cluster (Suite 20)"

    local name_prefix="${NAME_PREFIX:-test-jenkins}"

    local cmd=(
        ./run-test-suite.py 20-rosa-hcp-provision
        --format junit
        -vvv
        -e "OCP_HUB_API_URL=${OCP_HUB_API_URL}"
        -e "OCP_HUB_CLUSTER_USER=${OCP_HUB_CLUSTER_USER:-kubeadmin}"
        -e "OCP_HUB_CLUSTER_PASSWORD=${OCP_HUB_CLUSTER_PASSWORD}"
        -e "MCE_NAMESPACE=${MCE_NAMESPACE:-multicluster-engine}"
        -e "OCM_CLIENT_ID=${OCM_CLIENT_ID}"
        -e "OCM_CLIENT_SECRET=${OCM_CLIENT_SECRET}"
        -e "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
        -e "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"
        -e "aws_account_id=${AWS_ACCOUNT_ID}"
        -e "name_prefix=${name_prefix}"
    )

    log_info "Jenkins will execute:"
    echo "  ${cmd[*]}"
    echo ""

    if [ "$DRY_RUN" = false ]; then
        log_warning "This will provision a ROSA HCP cluster (takes ~20 minutes)!"
        log_warning "Cluster name will be: ${name_prefix}-rosa-hcp"
        read -p "Continue? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_warning "Skipped by user"
            return 0
        fi

        if "${cmd[@]}"; then
            log_success "Provisioning test completed successfully"
        else
            log_error "Provisioning test failed"
            return 1
        fi
    else
        log_info "[DRY RUN] Would execute provisioning test"
    fi
}

test_stage_delete() {
    if [ "$SKIP_DELETE" = true ]; then
        log_section "STAGE 4: Delete ROSA HCP Cluster (SKIPPED)"
        log_warning "Deletion test skipped by --skip-delete flag"
        return 0
    fi

    log_section "STAGE 4: Delete ROSA HCP Cluster (Suite 30)"

    local name_prefix="${NAME_PREFIX:-test-jenkins}"

    local cmd=(
        ./run-test-suite.py 30-rosa-hcp-delete
        --format junit
        -vvv
        -e "OCP_HUB_API_URL=${OCP_HUB_API_URL}"
        -e "OCP_HUB_CLUSTER_USER=${OCP_HUB_CLUSTER_USER:-kubeadmin}"
        -e "OCP_HUB_CLUSTER_PASSWORD=${OCP_HUB_CLUSTER_PASSWORD}"
        -e "MCE_NAMESPACE=${MCE_NAMESPACE:-multicluster-engine}"
        -e "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}"
        -e "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}"
        -e "OCM_CLIENT_ID=${OCM_CLIENT_ID}"
        -e "OCM_CLIENT_SECRET=${OCM_CLIENT_SECRET}"
        -e "name_prefix=${name_prefix}"
    )

    log_info "Jenkins will execute:"
    echo "  ${cmd[*]}"
    echo ""

    if [ "$DRY_RUN" = false ]; then
        log_warning "This will delete the ROSA HCP cluster (takes ~30-40 minutes)!"
        log_warning "Cluster name: ${name_prefix}-rosa-hcp"
        read -p "Continue? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_warning "Skipped by user"
            return 0
        fi

        if "${cmd[@]}"; then
            log_success "Deletion test completed successfully"
        else
            log_error "Deletion test failed"
            return 1
        fi
    else
        log_info "[DRY RUN] Would execute deletion test"
    fi
}

test_stage_archive() {
    log_section "STAGE 5: Archive Test Results"

    log_info "Jenkins will archive files from these paths:"
    echo "  capa/results/**/*.xml"
    echo "  capa/test-results/**/*.xml"
    echo ""

    log_info "Checking for test results in current directory..."

    if check_directory_exists "test-results"; then
        log_info "Finding XML test results..."
        local xml_count=$(find test-results -name "*.xml" 2>/dev/null | wc -l)
        log_success "Found $xml_count XML result file(s)"

        if [ "$xml_count" -gt 0 ]; then
            log_info "Recent test results:"
            find test-results -name "*.xml" -type f -exec ls -lh {} \; | head -5
        fi
    fi

    if check_directory_exists "results"; then
        log_info "Finding XML test results in results/..."
        local xml_count=$(find results -name "*.xml" 2>/dev/null | wc -l)
        if [ "$xml_count" -gt 0 ]; then
            log_success "Found $xml_count XML result file(s) in results/"
        fi
    fi

    log_success "Archive paths validated"
}

# ============================================================================
# Main Test Execution
# ============================================================================

main() {
    echo -e "${BOLD}${CYAN}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                                                                ║"
    echo "║         Jenkins Pipeline Simulation Test                      ║"
    echo "║         test-automation-capa                                   ║"
    echo "║                                                                ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    if [ "$DRY_RUN" = true ]; then
        log_warning "Running in DRY RUN mode - no actual tests will execute"
    fi

    # Track overall success
    local failed=false

    # Run validation
    if ! validate_environment; then
        log_error "Environment validation failed - cannot proceed"
        exit 1
    fi

    # Run test stages
    test_stage_clone || failed=true
    test_stage_configure || failed=true
    test_stage_provision || failed=true
    test_stage_delete || failed=true
    test_stage_archive || failed=true

    # Final summary
    log_section "TEST SUMMARY"

    if [ "$failed" = true ]; then
        log_error "Some tests failed!"
        echo ""
        echo "Review the errors above before running in Jenkins."
        exit 1
    else
        log_success "All tests completed successfully!"
        echo ""
        echo -e "${GREEN}${BOLD}✓ Pipeline is ready for Jenkins execution!${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Configure Jenkins credentials:"
        echo "     - CAPI_AWS_ACCESS_KEY_ID"
        echo "     - CAPI_AWS_SECRET_ACCESS_KEY"
        echo "     - CAPI_AWS_ACCOUNT_ID"
        echo "     - CAPI_OCM_CLIENT_ID"
        echo "     - CAPI_OCM_CLIENT_SECRET"
        echo ""
        echo "  2. Create Jenkins pipeline job"
        echo "  3. Configure job parameters (OCP_HUB_API_URL, password, etc.)"
        echo "  4. Run the pipeline!"
    fi
}

# Run main function
main
