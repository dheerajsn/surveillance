import asyncio
import json
import os
from typing import Dict, List, Any, TypedDict
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
import aiohttp
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class SurveillanceState(TypedDict):
    messages: List[Dict[str, Any]]
    query: str
    neo4j_data: Dict[str, Any]
    api_data: Dict[str, Any]
    analysis: str
    insights: List[str]

class FastMCPClient:
    """Client to connect to FastMCP servers via HTTP"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def call_tool(self, tool_name: str, **kwargs) -> Dict:
        """Call FastMCP tool via HTTP"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": kwargs
            }
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/mcp",  # Changed from /message to /mcp
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("result", [{}])[0] if result.get("result") else {}
                else:
                    return {"error": f"HTTP error: {response.status}"}
        except Exception as e:
            return {"error": f"Connection error: {str(e)}"}
    
    async def list_tools(self) -> List[Dict]:
        """List available tools"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {}
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/mcp",  # Changed from /message to /mcp
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("result", {}).get("tools", [])
                else:
                    return []
        except Exception as e:
            print(f"Error listing tools: {e}")
            return []

class SurveillanceAgent:
    def __init__(self):
        # Initialize with OpenAI API key from environment
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
            
        self.llm = ChatOpenAI(
            model="gpt-4", 
            temperature=0,
            openai_api_key=openai_api_key
        )
        
        # Initialize FastMCP clients with environment variables
        neo4j_host = os.getenv("NEO4J_MCP_HOST", "localhost")
        neo4j_port = os.getenv("NEO4J_MCP_PORT", "8001")
        api_host = os.getenv("API_MCP_HOST", "localhost") 
        api_port = os.getenv("API_MCP_PORT", "8002")
        
        self.neo4j_client = FastMCPClient(f"http://{neo4j_host}:{neo4j_port}")
        self.api_client = FastMCPClient(f"http://{api_host}:{api_port}")
        
        # Create the agent graph
        self.graph = self._create_graph()
        
        print(f"✅ SurveillanceAgent initialized")
        print(f"   Neo4j MCP: http://{neo4j_host}:{neo4j_port}")
        print(f"   API MCP: http://{api_host}:{api_port}")

    def _create_graph(self) -> StateGraph:
        """Create the LangGraph workflow"""
        workflow = StateGraph(SurveillanceState)
        
        # Add nodes
        workflow.add_node("parse_query", self._parse_query)
        workflow.add_node("fetch_neo4j_data", self._fetch_neo4j_data)
        workflow.add_node("fetch_api_data", self._fetch_api_data)
        workflow.add_node("analyze_data", self._analyze_data)
        workflow.add_node("generate_insights", self._generate_insights)
        
        # Define edges
        workflow.set_entry_point("parse_query")
        workflow.add_edge("parse_query", "fetch_neo4j_data")
        workflow.add_edge("parse_query", "fetch_api_data")
        workflow.add_edge("fetch_neo4j_data", "analyze_data")
        workflow.add_edge("fetch_api_data", "analyze_data")
        workflow.add_edge("analyze_data", "generate_insights")
        workflow.add_edge("generate_insights", END)
        
        return workflow.compile()
    
    async def _parse_query(self, state: SurveillanceState) -> SurveillanceState:
        """Parse user query to determine what data to fetch"""
        query = state["query"]
        
        # Use LLM to extract entities and intent
        system_prompt = """
        You are a surveillance query parser. Extract the following from user queries:
        1. Trader names mentioned
        2. Alert types of interest
        3. Time periods
        4. Specific analysis requested
        
        Respond in JSON format with extracted entities.
        """
        
        response = await self.llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Parse this query: {query}")
        ])
        
        # Store parsed information
        state["messages"].append({
            "role": "system",
            "content": f"Parsed query: {response.content}"
        })
        
        return state
    
    async def _fetch_neo4j_data(self, state: SurveillanceState) -> SurveillanceState:
        """Fetch data from Neo4j via FastMCP server"""
        query = state["query"].lower()
        
        async with self.neo4j_client as client:
            # Determine which Neo4j tools to use based on query
            if "bill lyons" in query or any(name in query for name in ["trader", "alerts"]):
                # Extract trader name
                trader_name = self._extract_trader_name(query)
                if trader_name:
                    # Get alerts for trader
                    alerts_data = await client.call_tool(
                        "get_alerts_for_trader",
                        trader_name=trader_name,
                        limit=20
                    )
                    
                    # Get trader network
                    network_data = await client.call_tool(
                        "get_trader_network",
                        trader_name=trader_name,
                        depth=2
                    )
                    
                    state["neo4j_data"] = {
                        "alerts": alerts_data,
                        "network": network_data
                    }
            
            elif "spoofing" in query:
                # Get spoofing alerts
                spoofing_data = await client.call_tool(
                    "get_alerts_by_type",
                    misconduct_type="spoofing",
                    limit=15
                )
                state["neo4j_data"] = {"spoofing_alerts": spoofing_data}
            
            elif "wash trading" in query:
                # Get wash trading alerts
                wash_data = await client.call_tool(
                    "get_alerts_by_type", 
                    misconduct_type="wash_trading",
                    limit=15
                )
                state["neo4j_data"] = {"wash_trading_alerts": wash_data}
        
        return state
    
    async def _fetch_api_data(self, state: SurveillanceState) -> SurveillanceState:
        """Fetch data from REST API via FastMCP server"""
        async with self.api_client as client:
            # Get real-time alerts
            real_time_data = await client.call_tool(
                "get_real_time_alerts",
                status="active",
                limit=10
            )
            
            state["api_data"] = {
                "real_time_alerts": real_time_data
            }
            
            # If specific trader mentioned, get their profile
            query = state["query"].lower()
            if "bill lyons" in query:
                trader_profile = await client.call_tool(
                    "get_trader_profile",
                    trader_id="Bill Lyons"
                )
                state["api_data"]["trader_profile"] = trader_profile
        
        return state
    
    async def _analyze_data(self, state: SurveillanceState) -> SurveillanceState:
        """Analyze the fetched data using LLM"""
        neo4j_data = state.get("neo4j_data", {})
        api_data = state.get("api_data", {})
        
        # Combine and analyze data
        analysis_prompt = f"""
        Analyze the following surveillance data for patterns and insights:
        
        Historical Data from Neo4j:
        {json.dumps(neo4j_data, indent=2)}
        
        Real-time Data from API:
        {json.dumps(api_data, indent=2)}
        
        Provide a comprehensive analysis focusing on:
        1. Alert patterns and trends
        2. Risk assessment for traders involved
        3. Notable findings or red flags
        4. Behavioral patterns
        5. Recommendations for surveillance team
        """
        
        response = await self.llm.ainvoke([
            SystemMessage(content="You are an expert market surveillance analyst. Provide detailed analysis of trading data and alert patterns."),
            HumanMessage(content=analysis_prompt)
        ])
        
        state["analysis"] = response.content
        return state
    
    async def _generate_insights(self, state: SurveillanceState) -> SurveillanceState:
        """Generate actionable insights"""
        analysis = state["analysis"]
        
        insights_prompt = f"""
        Based on this surveillance analysis:
        {analysis}
        
        Generate specific, actionable insights for the surveillance team:
        1. Immediate risks requiring attention
        2. Patterns that suggest coordinated activity
        3. Recommended investigative actions
        4. Priority levels for different alerts
        5. Potential regulatory implications
        
        Format as a numbered list of clear, actionable insights.
        """
        
        response = await self.llm.ainvoke([
            SystemMessage(content="Generate clear, actionable surveillance insights that help the compliance team prioritize their work."),
            HumanMessage(content=insights_prompt)
        ])
        
        # Parse insights into list
        insights_text = response.content
        insights = [
            line.strip() 
            for line in insights_text.split('\n') 
            if line.strip() and any(char.isdigit() for char in line[:3])
        ]
        
        state["insights"] = insights
        return state
    
    def _extract_trader_name(self, query: str) -> str:
        """Extract trader name from query"""
        # Simple extraction - in practice, use NER or more sophisticated parsing
        if "bill lyons" in query.lower():
            return "Bill Lyons"
        elif "trader" in query:
            # Try to extract trader name using simple pattern matching
            words = query.split()
            for i, word in enumerate(words):
                if word.lower() == "trader" and i + 1 < len(words):
                    return words[i + 1]
        return ""
    
    async def process_query(self, query: str) -> Dict[str, Any]:
        """Process a surveillance query end-to-end"""
        initial_state = SurveillanceState(
            messages=[],
            query=query,
            neo4j_data={},
            api_data={},
            analysis="",
            insights=[]
        )
        
        try:
            result = await self.graph.ainvoke(initial_state)
            return result
        except Exception as e:
            return {
                "error": f"Error processing query: {str(e)}",
                "query": query,
                "insights": [f"Failed to process query: {str(e)}"]
            }

# Convenience function for testing
async def test_agent():
    """Test the surveillance agent"""
    agent = SurveillanceAgent()
    
    test_queries = [
        "Get all alerts with workflow for Bill Lyons",
        "Show me recent spoofing alerts",
        "What are the latest surveillance concerns?"
    ]
    
    for query in test_queries:
        print(f"\n🔍 Processing: {query}")
        result = await agent.process_query(query)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
        else:
            print(f"✅ Analysis: {result.get('analysis', 'No analysis')[:200]}...")
            print(f"💡 Insights: {len(result.get('insights', []))} generated")

if __name__ == "__main__":
    asyncio.run(test_agent())