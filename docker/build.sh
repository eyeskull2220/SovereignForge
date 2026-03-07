#!/bin/bash

# SovereignForge Docker Build Script
# Builds and pushes Docker images for production deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="sovereignforge/arbitrage"
TAG=${1:-"latest"}
DOCKERFILE="docker/Dockerfile"

echo -e "${BLUE}🚀 SovereignForge Docker Build Script${NC}"
echo -e "${BLUE}=====================================${NC}"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}⚠️  docker-compose not found. Using 'docker compose' (Docker Compose V2).${NC}"
fi

# Navigate to project root
cd "$(dirname "$0")/.."

echo -e "${BLUE}📁 Working directory: $(pwd)${NC}"

# Check if required files exist
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}❌ requirements.txt not found in project root${NC}"
    exit 1
fi

if [ ! -d "src" ]; then
    echo -e "${RED}❌ src/ directory not found${NC}"
    exit 1
fi

if [ ! -d "models" ]; then
    echo -e "${YELLOW}⚠️  models/ directory not found - creating empty directory${NC}"
    mkdir -p models
fi

echo -e "${GREEN}✅ Prerequisites check passed${NC}"

# Build the Docker image
echo -e "${BLUE}🏗️  Building Docker image: ${IMAGE_NAME}:${TAG}${NC}"
if docker build -f "${DOCKERFILE}" -t "${IMAGE_NAME}:${TAG}" .; then
    echo -e "${GREEN}✅ Docker image built successfully${NC}"
else
    echo -e "${RED}❌ Docker build failed${NC}"
    exit 1
fi

# Tag as latest if not already
if [ "$TAG" != "latest" ]; then
    echo -e "${BLUE}🏷️  Tagging as latest${NC}"
    docker tag "${IMAGE_NAME}:${TAG}" "${IMAGE_NAME}:latest"
fi

# Ask to push to registry
read -p "Do you want to push the image to Docker registry? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}📤 Pushing image to registry${NC}"

    # Push the tagged version
    if docker push "${IMAGE_NAME}:${TAG}"; then
        echo -e "${GREEN}✅ Pushed ${IMAGE_NAME}:${TAG}${NC}"
    else
        echo -e "${RED}❌ Failed to push ${IMAGE_NAME}:${TAG}${NC}"
        exit 1
    fi

    # Push latest if different
    if [ "$TAG" != "latest" ]; then
        if docker push "${IMAGE_NAME}:latest"; then
            echo -e "${GREEN}✅ Pushed ${IMAGE_NAME}:latest${NC}"
        else
            echo -e "${RED}❌ Failed to push ${IMAGE_NAME}:latest${NC}"
            exit 1
        fi
    fi
fi

echo -e "${GREEN}🎉 Build completed successfully!${NC}"
echo -e "${BLUE}Image: ${IMAGE_NAME}:${TAG}${NC}"
echo -e "${BLUE}To run: docker run -p 8000:8000 ${IMAGE_NAME}:${TAG}${NC}"