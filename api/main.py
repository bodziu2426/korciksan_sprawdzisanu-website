# FastAPI search API
# TODO: implement search endpoints

from fastapi import FastAPI

app = FastAPI(title="Korciksan Sprawdzisanu")


@app.get("/")
def root():
    return {"status": "ok"}
