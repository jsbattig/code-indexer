FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Copy application code
COPY src/ ./src/
COPY README.md ./

# Create a non-root user
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PATH="/home/app/.local/bin:${PATH}"

# Expose port (if needed for web interface in future)
EXPOSE 8000

# Default command
ENTRYPOINT ["python", "-m", "code_indexer.cli"]
CMD ["--help"]