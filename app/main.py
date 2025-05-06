import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Health check endpoint
@app.get("/")
async def health_check():
    return JSONResponse(content={"status": "ok", "message": "Welcome to kite connect app"}, status_code=200)

# Health check endpoint
@app.get("/api/health")
async def health_check():
    return JSONResponse(content={"status": "ok"}, status_code=200)

# Redirect endpoint for Kite Connect OAuth flow
@app.get("/kite-redirect")
async def kite_redirect(request: Request):
    # Extract query parameters (e.g., request_token)
    query_params = dict(request.query_params)
    
    # Log query parameters
    logger.info(f"Received redirect request with query params: {query_params}")
    
    # Example response (modify as needed, e.g., to redirect or process token)
    response = {
        "message": "Redirect received",
        "query_params": query_params
    }
    return JSONResponse(content=response, status_code=200)

# Postback endpoint for Kite Connect order updates
@app.post("/kite-postback")
async def kite_postback(request: Request):
    # Extract JSON payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse postback payload: {str(e)}")
        return JSONResponse(
            content={"message": "Invalid payload"},
            status_code=400
        )
    
    # Log payload
    logger.info(f"Received postback with payload: {payload}")
    
    # Example response (Kite Connect expects a 200 status for successful receipt)
    response = {
        "message": "Postback received",
        "payload": payload
    }
    return JSONResponse(content=response, status_code=200)

# Run the app with Uvicorn
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=443)