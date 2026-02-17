# ClaudeVN Deployment Documentation

This directory contains documentation for deploying ClaudeVN in various environments.

## Available Guides

### Docker Deployment

- **[Docker Quick Start](../../DOCKER_README.md)** - Get started with Docker in 5 minutes
- **[Docker Deployment Guide](DOCKER_GUIDE.md)** - Comprehensive Docker documentation
- **[Docker Implementation Summary](DOCKER_SUMMARY.md)** - Technical details of Docker setup

## Deployment Options

### 1. Docker (Recommended)

**Best for:**
- Quick setup and testing
- Development environments
- Consistent deployment across platforms
- Easy scaling

**Requirements:**
- Docker Engine 20.10+
- Docker Compose 2.0+

**Quick Start:**
```bash
docker-compose up --build
```

**Learn More:** [Docker Quick Start](../../DOCKER_README.md)

---

### 2. Local Development

**Best for:**
- Active development
- Debugging
- Component-specific work
- Learning the codebase

**Requirements:**
- Python 3.11+
- Node.js 18+ (for frontends)
- Virtual environment

**Quick Start:**
```bash
./setup_environment.sh
./start_all.sh
```

**Learn More:** [Main README](../../README.md)

---

### 3. Cloud Deployment

**Best for:**
- Production environments
- High availability
- Scalability
- Global distribution

**Options:**
- Docker on cloud VMs (EC2, Compute Engine, etc.)
- Container services (ECS, GKE, AKS)
- Kubernetes clusters
- Serverless containers (Cloud Run, Fargate)

**Status:** Coming soon

---

### 4. Kubernetes

**Best for:**
- Enterprise production
- Auto-scaling
- High availability
- Multi-region deployment

**Requirements:**
- Kubernetes cluster 1.24+
- kubectl configured
- Container registry

**Status:** Coming soon

---

## Comparison Matrix

| Feature | Docker Compose | Local Dev | Cloud | Kubernetes |
|---------|---------------|-----------|-------|------------|
| Setup Time | 5 minutes | 15 minutes | 30+ minutes | 1+ hour |
| Isolation | Excellent | None | Excellent | Excellent |
| Portability | High | Low | Medium | High |
| Scalability | Limited | None | Good | Excellent |
| Production Ready | No | No | Yes | Yes |
| Cost | Free | Free | $$ | $$$ |
| Debugging | Good | Excellent | Medium | Medium |
| Hot Reload | Limited | Yes | No | No |

## Deployment Scenarios

### Development

**Recommended:** Local Development
- Fast iteration
- Easy debugging
- Direct file access

**Alternative:** Docker Compose
- Consistent environment
- Test deployment setup
- Service isolation

### Testing

**Recommended:** Docker Compose
- Reproducible environment
- Easy setup/teardown
- Integration testing

### Staging

**Recommended:** Cloud Deployment
- Production-like environment
- Real-world testing
- Performance validation

### Production

**Recommended:** Kubernetes or Cloud Containers
- High availability
- Auto-scaling
- Monitoring and alerting
- Zero-downtime deployments

## Configuration

### Environment Variables

Each deployment option uses environment variables for configuration:

**Docker:**
- Copy `docker.env.example` to `.env`
- Set API keys and configuration
- Run `docker-compose up`

**Local:**
- Create `.env` files in each component directory
- Or use project root `.env` for shared config
- Run `./start_all.sh`

**Cloud/Kubernetes:**
- Use cloud secret managers
- ConfigMaps and Secrets (Kubernetes)
- Environment injection at runtime

See [Configuration Guide](../guides/CONFIGURATION_GUIDE.md) for details.

## Monitoring

### Docker

```bash
# Service status
docker-compose ps

# Logs
docker-compose logs -f

# Resource usage
docker stats

# Health checks
curl http://localhost:8001/api/v1/health
```

### Local

```bash
# Status
./status.sh

# Logs
tail -f logs/*.log

# Process info
ps aux | grep python
```

### Production

- Use cloud monitoring services
- Set up log aggregation
- Configure alerting
- Health check endpoints
- Performance metrics

## Security

### Development

- Use example API keys for testing
- CORS set to `*` is acceptable
- No SSL required locally

### Production

- Use secret management (Vault, AWS Secrets Manager, etc.)
- Set specific CORS origins
- Enable SSL/TLS with certificates
- Network policies and firewalls
- Regular security updates
- Container image scanning
- Authentication and authorization

## Troubleshooting

### Docker Issues

See [Docker Guide - Troubleshooting](DOCKER_GUIDE.md#troubleshooting)

### Local Development Issues

See [Configuration Guide](../guides/CONFIGURATION_GUIDE.md)

### Production Issues

- Check cloud provider status
- Review logs from monitoring service
- Verify network connectivity
- Check resource limits
- Review security groups/firewall rules

## Next Steps

1. **Get Started**: Choose a deployment option above
2. **Configure**: Set environment variables
3. **Deploy**: Follow the specific guide
4. **Monitor**: Set up health checks
5. **Scale**: Adjust based on usage

## Additional Resources

- [Main README](../../README.md)
- [Configuration Guide](../guides/CONFIGURATION_GUIDE.md)
- [Testing Guide](../guides/TESTING_GUIDE.md)
- [Architecture Overview](../design/architecture/platform-overview.md)

---

**Need Help?**
- Docker: [DOCKER_GUIDE.md](DOCKER_GUIDE.md)
- Configuration: [CONFIGURATION_GUIDE.md](../guides/CONFIGURATION_GUIDE.md)
- General: [Main README](../../README.md)

