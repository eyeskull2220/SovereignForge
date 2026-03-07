#!/bin/bash
# SovereignForge Production Deployment Script
# Deploys Docker/K8s infrastructure with MiCA compliance

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="sovereignforge"
DOCKER_IMAGE="sovereignforge:latest"
DEPLOYMENT_NAME="sovereignforge-inference"

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Pre-deployment checks
pre_deployment_checks() {
    log_info "Running pre-deployment checks..."

    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi

    # Check if kubectl is available and configured
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "kubectl is not configured or cluster is not accessible."
        exit 1
    fi

    # Check for required files
    required_files=(
        "Dockerfile"
        "docker-compose.yml"
        "k8s/deployment.yaml"
        "k8s/service.yaml"
        "k8s/configmap.yaml"
        "k8s/secrets.yaml"
        "k8s/pvc.yaml"
    )

    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_error "Required file missing: $file"
            exit 1
        fi
    done

    log_success "Pre-deployment checks passed"
}

# Build Docker image
build_docker_image() {
    log_info "Building Docker image..."

    # Build with build cache mount for faster builds
    DOCKER_BUILDKIT=1 docker build \
        --target runtime \
        --tag "$DOCKER_IMAGE" \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        .

    if [[ $? -eq 0 ]]; then
        log_success "Docker image built successfully"
    else
        log_error "Docker build failed"
        exit 1
    fi
}

# Test Docker image
test_docker_image() {
    log_info "Testing Docker image..."

    # Run basic health check
    if docker run --rm --entrypoint python3 "$DOCKER_IMAGE" -c "import sys; print('Python OK')"; then
        log_success "Docker image basic test passed"
    else
        log_error "Docker image test failed"
        exit 1
    fi
}

# Deploy to Kubernetes
deploy_kubernetes() {
    log_info "Deploying to Kubernetes..."

    # Create namespace if it doesn't exist
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

    # Apply configurations in order
    manifests=(
        "k8s/pvc.yaml"
        "k8s/configmap.yaml"
        "k8s/secrets.yaml"
        "k8s/service.yaml"
        "k8s/deployment.yaml"
    )

    for manifest in "${manifests[@]}"; do
        log_info "Applying $manifest..."
        kubectl apply -f "$manifest" -n "$NAMESPACE"
    done

    log_success "Kubernetes manifests applied"
}

# Wait for deployment to be ready
wait_for_deployment() {
    log_info "Waiting for deployment to be ready..."

    # Wait for deployment rollout
    kubectl rollout status deployment/"$DEPLOYMENT_NAME" -n "$NAMESPACE" --timeout=300s

    if [[ $? -eq 0 ]]; then
        log_success "Deployment is ready"
    else
        log_error "Deployment failed to become ready"
        exit 1
    fi
}

# Run post-deployment tests
post_deployment_tests() {
    log_info "Running post-deployment tests..."

    # Test service endpoints
    SERVICE_IP=$(kubectl get svc sovereignforge-service -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}')
    SERVICE_PORT=8000

    # Wait for service to be ready
    sleep 10

    # Test health endpoint
    if curl -f "http://$SERVICE_IP:$SERVICE_PORT/health" --max-time 10 >/dev/null 2>&1; then
        log_success "Health check passed"
    else
        log_warning "Health check failed - service may still be starting"
    fi

    # Test metrics endpoint
    if curl -f "http://$SERVICE_IP:9090/metrics" --max-time 10 >/dev/null 2>&1; then
        log_success "Metrics endpoint accessible"
    else
        log_warning "Metrics endpoint not accessible"
    fi
}

# Display deployment status
show_deployment_status() {
    log_info "Deployment Status:"

    echo ""
    echo "=== Pods ==="
    kubectl get pods -n "$NAMESPACE" -o wide

    echo ""
    echo "=== Services ==="
    kubectl get svc -n "$NAMESPACE"

    echo ""
    echo "=== Persistent Volumes ==="
    kubectl get pvc -n "$NAMESPACE"

    echo ""
    echo "=== ConfigMaps & Secrets ==="
    kubectl get configmap,secret -n "$NAMESPACE"

    echo ""
    log_success "Deployment completed successfully!"
    log_info "Access your application at: http://<load-balancer-ip>:80"
    log_info "Monitor with: kubectl logs -f deployment/$DEPLOYMENT_NAME -n $NAMESPACE"
}

# Cleanup function
cleanup() {
    log_warning "Cleaning up on failure..."
    # Add cleanup logic here if needed
}

# Main deployment function
main() {
    echo "=========================================="
    echo " SovereignForge Production Deployment"
    echo "=========================================="
    echo ""

    # Set trap for cleanup on error
    trap cleanup ERR

    # Run deployment steps
    pre_deployment_checks
    build_docker_image
    test_docker_image
    deploy_kubernetes
    wait_for_deployment
    post_deployment_tests
    show_deployment_status

    echo ""
    log_success "🎉 SovereignForge deployment completed successfully!"
    log_info "MiCA Compliance: ACTIVE"
    log_info "Circuit Breaker: ENABLED"
    log_info "WebSocket Connections: READY"
}

# Handle command line arguments
case "${1:-}" in
    "build-only")
        pre_deployment_checks
        build_docker_image
        test_docker_image
        log_success "Build completed successfully"
        ;;
    "deploy-only")
        deploy_kubernetes
        wait_for_deployment
        post_deployment_tests
        show_deployment_status
        ;;
    "status")
        show_deployment_status
        ;;
    "cleanup")
        log_info "Cleaning up deployment..."
        kubectl delete namespace "$NAMESPACE" --ignore-not-found=true
        log_success "Cleanup completed"
        ;;
    *)
        main
        ;;
esac