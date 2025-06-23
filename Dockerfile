# Use Python 3.10 slim as base image (MCP requires Python >=3.10)
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NODE_VERSION=18

# Set work directory
WORKDIR /app

# Install system dependencies including Node.js
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml first to install dependencies
COPY pyproject.toml ./

# Install core dependencies (correct MCP package with CLI tools + additional dependencies)
RUN pip install --no-cache-dir black "mcp[cli]" duckdb

# Install optional dependencies for full functionality
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov

# Copy remaining project files
COPY README.md ./
COPY LICENSE ./

# Copy source code
COPY src/ ./src/

# Add the src directory to Python path so modules can be imported
ENV PYTHONPATH="/app/src"

# Install Node.js dependencies for JavaScript/JSX syntax checking
# Install both globally and locally to ensure availability
RUN npm install -g @babel/core @babel/cli @babel/preset-env @babel/preset-react && \
    npm init -y && \
    npm install --save-dev @babel/core @babel/cli @babel/preset-env @babel/preset-react

# Create a basic .babelrc for JSX processing
RUN echo '{"presets": ["@babel/preset-env", "@babel/preset-react"]}' > /app/.babelrc

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash mcp && \
    chown -R mcp:mcp /app

# Switch to non-root user
USER mcp

# Set the default command to run the MCP server directly from source
CMD ["python", "-m", "text_editor.server"]

# Health check (optional - checks if the module can be imported from source)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import text_editor.server; print('OK')" || exit 1