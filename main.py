import os
from fastapi import FastAPI, APIRouter
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
load_dotenv(override=True)
from routes.dataset import router as dataset_router
from routes.data_layer import router as data_layer_router


app = FastAPI(title="Soft Tissue Sarcoma Portal API", openapi_url="/api/v1/openapi.json", version=f"v{os.getenv('VERSION', '0.0.1')}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")

api_router.include_router(dataset_router)
app.include_router(api_router)
api_router.include_router(data_layer_router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

# @app.get("/")
# async def root():
#     return {"message": "Hello World"}
