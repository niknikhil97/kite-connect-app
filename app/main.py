import logging
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from kiteconnect import KiteConnect
from dotenv import load_dotenv
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Kite Connect configuration
KITE_API_KEY = os.getenv("KITE_API_KEY")
KITE_SECRET = os.getenv("KITE_SECRET")
KITE_ID = os.getenv("KITE_ID")

# In-memory storage for access token (for simplicity; use a database in production)
session_storage = {}

# Initialize KiteConnect client
kite = KiteConnect(api_key=KITE_API_KEY)

# Pydantic model for place order request
class OrderRequest(BaseModel):
    tradingsymbol: str
    quantity: int
    transaction_type: str = "BUY"  # BUY or SELL
    exchange: str = "NSE"

# Root endpoint
@app.get("/")
async def root():
    return JSONResponse(content={"status": "ok", "message": "Welcome to Kite Connect app"}, status_code=200)

# Health check endpoint
@app.get("/api/health")
async def health_check():
    return JSONResponse(content={"status": "ok"}, status_code=200)

# Redirect endpoint for Kite Connect OAuth flow
@app.get("/kite-redirect")
async def kite_redirect(request: Request):
    # Extract query parameters
    query_params = dict(request.query_params)
    request_token = query_params.get("request_token")
    
    # Log query parameters
    logger.info(f"Received redirect request with query params: {query_params}")
    
    if not request_token:
        logger.error("Missing request_token in redirect")
        raise HTTPException(status_code=400, detail="Missing request_token")
    
    try:
        # Exchange request_token for access_token
        data = kite.generate_session(request_token, api_secret=KITE_SECRET)
        access_token = data["access_token"]
        
        # Store access_token in memory
        session_storage[KITE_ID] = access_token
        kite.set_access_token(access_token)
        
        logger.info(f"Successfully generated access_token for user: {KITE_ID}")
        
        response = {
            "message": "Authentication successful",
            "user_id": KITE_ID,
            "access_token": access_token  # For debugging; remove in production
        }
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        logger.error(f"Failed to generate session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Authentication failed: {str(e)}")

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
    
    # Example response (Kite Connect expects a 200 status)
    response = {
        "message": "Postback received",
        "payload": payload
    }
    return JSONResponse(content=response, status_code=200)

# Profile endpoint to fetch user profile
@app.get("/api/profile")
async def get_profile():
    if KITE_ID not in session_storage:
        logger.error("No access_token found for user")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Set access_token for the request
        kite.set_access_token(session_storage[KITE_ID])
        
        # Fetch user profile
        profile = kite.profile()
        logger.info(f"Fetched profile for user: {KITE_ID}")
        
        return JSONResponse(content={
            "message": "Profile fetched successfully",
            "profile": profile
        }, status_code=200)
    except Exception as e:
        logger.error(f"Failed to fetch profile: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {str(e)}")

# Place order endpoint
@app.post("/api/place-order")
async def place_order(order: OrderRequest):
    if KITE_ID not in session_storage:
        logger.error("No access_token found for user")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Set access_token for the request
        kite.set_access_token(session_storage[KITE_ID])
        
        # Place a market order
        order_response = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=order.exchange,
            tradingsymbol=order.tradingsymbol,
            transaction_type=order.transaction_type,
            quantity=order.quantity,
            product=kite.PRODUCT_CNC,
            order_type=kite.ORDER_TYPE_MARKET
        )
        logger.info(f"Order placed successfully: {order_response}")
        
        return JSONResponse(content={
            "message": "Order placed successfully",
            "order_id": order_response["order_id"]
        }, status_code=200)
    except Exception as e:
        logger.error(f"Failed to place order: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to place order: {str(e)}")

# Run the app with Uvicorn
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=443)