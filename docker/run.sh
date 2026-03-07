#!/bin/bash

# SovereignForge Docker Run Script
# Deploys the application using Docker Compose

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 SovereignForge Docker Deployment Script${NC}"
echo -e "${BLUE}=========================================${NC}"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

# Check if docker-compose is available
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    echo -e "${RED}❌ docker-compose is not available. Please install Docker Compose.${NC}"
    exit 1
fi

echo -e "${BLUE}📁 Working directory: $(pwd)${NC}"

# Check if docker-compose.yml exists
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}❌ docker-compose.yml not found in docker/ directory${NC}"
    exit 1
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found. Creating template...${NC}"
    cat > .env << EOF
# SovereignForge Environment Configuration
# Copy this file and update with your actual values

# Telegram Bot Configuration (optional)
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_IDS=123456789,987654321

# Logging
LOG_LEVEL=INFO

# Redis Configuration (if using redis service)
REDIS_URL=redis://redis:6379

# Application Configuration
PYTHONPATH=/app
EOF
    echo -e "${GREEN}✅ Created .env template. Please update with your actual values.${NC}"
fi

# Function to show usage
show_usage() {
    echo -e "${BLUE}Usage: $0 [COMMAND]${NC}"
    echo ""
    echo "Commands:"
    echo "  start     - Start all services"
    echo "  stop      - Stop all services"
    echo "  restart   - Restart all services"
    echo "  logs      - Show logs from all services"
    echo "  status    - Show status of all services"
    echo "  build     - Build the SovereignForge image"
    echo "  clean     - Remove containers and volumes"
    echo ""
    echo "If no command is specified, 'start' is used by default."
}

# Function to start services
start_services() {
    echo -e "${BLUE}🏗️  Starting SovereignForge services...${NC}"

    # Build the image if it doesn't exist
    if ! docker images | grep -q "sovereignforge/arbitrage"; then
        echo -e "${YELLOW}⚠️  SovereignForge image not found. Building...${NC}"
        $DOCKER_COMPOSE_CMD build sovereignforge
    fi

    # Start services
    $DOCKER_COMPOSE_CMD up -d

    echo -e "${GREEN}✅ Services started successfully!${NC}"
    echo -e "${BLUE}🌐 SovereignForge will be available at: http://localhost:8000${NC}"
    echo -e "${BLUE}📊 Prometheus metrics at: http://localhost:9090${NC}"
    echo -e "${BLUE}🔴 Redis at: localhost:6379${NC}"
}

# Function to stop services
stop_services() {
    echo -e "${BLUE}🛑 Stopping SovereignForge services...${NC}"
    $DOCKER_COMPOSE_CMD down
    echo -e "${GREEN}✅ Services stopped successfully!${NC}"
}

# Function to show logs
show_logs() {
    echo -e "${BLUE}📋 Showing SovereignForge logs...${NC}"
    $DOCKER_COMPOSE_CMD logs -f
}

# Function to show status
show_status() {
    echo -e "${BLUE}📊 SovereignForge Service Status${NC}"
    echo -e "${BLUE}=================================${NC}"

    # Check if services are running
    if $DOCKER_COMPOSE_CMD ps | grep -q "Up"; then
        echo -e "${GREEN}✅ Services are running${NC}"
        $DOCKER_COMPOSE_CMD ps

        # Check health status
        echo ""
        echo -e "${BLUE}🏥 Health Status:${NC}"
        if curl -f http://localhost:8000/health &>/dev/null; then
            echo -e "${GREEN}✅ SovereignForge health check passed${NC}"
        else
            echo -e "${RED}❌ SovereignForge health check failed${NC}"
        fi

        if curl -f http://localhost:9090/-/healthy &>/dev/null; then
            echo -e "${GREEN}✅ Prometheus health check passed${NC}"
        else
            echo -e "${YELLOW}⚠️  Prometheus health check failed (optional service)${NC}"
        fi
    else
        echo -e "${RED}❌ No services are running${NC}"
        echo "Use '$0 start' to start the services."
    fi
}

# Function to build image
build_image() {
    echo -e "${BLUE}🏗️  Building SovereignForge image...${NC}"
    $DOCKER_COMPOSE_CMD build sovereignforge
    echo -e "${GREEN}✅ Image built successfully!${NC}"
}

# Function to clean up
cleanup() {
    echo -e "${YELLOW}⚠️  This will remove all containers and volumes. Are you sure? (y/N): ${NC}"
    read -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}🧹 Cleaning up SovereignForge deployment...${NC}"
        $DOCKER_COMPOSE_CMD down -v --remove-orphans
        echo -e "${GREEN}✅ Cleanup completed!${NC}"
    else
        echo "Cleanup cancelled."
    fi
}

# Main script logic
COMMAND=${1:-"start"}

case $COMMAND in
    start)
        start_services
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        sleep 2
        start_services
        ;;
    logs)
        show_logs
        ;;
    status)
        show_status
        ;;
    build)
        build_image
        ;;
    clean)
        cleanup
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $COMMAND${NC}"
        show_usage
        exit 1
        ;;
esac