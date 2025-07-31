import asyncio
import json
from typing import Any, Dict, List
import logging 

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.shared.exceptions import McpError
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from api_database_tools.tools.get_decomposed_function import decompose_function
from api_database_tools.tools.get_llk_functions import query_llk_functions  
from api_database_tools.tools.get_similar_symbols import find_similar_symbols

# Create server instance
app = Server("tt-metal-tools")

# Tool definitions
TOOLS = [
    Tool(
        name="decompose_function",
        description="Analyze function dependencies and output them in dependency order",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the source file containing the function"
                },
                "function_name": {
                    "type": "string", 
                    "description": "Name of the function to analyze"
                }
            },
            "required": ["file_path", "function_name"]
        }
    ),
    Tool(
        name="query_llk_functions",
        description="Query SFPI/LLK functions from TT-Metal API database by substring search",
        inputSchema={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Keyword to search for in function names (e.g., 'exp', 'neg', 'sqrt')"
                }
            },
            "required": ["keyword"]
        }
    ),
    Tool(
        name="find_similar_symbols",
        description="Find symbols similar to a potentially incorrect symbol name",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The symbol to search for"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10
                }
            },
            "required": ["symbol"]
        }
    )
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return TOOLS

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> List[TextContent]:
    """Execute a tool and return results."""
    # Log tool invocation
    logger.info(f"🛠️  MCP Tool Called: {name}")
    logger.info(f"🛠️  Arguments: {json.dumps(arguments, indent=2)}")
    
    try:
        if name == "decompose_function":
            result = await decompose_function(
                file_path=arguments["file_path"],
                function_name=arguments["function_name"],
                #database_path=arguments.get("database_path", "./api_impl_db.json")
            )
        
        elif name == "query_llk_functions":
            result = await query_llk_functions(
                keyword=arguments["keyword"],
                #database_path=arguments.get("database_path", "./api_signatures_db.json")
            )
        
        elif name == "find_similar_symbols":
            result = await find_similar_symbols(
                incorrect_symbol=arguments["incorrect_symbol"],
                max_results=arguments.get("max_results", 10),
                #database_path=arguments.get("database_path", "./api_signatures_db.json")
            )
        
        else:
            raise McpError(f"Unknown tool: {name}")
        
        # Log result summary
        logger.info(f"✅ Tool {name} completed successfully")
        if isinstance(result, dict):
            if "error" in result:
                logger.error(f"❌ Tool error: {result['error']}")
            elif "results" in result:
                logger.info(f"✅ Found {len(result.get('results', []))} results")
        
        # Format result as JSON string
        if isinstance(result, dict):
            content = json.dumps(result, indent=2)
        else:
            content = str(result)
        
        return [TextContent(type="text", text=content)]
        
    except Exception as e:
        logger.error(f"❌ Tool execution failed: {str(e)}")
        raise McpError(f"Tool execution failed: {str(e)}")

async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="tt-metal-tools",
                server_version="1.0.0",
                capabilities={}
            )
        )

def main_sync():
    """Synchronous entry point for console script."""
    asyncio.run(main())

if __name__ == "__main__":
    asyncio.run(main())