import os
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
load_dotenv(override=True)
from routes.dataset import router as dataset_router


app = FastAPI(title="Soft Tissue Sarcoma Portal API", openapi_url="/api/v1/openapi.json", version=f"v{os.getenv('VERSION')}")

app.include_router(dataset_router)

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

# @app.get("/")
# async def root():
#     return {"message": "Hello World"}
