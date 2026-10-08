import uvicorn

if __name__ == "__main__":
    print("Starting Bulk Certificate Generator on http://127.0.0.1:8000 ...")
    print("Interactive Dashboard: http://127.0.0.1:8000")
    print("Swagger OpenAPI Docs:  http://127.0.0.1:8000/docs")
    print("ReDoc Docs:            http://127.0.0.1:8000/redoc")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
