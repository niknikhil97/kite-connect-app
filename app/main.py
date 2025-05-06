import logging
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from kiteconnect import KiteConnect
from dotenv import load_dotenv
import uvicorn
from datetime import datetime, timedelta
import numpy as np

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

# Pydantic model for AI order configuration
class AIOrderConfig(BaseModel):
    max_investment: float = 10000.0  # Max amount to invest per run
    max_stocks: int = 5  # Max number of stocks to buy
    penny_stock_threshold: float = 50.0  # Price below which a stock is considered a penny stock
    min_growth_percent: float = 5.0  # Minimum price growth percentage over the lookback period

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

# Check available funds
async def check_available_funds():
    try:
        kite.set_access_token(session_storage[KITE_ID])
        margins = kite.margins(segment="equity")
        available_funds = margins.get("net", 0)
        logger.info(f"Available funds: ₹{available_funds}")
        return available_funds
    except Exception as e:
        logger.error(f"Failed to check funds: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to check funds: {str(e)}")

# Fetch penny stocks with growth potential
async def find_penny_stocks(config: AIOrderConfig):
    try:
        kite.set_access_token(session_storage[KITE_ID])
        # Fetch all instruments for NSE
        instruments = kite.instruments(exchange="NSE")
        
        penny_stocks = []
        lookback_days = 30
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)
        
        for instrument in instruments[:100]:  # Limit to 100 for simplicity; adjust in production
            if instrument["segment"] != "NSE-EQ" or instrument["last_price"] > config.penny_stock_threshold:
                continue
            
            # Fetch historical data
            try:
                historical = kite.historical_data(
                    instrument_id=instrument["instrument_token"],
                    from_date=start_date.strftime("%Y-%m-%d"),
                    to_date=end_date.strftime("%Y-%m-%d"),
                    interval="day"
                )
                
                if len(historical) < 5:  # Ensure enough data points
                    continue
                
                # Calculate growth
                prices = [data["close"] for data in historical]
                growth_percent = ((prices[-1] - prices[0]) / prices[0]) * 100 if prices[0] != 0 else 0
                
                # Check volume trend
                volumes = [data["volume"] for data in historical]
                avg_volume = np.mean(volumes)
                
                if growth_percent >= config.min_growth_percent and avg_volume > 10000:  # Basic filter
                    penny_stocks.append({
                        "tradingsymbol": instrument["tradingsymbol"],
                        "last_price": instrument["last_price"],
                        "growth_percent": growth_percent,
                        "avg_volume": avg_volume
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch historical data for {instrument['tradingsymbol']}: {str(e)}")
                continue
        
        # Sort by growth percent
        penny_stocks = sorted(penny_stocks, key=lambda x: x["growth_percent"], reverse=True)[:config.max_stocks]
        logger.info(f"Found {len(penny_stocks)} penny stocks with growth potential")
        return penny_stocks
    except Exception as e:
        logger.error(f"Failed to find penny stocks: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to find penny stocks: {str(e)}")

# AI-driven order placement endpoint
@app.post("/api/ai-place-orders")
async def ai_place_orders(config: AIOrderConfig):
    if KITE_ID not in session_storage:
        logger.error("No access_token found for user")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        # Check available funds
        available_funds = await check_available_funds()
        if available_funds < 1000:  # Minimum threshold
            logger.warning("Insufficient funds for AI trading")
            raise HTTPException(status_code=400, detail="Insufficient funds for trading")
        
        # Cap investment to available funds
        max_investment = min(config.max_investment, available_funds * 0.8)  # Use 80% of funds for safety
        
        # Find penny stocks
        penny_stocks = await find_penny_stocks(config)
        if not penny_stocks:
            logger.info("No suitable penny stocks found")
            raise HTTPException(status_code=404, detail="No suitable penny stocks found")
        
        # Distribute investment across stocks
        investment_per_stock = max_investment / min(config.max_stocks, len(penny_stocks))
        orders_placed = []
        
        for stock in penny_stocks:
            try:
                # Calculate quantity based on last price
                quantity = int(investment_per_stock / stock["last_price"])
                if quantity < 1:
                    logger.info(f"Skipping {stock['tradingsymbol']} due to insufficient funds for 1 share")
                    continue
                
                # Place market order
                order_response = kite.place_order(
                    variety=kite.VARIETY_REGULAR,
                    exchange="NSE",
                    tradingsymbol=stock["tradingsymbol"],
                    transaction_type="BUY",
                    quantity=quantity,
                    product=kite.PRODUCT_CNC,
                    order_type=kite.ORDER_TYPE_MARKET
                )
                
                orders_placed.append({
                    "tradingsymbol": stock["tradingsymbol"],
                    "quantity": quantity,
                    "order_id": order_response["order_id"]
                })
                logger.info(f"Placed order for {stock['tradingsymbol']}: {quantity} shares")
            except Exception as e:
                logger.warning(f"Failed to place order for {stock['tradingsymbol']}: {str(e)}")
                continue
        
        if not orders_placed:
            logger.info("No orders were placed")
            raise HTTPException(status_code=400, detail="No orders were placed")
        
        return JSONResponse(content={
            "message": "AI orders placed successfully",
            "orders": orders_placed
        }, status_code=200)
    except Exception as e:
        logger.error(f"Failed to process AI orders: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process AI orders: {str(e)}")

# Run the app with Uvicorn
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=443)