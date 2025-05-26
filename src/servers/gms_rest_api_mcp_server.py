import asyncio
import aiohttp
import os
from typing import Dict, List, Any, Optional
from fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("GMS REST API Surveillance")

class ApiService:
    def __init__(self):
        self.base_url = os.getenv("SURVEILLANCE_API_URL", "http://localhost:8000/api")
        self.session = None
        print(f"API Base URL: {self.base_url}")
    
    async def get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        if self.session:
            await self.session.close()

# Service instance
api_service = ApiService()

@mcp.tool()
async def get_real_time_alerts(status: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """
    Get real-time surveillance alerts from the API
    
    Args:
        status: Alert status filter (active, pending, closed)
        limit: Maximum number of alerts
    """
    session = await api_service.get_session()
    
    params = {"limit": limit}
    if status:
        params["status"] = status
        
    async with session.get(f"{api_service.base_url}/alerts", params=params) as response:
        if response.status == 200:
            return await response.json()
        else:
            return {"error": f"API error: {response.status}"}

@mcp.tool()
async def get_trader_profile(trader_id: str) -> Dict[str, Any]:
    """
    Get detailed trader profile from surveillance system
    
    Args:
        trader_id: Trader ID or name
    """
    session = await api_service.get_session()
    
    async with session.get(f"{api_service.base_url}/traders/{trader_id}") as response:
        if response.status == 200:
            return await response.json()
        else:
            return {"error": f"Trader not found: {trader_id}"}

@mcp.tool()
async def submit_alert_feedback(
    alert_id: str, 
    disposition: str, 
    commentary: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit feedback or disposition for an alert
    
    Args:
        alert_id: Alert ID
        disposition: Alert disposition (dismissed, escalated, etc.)
        commentary: Commentary for the disposition
    """
    session = await api_service.get_session()
    
    payload = {
        "disposition": disposition,
        "commentary": commentary or ""
    }
    
    async with session.post(
        f"{api_service.base_url}/alerts/{alert_id}/feedback", 
        json=payload
    ) as response:
        if response.status == 200:
            return {"success": True, "message": "Feedback submitted"}
        else:
            return {"error": f"Failed to submit feedback: {response.status}"}

@mcp.tool()
async def get_market_data(
    symbol: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get relevant market data for analysis
    
    Args:
        symbol: Asset symbol
        start_time: Start time (ISO format)
        end_time: End time (ISO format)
    """
    session = await api_service.get_session()
    
    params = {"symbol": symbol}
    if start_time:
        params["start_time"] = start_time
    if end_time:
        params["end_time"] = end_time
        
    async with session.get(f"{api_service.base_url}/market-data", params=params) as response:
        if response.status == 200:
            return await response.json()
        else:
            return {"error": f"Market data error: {response.status}"}

@mcp.startup()
async def startup():
    """Initialize API service"""
    print("✅ REST API MCP Server started successfully")
    print("Available tools:")
    print("  - get_real_time_alerts")
    print("  - get_trader_profile")
    print("  - submit_alert_feedback")
    print("  - get_market_data")

@mcp.shutdown()
async def shutdown():
    """Clean up API connections"""
    await api_service.close_session()
    print("🔌 API connections closed")

if __name__ == "__main__":
    mcp.run(
        transport="sse",
        host=os.getenv("MCP_HOST", "localhost"),
        port=int(os.getenv("MCP_PORT", "8002"))
    )