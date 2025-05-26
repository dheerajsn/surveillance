import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from fastmcp import FastMCP
from neo4j import AsyncGraphDatabase
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("GMS Neo4j Surveillance")

class Neo4jService:
    def __init__(self):
        self.driver = None
        
    async def initialize_driver(self):
        """Initialize Neo4j driver"""
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        
        print(f"Connecting to Neo4j at: {uri}")
        self.driver = AsyncGraphDatabase.driver(uri, auth=(username, password))
        
    async def close_driver(self):
        """Close Neo4j driver"""
        if self.driver:
            await self.driver.close()

# Create service instance
neo4j_service = Neo4jService()

@mcp.tool()
async def get_alerts_for_trader(trader_name: str, limit: int = 10) -> Dict[str, Any]:
    """
    Get all surveillance alerts for a specific trader
    
    Args:
        trader_name: Name of the trader to search for
        limit: Maximum number of alerts to return
    """
    async with neo4j_service.driver.session() as session:
        query = """
        MATCH (t:Trader {name: $trader_name})-[:INVOLVED_IN]->(a:Alert)
        OPTIONAL MATCH (a)-[:HAS_WORKFLOW]->(w:Workflow)
        OPTIONAL MATCH (a)-[:CONTAINS]->(o:Order)
        RETURN a.alert_id as alert_id,
               a.alert_type as alert_type,
               a.created_date as created_date,
               a.status as status,
               w.commentary as commentary,
               w.disposition as disposition,
               collect(DISTINCT {
                   order_id: o.order_id,
                   asset_type: o.asset_type,
                   venue: o.venue_mic,
                   quantity: o.visible_usd_quantity,
                   placed_time: o.placed_time,
                   cancelled_time: o.cancelled_time
               }) as orders
        ORDER BY a.created_date DESC
        LIMIT $limit
        """
        
        result = await session.run(query, trader_name=trader_name, limit=limit)
        records = await result.data()
        
        return {
            "trader_name": trader_name,
            "total_alerts": len(records),
            "alerts": records
        }

@mcp.tool()
async def get_alert_workflow(alert_id: str) -> Dict[str, Any]:
    """
    Get the complete workflow and commentary for a specific alert
    
    Args:
        alert_id: Alert ID to get workflow for
    """
    async with neo4j_service.driver.session() as session:
        query = """
        MATCH (a:Alert {alert_id: $alert_id})
        OPTIONAL MATCH (a)-[:HAS_WORKFLOW]->(w:Workflow)
        OPTIONAL MATCH (a)-[:CONTAINS]->(o:Order)
        OPTIONAL MATCH (a)<-[:INVOLVED_IN]-(t:Trader)
        RETURN a.alert_id as alert_id,
               a.alert_type as alert_type,
               a.created_date as created_date,
               a.status as status,
               w.commentary as commentary,
               w.disposition as disposition,
               w.supervisor as supervisor,
               w.review_date as review_date,
               collect(DISTINCT t.name) as traders,
               collect(DISTINCT {
                   order_id: o.order_id,
                   asset_type: o.asset_type,
                   venue: o.venue_mic,
                   quantity: o.visible_usd_quantity,
                   placed_time: o.placed_time,
                   cancelled_time: o.cancelled_time,
                   executed_time: o.executed_time,
                   is_algo: o.is_algo
               }) as orders
        """
        
        result = await session.run(query, alert_id=alert_id)
        record = await result.single()
        
        if record:
            return dict(record)
        else:
            return {"error": f"Alert {alert_id} not found"}

@mcp.tool()
async def get_alerts_by_type(misconduct_type: str, limit: int = 10) -> Dict[str, Any]:
    """
    Get alerts filtered by misconduct type
    
    Args:
        misconduct_type: Type of misconduct (spoofing, wash_trading, layering, front_running)
        limit: Maximum number of alerts to return
    """
    async with neo4j_service.driver.session() as session:
        query = """
        MATCH (a:Alert {alert_type: $misconduct_type})
        OPTIONAL MATCH (a)-[:HAS_WORKFLOW]->(w:Workflow)
        OPTIONAL MATCH (a)<-[:INVOLVED_IN]-(t:Trader)
        RETURN a.alert_id as alert_id,
               a.created_date as created_date,
               a.status as status,
               w.commentary as commentary,
               w.disposition as disposition,
               collect(DISTINCT t.name) as traders
        ORDER BY a.created_date DESC
        LIMIT $limit
        """
        
        result = await session.run(query, misconduct_type=misconduct_type, limit=limit)
        records = await result.data()
        
        return {
            "misconduct_type": misconduct_type,
            "total_alerts": len(records),
            "alerts": records
        }

