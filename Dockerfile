# Use debian slim
FROM debian:bookworm-slim

WORKDIR /app

# Install curl (to install pixi), tini (signal handling), and ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tini \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install pixi globally
RUN curl -fsSL https://pixi.sh/install.sh | bash
ENV PATH="/root/.pixi/bin:${PATH}"

# Copy dependency management files first to cache the pixi environment
COPY pixi.toml pixi.lock ./

# Install dependencies into the default pixi environment
RUN pixi install

# Copy the rest of the application code
COPY . .

# Cloud Run sets the PORT environment variable (default is 8080)
EXPOSE 8080

# Use tini to handle signals and reap zombie processes
ENTRYPOINT ["/usr/bin/tini", "--"]

# `pixi run` executes the prod_start task (gunicorn with uvicorn workers)
CMD ["pixi", "run", "prod_start"]
