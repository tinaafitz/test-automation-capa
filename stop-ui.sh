#!/bin/bash

# CAPI Test Automation UI Shutdown Script
# Stops both FastAPI backend and React frontend

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Stopping CAPI Test Automation UI${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Read PIDs from files
if [ -f /tmp/test-automation-ui-backend.pid ]; then
    BACKEND_PID=$(cat /tmp/test-automation-ui-backend.pid)
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${RED}Stopping backend (PID: $BACKEND_PID)...${NC}"
        kill $BACKEND_PID
        rm /tmp/test-automation-ui-backend.pid
    else
        echo -e "${GREEN}Backend already stopped${NC}"
        rm /tmp/test-automation-ui-backend.pid 2>/dev/null
    fi
else
    echo -e "${GREEN}No backend PID file found${NC}"
fi

if [ -f /tmp/test-automation-ui-frontend.pid ]; then
    FRONTEND_PID=$(cat /tmp/test-automation-ui-frontend.pid)
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${RED}Stopping frontend (PID: $FRONTEND_PID)...${NC}"
        kill $FRONTEND_PID
        rm /tmp/test-automation-ui-frontend.pid
    else
        echo -e "${GREEN}Frontend already stopped${NC}"
        rm /tmp/test-automation-ui-frontend.pid 2>/dev/null
    fi
else
    echo -e "${GREEN}No frontend PID file found${NC}"
fi

# Cleanup any remaining node/uvicorn processes on these ports
echo ""
echo -e "${BLUE}Checking for lingering processes...${NC}"

# Kill any process on port 8000 (backend)
BACKEND_PORT_PID=$(lsof -ti:8000 2>/dev/null)
if [ ! -z "$BACKEND_PORT_PID" ]; then
    echo -e "${RED}Found process on port 8000: $BACKEND_PORT_PID, killing...${NC}"
    kill $BACKEND_PORT_PID 2>/dev/null || true
fi

# Kill any process on port 3000 (frontend)
FRONTEND_PORT_PID=$(lsof -ti:3000 2>/dev/null)
if [ ! -z "$FRONTEND_PORT_PID" ]; then
    echo -e "${RED}Found process on port 3000: $FRONTEND_PORT_PID, killing...${NC}"
    kill $FRONTEND_PORT_PID 2>/dev/null || true
fi

echo ""
echo -e "${GREEN}UI services stopped successfully!${NC}"
echo ""
