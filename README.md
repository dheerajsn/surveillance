# Market Surveillance System

A comprehensive market surveillance system using LangGraph agents, Neo4j graph database, and FastMCP servers for detecting market misconduct patterns.

## 🏗️ Architecture
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ │ Streamlit UI │────│ LangGraph │────│ FastMCP │ │ │ │ Agent │ │ Servers │ └─────────────────┘ └─────────────────┘ └─────────────────┘ │ │ │ ┌───────┴───────┐ │ │ │ ┌──────▼──────┐ ▼ ▼ │ OpenAI │ ┌─────────┐ ┌─────────┐ │ GPT-4 │ │ Neo4j │ │ REST │ └─────────────┘ │ Server │ │ API │ └─────────┘ └─────────┘


## 🚀 Features

- **Zero-shot surveillance agents** using OpenAI GPT-4
- **Graph-based analysis** with Neo4j for trader networks
- **Real-time alerts** via FastMCP servers
- **Interactive dashboard** with Streamlit
- **Market misconduct detection**: Spoofing, wash trading, layering, front-running
- **Automated commentary generation** for alert dispositions

## 📋 Prerequisites

- Python 3.8+
- Neo4j Database
- OpenAI API Key
- Docker (optional)

## 🛠️ Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/market-surveillance-system.git
cd market-surveillance-system