import asyncio
import json
from typing import Any, Dict, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Resource, Tool, TextContent, ImageContent, EmbeddedResource
from neo4j import AsyncGraphDatabase
import os

class Neo4jMCPServer:
    def __init__(self):
        self.server = Server("neo4j-surveillance")
        self.driver = None
        
        # Register tools
        self.server.list_tools = self.list_tools
        self.server.call_tool = self.call_tool
        
    async def initialize_driver(self):
        """Initialize Neo4j driver"""
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        
        self.driver = AsyncGraphDatabase.driver(uri, auth=(username, password))
        
    async def list_tools(self) -> List[Tool]:
        """List available tools"""
        return [
            Tool(
                name="get_alerts_for_trader",
                description="Get all surveillance alerts for a specific trader",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "trader_name": {
                            "type": "string",
                            "description": "Name of the trader to search for"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of alerts to return",
                            "default": 10
                        }
                    },
                    "required": ["trader_name"]
                }
            ),
            Tool(
                name="get_alert_workflow",
                description="Get the complete workflow and commentary for a specific alert",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "alert_id": {
                            "type": "string",
                            "description": "Alert ID to get workflow for"
                        }
                    },
                    "required": ["alert_id"]
                }
            ),
            Tool(
                name="get_alerts_by_type",
                description="Get alerts filtered by misconduct type (spoofing, wash_trading, etc.)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "misconduct_type": {
                            "type": "string",
                            "description": "Type of misconduct (spoofing, wash_trading, layering, front_running)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of alerts to return",
                            "default": 10
                        }
                    },
                    "required": ["misconduct_type"]
                }
            ),
            Tool(
                name="get_trader_network",
                description="Get network of traders connected to a specific trader",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "trader_name": {
                            "type": "string",
                            "description": "Central trader name"
                        },
                        "depth": {
                            "type": "integer",
                            "description": "Network depth (degrees of separation)",
                            "default": 2
                        }
                    },
                    "required": ["trader_name"]
                }
            )
        ]
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Execute tool calls"""
        try:
            if name == "get_alerts_for_trader":
                result = await self._get_alerts_for_trader(
                    arguments["trader_name"], 
                    arguments.get("limit", 10)
                )
            elif name == "get_alert_workflow":
                result = await self._get_alert_workflow(arguments["alert_id"])
            elif name == "get_alerts_by_type":
                result = await self._get_alerts_by_type(
                    arguments["misconduct_type"],
                    arguments.get("limit", 10)
                )
            elif name == "get_trader_network":
                result = await self._get_trader_network(
                    arguments["trader_name"],
                    arguments.get("depth", 2)
                )
            else:
                result = {"error": f"Unknown tool: {name}"}
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def _get_alerts_for_trader(self, trader_name: str, limit: int) -> Dict:
        """Get alerts for specific trader"""
        async with self.driver.session() as session:
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
    
    async def _get_alert_workflow(self, alert_id: str) -> Dict:
        """Get complete workflow for alert"""
        async with self.driver.session() as session:
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
    
    async def _get_alerts_by_type(self, misconduct_type: str, limit: int) -> Dict:
        """Get alerts by misconduct type"""
        async with self.driver.session() as session:
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
    
    async def _get_trader_network(self, trader_name: str, depth: int) -> Dict:
        """Get trader network"""
        async with self.driver.session() as session:
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

async def main():
    """Run the Neo4j MCP server"""
    server = Neo4jMCPServer()
    await server.initialize_driver()
    
    async with stdio_server() as (read_stream, write_stream):
        await server.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="neo4j-surveillance",
                server_version="1.0.0",
                capabilities=server.server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())