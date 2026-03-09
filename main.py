from fastapi import FastAPI  
from fastapi.middleware.cors import CORSMiddleware  
import sys  
import os  
  
# Add parent directory to path to import SovereignForge modules  
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))  
  
app = FastAPI(title="SovereignForge Paper Trading API")  
  
app.add_middleware(  
    CORSMiddleware,  
    allow_origins=["*"],  
    allow_credentials=True,  
    allow_methods=["*"],  
    allow_headers=["*"],  
)  
  
@app.get("/")  
async def root():  
    return {"message": "SovereignForge Paper Trading API"}  
  
@app.get("/api/portfolio")  
async def get_portfolio():  
    # Mock data for now  
    return {  
        "balance": 9500.0,  
        "totalValue": 10247.89,  
        "pnl": 247.89,  
        "pnlPct": 2.48,  
        "positions": [  
            {  
                "pair": "XRP/USDC",  
                "strategy": "fib_dca",  
                "side": "buy",  
                "entryPrice": 0.45,  
                "quantity": 1000,  
                "pnl": 47.89,  
                "pnlPct": 10.6,  
                "status": "open"  
            }  
        ]  
    } 
