#!/usr/bin/env python3
"""
MCP Tool for querying SFPI functions from the TT-Metal API database.
Simple substring search in function names.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict


class LLKFunctionQuery:
    """Query LLK functions from the TT-Metal API database using simple substring search."""
    
    # Hardcoded but easily configurable database path
    DATABASE_PATH = "./api_signatures_db.json"
    
    # Target path for SFPI functions
    SFPI_BASE_PATH = "hw/ckernels/wormhole_b0/metal/llk_api"
    
    def __init__(self, database_path: Optional[str] = None):
        """Initialize with database path."""
        self.database_path = Path(database_path or self.DATABASE_PATH)
        self.database = None
        self._load_database()
    
    def _load_database(self):
        """Load the API database from JSON file."""
        if not self.database_path.exists():
            raise FileNotFoundError(f"Database not found at: {self.database_path}")
        
        with open(self.database_path, 'r') as f:
            self.database = json.load(f)
    
    def _is_sfpi_header(self, header_path: str) -> bool:
        """Check if a header is in the SFPI path."""
        return header_path.startswith(self.SFPI_BASE_PATH)
    
    def _normalize_include_path(self, header_path: str) -> str:
        """Convert header path to normalized include statement."""
        # Remove any leading slashes
        header_path = header_path.lstrip('/')
        
        # For SFPI headers, we want to include from the llk_api directory
        if header_path.startswith(self.SFPI_BASE_PATH):
            # Extract the relative path from llk_api
            relative_path = header_path[len(self.SFPI_BASE_PATH):].lstrip('/')
            if relative_path:
                return f"#include <llk_api/{relative_path}>"
            else:
                # If it's directly in llk_api
                filename = header_path.split('/')[-1]
                return f"#include <llk_api/{filename}>"
        
        # Fallback for other paths
        return f"#include <{header_path}>"
    
    def _search_functions_by_name(self, keyword: str) -> Dict[str, List[Dict]]:
        """
        Search for functions by name in the database using simple substring matching.
        Returns functions grouped by header.
        """
        # Dictionary to group functions by header
        functions_by_header = defaultdict(list)
        
        # Search through all APIs in the database
        for api_key, api_info in self.database.get("apis", {}).items():
            # Only consider functions and template functions
            if api_info.get("type") not in ["function", "template_function", "member_function"]:
                continue
            
            # Get the header path
            header = api_info.get("header", "")
            
            # Skip if not in SFPI path
            if not self._is_sfpi_header(header):
                continue
            
            # Get function name
            func_name = api_info.get("name", "")
            
            # Simple substring search - if keyword appears anywhere in function name
            if keyword.lower() in func_name.lower():
                functions_by_header[header].append({
                    "signature": api_info.get("signature", ""),
                    "name": func_name
                })
        
        return dict(functions_by_header)
    
    def query(self, keyword: str) -> Dict[str, List]:
        """
        Query SFPI functions by keyword in function names.
        Simple case-insensitive substring matching.
        
        Args:
            keyword: The keyword to search for in function names
            
        Returns:
            Dictionary with headers and their matching function signatures
        """
        # Search for functions - simple substring match
        functions_by_header = self._search_functions_by_name(keyword)
        
        # Build result
        result = {
            "keyword": keyword,
            "headers": []
        }
        
        # Sort headers by the number of matching functions (descending)
        sorted_headers = sorted(
            functions_by_header.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        for header, functions in sorted_headers:
            header_info = {
                "include": self._normalize_include_path(header),
                "signatures": [f["signature"] for f in functions]
            }
            result["headers"].append(header_info)
        
        return result

async def query_llk_functions(keyword: str) -> Dict[str, List]:
    """
    Query llk functions by searching function names directly.
    
    This tool searches the TT-Metal API database for functions whose names
    contain the given keyword (case-insensitive substring match), but only 
    returns those defined in the tt_metal/hw/ckernels/wormhole_b0/metal/llk_api 
    directory.
    
    Args:
        keyword (str): The keyword to search for in function names (e.g., "exp", "neg", "sqrt")
    
    Returns:
        Dict containing:
            - keyword: The searched keyword
            - headers: List of headers containing matching functions, each with:
                - include: Normalized include statement
                - signatures: List of function signatures
    
    Example:
        >>> result = query_sfpi_functions("exp")
        >>> print(result)
        {
            "keyword": "exp",
            "headers": [
                {
                    "include": "#include <llk_api/llk_sfpu_exp.h>",
                    "signatures": [
                        "void llk_math_exp_init()",
                        "void llk_math_exp(uint dst_index)",
                        "void llk_math_eltwise_unary_sfpu_exponential(uint dst_index)"
                    ]
                }
            ]
        }
    """
    try:
        # Create query instance
        query_instance = LLKFunctionQuery()
        
        # Perform the query
        result = query_instance.query(keyword)
        
        return result
        
    except FileNotFoundError as e:
        return {
            "error": f"Database not found: {str(e)}",
            "keyword": keyword,
            "headers": []
        }
    except Exception as e:
        return {
            "error": f"Query failed: {str(e)}",
            "keyword": keyword,
            "headers": []
        }


# Standalone testing
if __name__ == "__main__":
    import sys

    keyword = sys.argv[1]
    
    # Test the tool
    result = query_sfpi_functions(keyword)
    
    # Pretty print the result
    print(json.dumps(result, indent=2))