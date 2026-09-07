from fastapi import FastAPI

app = FastAPI(title="FrameFlux API")


@app.get("/")
def root():
    return {"message": "FrameFlux API is running"}
