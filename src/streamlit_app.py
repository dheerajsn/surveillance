import streamlit as st
import asyncio
import json
import pandas as pd
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Import your agent
from src.agents.langgraph_agent import SurveillanceAgent

# Configure Streamlit
st.set_page_config(
    page_title="Market Surveillance Assistant",
    page_icon="🔍",
    layout="wide"
)

# Initialize session state
if 'agent' not in st.session_state:
    try:
        st.session_state.agent = SurveillanceAgent()
        st.session_state.agent_status = "✅ Connected"
    except Exception as e:
        st.session_state.agent = None
        st.session_state.agent_status = f"❌ Error: {str(e)}"
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

def main():
    st.title("🔍 Market Surveillance Assistant")
    st.markdown("Ask questions about surveillance alerts, traders, and market misconduct patterns.")
    
    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")
        
        # MCP Server Status
        st.subheader("MCP Servers")
        st.success("✅ Neo4j Server Connected")
        st.success("✅ REST API Server Connected")
        
        # Quick actions
        st.subheader("Quick Actions")
        if st.button("Get Recent Alerts"):
            st.session_state.quick_query = "Show me the latest surveillance alerts"
        if st.button("Bill Lyons Analysis"):
            st.session_state.quick_query = "Get all alerts and workflow for Bill Lyons"
        if st.button("Spoofing Alerts"):
            st.session_state.quick_query = "Show me all spoofing alerts from last week"
    
    # Main chat interface
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Chat with Surveillance Agent")
        
        # Chat history
        chat_container = st.container()
        
        # Query input
        query = st.text_input(
            "Ask about surveillance data:",
            value=st.session_state.get('quick_query', ''),
            placeholder="e.g., 'Get all alerts with workflow for Bill Lyons'"
        )
        
        if st.button("Send Query") or st.session_state.get('quick_query'):
            if query or st.session_state.get('quick_query'):
                actual_query = query or st.session_state.get('quick_query')
                st.session_state.quick_query = ""
                
                # Add user message to chat
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": actual_query,
                    "timestamp": datetime.now()
                })
                
                # Process query with agent
                with st.spinner("Processing query..."):
                    try:
                        result = asyncio.run(st.session_state.agent.process_query(actual_query))
                        
                        # Add agent response to chat
                        st.session_state.chat_history.append({
                            "role": "assistant", 
                            "content": result,
                            "timestamp": datetime.now()
                        })
                        
                    except Exception as e:
                        st.error(f"Error processing query: {str(e)}")
        
        # Display chat history
        with chat_container:
            for message in st.session_state.chat_history:
                if message["role"] == "user":
                    st.chat_message("user").write(message["content"])
                else:
                    # Display agent response with structured data
                    with st.chat_message("assistant"):
                        display_agent_response(message["content"])
    
    with col2:
        st.subheader("Quick Stats")
        
        # Display summary statistics
        if st.session_state.chat_history:
            latest_result = st.session_state.chat_history[-1]
            if latest_result["role"] == "assistant":
                display_summary_stats(latest_result["content"])

def display_agent_response(result):
    """Display structured agent response"""
    if isinstance(result, dict):
        # Display analysis
        if "analysis" in result and result["analysis"]:
            st.write("**Analysis:**")
            st.write(result["analysis"])
        
        # Display insights
        if "insights" in result and result["insights"]:
            st.write("**Key Insights:**")
            for i, insight in enumerate(result["insights"], 1):
                st.write(f"{i}. {insight}")
        
        # Display Neo4j data
        if "neo4j_data" in result and result["neo4j_data"]:
            display_neo4j_data(result["neo4j_data"])
        
        # Display API data
        if "api_data" in result and result["api_data"]:
            display_api_data(result["api_data"])
    else:
        st.write(str(result))

def display_neo4j_data(neo4j_data):
    """Display Neo4j data with visualizations"""
    st.write("**Historical Data:**")
    
    # Alerts data
    if "alerts" in neo4j_data and neo4j_data["alerts"].get("alerts"):
        alerts = neo4j_data["alerts"]["alerts"]
        
        # Create alerts DataFrame
        alerts_df = pd.DataFrame(alerts)
        
        if not alerts_df.empty:
            st.write(f"Found {len(alerts_df)} alerts")
            
            # Alert type distribution
            if 'alert_type' in alerts_df.columns:
                alert_counts = alerts_df['alert_type'].value_counts()
                fig = px.pie(values=alert_counts.values, names=alert_counts.index, 
                           title="Alert Type Distribution")
                st.plotly_chart(fig, use_container_width=True)
            
            # Display alerts table
            st.dataframe(alerts_df)
    
    # Network data
    if "network" in neo4j_data and neo4j_data["network"].get("connected_traders"):
        st.write("**Trader Network:**")
        network = neo4j_data["network"]["connected_traders"]
        
        if network:
            network_df = pd.DataFrame(network)
            st.dataframe(network_df)

def display_api_data(api_data):
    """Display real-time API data"""
    st.write("**Real-time Data:**")
    
    if "real_time_alerts" in api_data:
        real_time = api_data["real_time_alerts"]
        if isinstance(real_time, dict) and "alerts" in real_time:
            alerts = real_time["alerts"]
            if alerts:
                alerts_df = pd.DataFrame(alerts)
                st.dataframe(alerts_df)

def display_summary_stats(result):
    """Display summary statistics in sidebar"""
    if isinstance(result, dict):
        # Count various metrics
        total_alerts = 0
        alert_types = set()
        
        # From Neo4j data
        if "neo4j_data" in result and result["neo4j_data"].get("alerts", {}).get("alerts"):
            alerts = result["neo4j_data"]["alerts"]["alerts"]
            total_alerts += len(alerts)
            for alert in alerts:
                if "alert_type" in alert:
                    alert_types.add(alert["alert_type"])
        
        # From API data  
        if "api_data" in result and result["api_data"].get("real_time_alerts", {}).get("alerts"):
            real_time_alerts = result["api_data"]["real_time_alerts"]["alerts"]
            total_alerts += len(real_time_alerts)
        
        # Display metrics
        st.metric("Total Alerts", total_alerts)
        st.metric("Alert Types", len(alert_types))
        
        if alert_types:
            st.write("**Alert Types:**")
            for alert_type in alert_types:
                st.write(f"• {alert_type}")

if __name__ == "__main__":
    main()