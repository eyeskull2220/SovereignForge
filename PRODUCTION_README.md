# SovereignForge Production Deployment Guide

This guide provides comprehensive instructions for deploying SovereignForge in production environments.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Kubernetes cluster (GKE, EKS, AKS, or self-hosted)
- kubectl configured
- GPU nodes (recommended for optimal performance)

### One-Command Deployment
```bash
# Clone and deploy
git clone <repository>
cd sovereignforge
chmod +x deploy.sh

# Set your registry
export DOCKER_REGISTRY=your-registry.com

# Run full deployment
./deploy.sh
```

## 📋 Deployment Options

### Option 1: Full Kubernetes Production Deployment

1. **Configure Secrets**:
   ```bash
   # Edit k8s/sovereignforge-secrets.yaml
   # Add your base64-encoded secrets
   ```

2. **Deploy**:
   ```bash
   ./deploy.sh
   ```

3. **Monitor**:
   ```bash
   kubectl logs -f deployment/sovereignforge-arbitrage -n trading
   ```

### Option 2: Docker Compose (Development/Testing)

1. **Create .env file**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Run locally**:
   ```bash
   docker-compose up -d
   ```

3. **With monitoring**:
   ```bash
   docker-compose --profile monitoring up -d
   ```

## 🔧 Configuration

### Environment Variables

#### Required
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
XAI_API_KEY=your_xai_api_key
```

#### Optional
```bash
DOCKER_REGISTRY=your-registry.com
ENABLE_GROK_REASONING=true
MIN_PROBABILITY=0.75
MAX_RISK_SCORE=0.25
```

### Kubernetes Configuration

#### Secrets Management
```bash
# Encode secrets
echo -n "your_secret" | base64

# Update k8s/sovereignforge-secrets.yaml
```

#### Resource Allocation
Edit `k8s/sovereignforge-deployment.yaml`:
```yaml
resources:
  requests:
    cpu: 500m
    memory: 1Gi
    nvidia.com/gpu: 1
  limits:
    cpu: 2000m
    memory: 4Gi
    nvidia.com/gpu: 1
```

## 🏗️ Architecture

### Components
- **Arbitrage Engine**: Core AI detection system
- **Data Integration**: Multi-exchange data aggregation
- **Telegram Alerts**: Real-time notification system
- **Grok Reasoning**: Advanced AI market analysis
- **Monitoring**: Health checks and metrics

### Storage
- **Models**: 50GB SSD for AI models
- **Logs**: 10GB for application logs
- **Data**: 20GB for market data and cache

### Networking
- **Internal Service**: ClusterIP for internal communication
- **External Service**: LoadBalancer for monitoring access
- **Health Checks**: HTTP probes on port 8080

## 📊 Monitoring & Observability

### Health Checks
```bash
# Kubernetes health
kubectl get pods -n trading

# Application health
curl http://sovereignforge-service.trading/health
```

### Logs
```bash
# Application logs
kubectl logs -f deployment/sovereignforge-arbitrage -n trading

# System events
kubectl get events -n trading --sort-by=.metadata.creationTimestamp
```

### Metrics (Future)
- Prometheus metrics on port 9090
- Grafana dashboards on port 3000
- Custom arbitrage performance metrics

## 🔒 Security

### Best Practices
- Run as non-root user
- Use Kubernetes secrets for sensitive data
- Network policies for pod isolation
- Regular security updates

### RBAC
```yaml
# ServiceAccount with minimal permissions
apiVersion: v1
kind: ServiceAccount
metadata:
  name: sovereignforge-sa
```

## 🚀 Scaling

### Horizontal Scaling
```bash
kubectl scale deployment sovereignforge-arbitrage --replicas=3 -n trading
```

### Vertical Scaling
Update resource requests/limits in deployment YAML.

### GPU Scaling
Ensure GPU nodes are available and properly configured.

## 🔄 Updates & Rollbacks

### Rolling Updates
```bash
# Update image
kubectl set image deployment/sovereignforge-arbitrage sovereignforge=new-image:tag -n trading

# Check rollout status
kubectl rollout status deployment/sovereignforge-arbitrage -n trading
```

### Rollbacks
```bash
kubectl rollout undo deployment/sovereignforge-arbitrage -n trading
```

## 🐛 Troubleshooting

### Common Issues

#### Pod CrashLoopBackOff
```bash
kubectl describe pod <pod-name> -n trading
kubectl logs <pod-name> -n trading
```

#### Image Pull Errors
```bash
# Check image exists
docker pull your-registry/sovereignforge:latest

# Check registry credentials
kubectl get secrets -n trading
```

#### GPU Issues
```bash
# Check GPU nodes
kubectl get nodes -l nvidia.com/gpu.present=true

# Check GPU resources
kubectl describe node <gpu-node>
```

### Debug Commands
```bash
# Enter pod
kubectl exec -it <pod-name> -n trading -- /bin/bash

# Check environment
kubectl exec <pod-name> -n trading -- env

# Test connectivity
kubectl exec <pod-name> -n trading -- curl -f http://localhost:8080/health
```

## 📈 Performance Tuning

### GPU Optimization
- Use CUDA-compatible PyTorch
- Enable GPU memory optimization
- Monitor GPU utilization

### Memory Management
- Configure appropriate memory limits
- Monitor for memory leaks
- Use efficient data structures

### Network Optimization
- Use efficient serialization (MessagePack, Protocol Buffers)
- Implement connection pooling
- Configure appropriate timeouts

## 🔧 Maintenance

### Backup Strategy
```bash
# Backup models and data
kubectl cp trading/<pod-name>:/app/models ./backup/models
kubectl cp trading/<pod-name>:/app/data ./backup/data
```

### Log Rotation
Configured automatically via Docker/Kubernetes.

### Updates
```bash
# Update application
git pull
./deploy.sh build
kubectl rollout restart deployment/sovereignforge-arbitrage -n trading
```

## 📞 Support

### Monitoring Commands
```bash
# System status
kubectl get all -n trading

# Resource usage
kubectl top pods -n trading

# Events
kubectl get events -n trading --sort-by=.metadata.creationTimestamp
```

### Logs Analysis
```bash
# Recent errors
kubectl logs deployment/sovereignforge-arbitrage -n trading --since=1h | grep ERROR

# Performance metrics
kubectl logs deployment/sovereignforge-arbitrage -n trading | grep "opportunities\|alerts"
```

## 🎯 Production Checklist

- [ ] Secrets configured and encoded
- [ ] GPU nodes available and configured
- [ ] Storage classes exist
- [ ] Network policies applied
- [ ] Monitoring stack deployed
- [ ] Backup strategy implemented
- [ ] Rollback procedures tested
- [ ] Alerting configured (Telegram)
- [ ] Health checks passing
- [ ] Performance benchmarks completed

## 🚀 Next Steps

1. **Configure Secrets**: Set up Telegram and xAI credentials
2. **Deploy**: Run `./deploy.sh` for full deployment
3. **Monitor**: Set up monitoring dashboards
4. **Scale**: Adjust resources based on performance
5. **Optimize**: Fine-tune configuration for your environment

---

**SovereignForge** is now production-ready with enterprise-grade deployment, monitoring, and scaling capabilities! 🎉