@mcp.tool()
async def get_trader_network(trader_name: str, depth: int = 2) -> Dict[str, Any]:
    """
    Get network of traders connected to a specific trader
    
    Args:
        trader_name: Central trader name
        depth: Network depth (degrees of separation)
    """
    async with neo4j_service.driver.session() as session:
        query = """
        MATCH path = (t:Trader {name: $trader_name})-[:TRADES_WITH*1..$depth]-(connected:Trader)
        RETURN DISTINCT connected.name as connected_trader,
               length(path) as degrees_of_separation,
               [rel in relationships(path) | {
                   type: type(rel),
                   properties: properties(rel)
               }] as relationships
        ORDER BY degrees_of_separation, connected_trader
        """
        
        result = await session.run(query, trader_name=trader_name, depth=depth)
        records = await result.data()
        
        return {
            "central_trader": trader_name,
            "network_depth": depth,
            "connected_traders": records
        }

@mcp.tool()
async def search_alerts_by_criteria(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    venue: Optional[str] = None,
    asset_type: Optional[str] = None,
    min_amount: Optional[float] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Search alerts by multiple criteria
    
    Args:
        start_date: Start date (YYYY-MM-DD format)
        end_date: End date (YYYY-MM-DD format)
        venue: Venue MIC code
        asset_type: Asset type filter
        min_amount: Minimum USD amount
        limit: Maximum results
    """
    async with neo4j_service.driver.session() as session:
        # Build dynamic query based on criteria
        where_clauses = []
        params = {"limit": limit}
        
        if start_date:
            where_clauses.append("a.created_date >= date($start_date)")
            params["start_date"] = start_date
            
        if end_date:
            where_clauses.append("a.created_date <= date($end_date)")
            params["end_date"] = end_date
            
        if venue:
            where_clauses.append("ANY(o IN orders WHERE o.venue_mic = $venue)")
            params["venue"] = venue
            
        if asset_type:
            where_clauses.append("ANY(o IN orders WHERE o.asset_type = $asset_type)")
            params["asset_type"] = asset_type
            
        if min_amount:
            where_clauses.append("ANY(o IN orders WHERE o.visible_usd_quantity >= $min_amount)")
            params["min_amount"] = min_amount
        
        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = f"""
        MATCH (a:Alert)
        OPTIONAL MATCH (a)-[:CONTAINS]->(o:Order)
        WITH a, collect(o) as orders
        {where_clause}
        OPTIONAL MATCH (a)-[:HAS_WORKFLOW]->(w:Workflow)
        OPTIONAL MATCH (a)<-[:INVOLVED_IN]-(t:Trader)
        RETURN a.alert_id as alert_id,
               a.alert_type as alert_type,
               a.created_date as created_date,
               a.status as status,
               w.commentary as commentary,
               w.disposition as disposition,
               collect(DISTINCT t.name) as traders
        ORDER BY a.created_date DESC
        LIMIT $limit
        """
        
        result = await session.run(query, **params)
        records = await result.data()
        
        return {
            "search_criteria": {
                "start_date": start_date,
                "end_date": end_date,
                "venue": venue,
                "asset_type": asset_type,
                "min_amount": min_amount
            },
            "total_results": len(records),
            "alerts": records
        }

# Startup and shutdown handlers
@mcp.startup()
async def startup():
    """Initialize Neo4j connection on startup"""
    await neo4j_service.initialize_driver()
    print("✅ Neo4j MCP Server started successfully")
    print("Available tools:")
    print("  - get_alerts_for_trader")
    print("  - get_alert_workflow") 
    print("  - get_alerts_by_type")
    print("  - get_trader_network")
    print("  - search_alerts_by_criteria")

@mcp.shutdown()
async def shutdown():
    """Clean up Neo4j connection on shutdown"""
    await neo4j_service.close_driver()
    print("🔌 Neo4j connection closed")

if __name__ == "__main__":
    # Run with HTTP transport
    mcp.run(
        transport="sse",  # Server-Sent Events transport
        host=os.getenv("MCP_HOST", "localhost"),
        port=int(os.getenv("MCP_PORT", "8001"))
    )