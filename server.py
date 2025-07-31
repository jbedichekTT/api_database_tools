import asyncio
import json
import logging
from typing import List, Optional

from fastmcp import FastMCP
from tools.get_decomposed_function import decompose_function
from tools.get_llk_functions import query_llk_functions
from tools.get_similar_symbols import find_similar_symbols

# Configure logging for debugging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP(name="tt-metal-tools", version="1.0.0")

# Tool: decompose_function
@mcp.tool(name="decompose_function", description="Returns a complete implementation of every API function called in a given function and file, searched recursively to maximum depth.  Use this to understand how a function works behind the scenes. \
Doesn't work for functions that are not defined in the TT-Metal API database.")
async def decompose_function_tool(file_path: str, function_name: str) -> dict:
    logger.info(f"🛠️  Called decompose_function with file_path={file_path}, function_name={function_name}")
    result = await decompose_function(file_path=file_path, function_name=function_name)
    logger.info(f"✅ decompose_function result: {len(result.get('dependencies', []))} dependencies found")
    return result

# Tool: query_llk_functions
@mcp.tool(name="query_llk_functions", description="Returns validated names and signatures of LLK API calls similar to the query. Includes all functions from this file: tt_metal/hw/ckernels/wormhole_b0/metal/llk_api")
async def query_llk_functions_tool(keyword: str) -> dict:
    logger.info(f"🛠️  Called query_llk_functions with keyword={keyword}")
    result = await query_llk_functions(keyword=keyword)
    logger.info(f"✅ query_llk_functions result count: {len(result.get('functions', []))} functions found")
    return result

# Tool: find_similar_symbols
@mcp.tool(name="find_similar_symbols", description="Find symbols similar to an incorrect symbol name, returns validated names and signatures similar to the query.")
async def find_similar_symbols_tool(symbol: str, max_results: int = 10, search_paths: Optional[List[str]] = None) -> dict:
    logger.info(f"🛠️  Called find_similar_symbols with symbol={symbol}, max_results={max_results}")
    result = await find_similar_symbols(incorrect_symbol=symbol, max_results=max_results, search_paths=search_paths)
    logger.info(f"✅ find_similar_symbols returned {len(result.get('results', []))} suggestions")
    return result

if __name__ == "__main__":
    # Run FastMCP server (default STDIO transport)
    mcp.run()
