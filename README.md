# STS-backend

The Soft Tissue Sarcoma (STS) Data Portal Backend is a high-performance REST API built with FastAPI, SQLAlchemy, and Pixi. It serves as the primary data and query engine for the STS Portal, managing access to curated clinical and preclinical sarcoma datasets, molecular profiles, and drug treatment response data. The backend powers dynamic dataset exploration, statistical distributions, and multi-omics visualizations across patient cohorts and cell line models. It connects directly to a MySQL data store with optimized session management and structured route endpoints. The application is fully containerized with Pixi and Debian Slim for streamlined local development and compliant cloud deployment.

## Development

### Local Setup with Pixi

To start the development server with hot-reload:

```bash
pixi run start
```

To run the production server locally via Gunicorn:

```bash
pixi run prod_start
```

---

## Docker

### Build and Run Locally

To build the Docker image locally:

```bash
docker build -t sts-backend .
```

To run the container locally on port 8080 with your local `.env`:

```bash
docker run --rm -p 8080:8080 --env-file .env sts-backend
```

---

### Deploying to Google Cloud Run

Google Cloud Run can host containerized backend services. Make sure you are authenticated and have the correct project selected.

First, log in and set your active Google Cloud project:

```bash
gcloud auth login

# List out projects
gcloud projects list

# Set the active project
gcloud config set project sts-data-portal
```

To deploy the application, we split it into a two-step process (Build then Deploy) to bypass strict UHN data residency constraints that block Cloud Build's default US staging buckets. We build the image locally and push it directly to the Toronto Artifact Registry (`northamerica-northeast2`).

```bash
# 1. Build and push the image using your local Docker to the Toronto Artifact Registry 
# (force amd64 with --platform to ensure compatibility with Cloud Run deployments. M-series Macs will default to arm64 builds)
docker build --platform linux/amd64 -t northamerica-northeast2-docker.pkg.dev/sts-data-portal/cloud-run-source-deploy/sts-backend .

docker push northamerica-northeast2-docker.pkg.dev/sts-data-portal/cloud-run-source-deploy/sts-backend

# 2. Deploy the built image to Cloud Run with GCS FUSE volume mount for Whole Slide Images (.svs)
gcloud run deploy sts-backend \
  --image northamerica-northeast2-docker.pkg.dev/sts-data-portal/cloud-run-source-deploy/sts-backend \
  --region northamerica-northeast2 \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 1 \
  --min-instances 1 \
  --max-instances 2 \
  --concurrency 10 \
  --execution-environment gen2 \
  --add-volume=name=slides-vol,type=cloud-storage,bucket=portal-raw-slides \
  --add-volume-mount=volume=slides-vol,mount-path=/mnt/slides \
  --env-vars-file=env.yaml
```

# TODO: For production security, mount DATABASE_PASS from Google Secret Manager with --set-secrets
