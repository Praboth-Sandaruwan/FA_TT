from fastapi import FastAPI

app = FastAPI(title="App1")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "app1 ok"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
