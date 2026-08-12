from fastapi import FastAPI
from fastapi.responses import RedirectResponse

app = FastAPI(title="Soft Tissue Sarcoma Portal API", openapi_url="/api/v1/openapi.json")


@app.get("/")
async def root():
    return RedirectResponse(url="/docs")

# @app.get("/")
# async def root():
#     return {"message": "Hello World"}
