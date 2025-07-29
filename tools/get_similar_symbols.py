#!/usr/bin/env python3
"""
Simple Symbol Finder - A fresh, clean implementation for finding similar symbols
in the TT-Metal API database.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional


class SymbolFinder:
    """Find similar symbols in the TT-Metal API database."""
    
    def __init__(self, database_path: str = "./api_signatures_db.json", debug: bool = False):
        """Initialize the symbol finder."""
        self.database_path = Path(database_path)
        self.debug = debug
        self.database = None
        
        # Default search paths
        self.search_paths = [
            "hw/ckernels/wormhole_b0/metal/llk_api",
            "hostdevcommon"
        ]
        
        # Load database
        self.load_database()
    
    def log(self, message: str):
        """Print debug message if debug is enabled."""
        if self.debug:
            print(f"[DEBUG] {message}")
    
    def load_database(self):
        """Load the API database from JSON file."""
        self.log(f"Loading database from: {self.database_path}")
        
        if not self.database_path.exists():
            raise FileNotFoundError(f"Database not found at: {self.database_path}")
        
        try:
            with open(self.database_path, 'r') as f:
                self.database = json.load(f)
            
            self.log(f"Database loaded successfully")
            self.log(f"Total APIs: {len(self.database.get('apis', {}))}")
            self.log(f"Total headers: {len(self.database.get('headers', {}))}")
        except Exception as e:
            self.log(f"Error loading database: {e}")
            raise
    
    def is_in_search_paths(self, header_path: str) -> bool:
        """Check if a header is in one of the search paths."""
        #print(header_path)
        for search_path in self.search_paths:
            if header_path.startswith(search_path):
                return True
        return False
    
    def calculate_similarity(self, query: str, target: str) -> float:
        """Calculate simple similarity score between two strings."""
        query = query.lower()
        target = target.lower()
        
        # Exact match
        if query == target:
            return 1.0
        
        # Query is substring of target
        if query in target:
            return 0.8 + (len(query) / len(target)) * 0.2
        
        # Target is substring of query
        if target in query:
            return 0.7 + (len(target) / len(query)) * 0.2
        
        # Count matching characters
        matching = sum(1 for c in query if c in target)
        return matching / max(len(query), len(target)) * 0.5
    
    def find_similar_symbols(self, query: str, max_results: int = 10) -> List[Dict]:
        """Find symbols similar to the query."""
        self.log(f"Searching for symbols similar to: '{query}'")
        
        results = []
        checked_count = 0
        matched_count = 0
        
        # Get all APIs
        apis = self.database.get('apis', {})
        
        for api_key, api_info in apis.items():
            # Get header path
            header = api_info.get('header', '')
            
            # Check if in search paths
            if not self.is_in_search_paths(header):
                continue
            
            checked_count += 1
            
            # Get symbol name
            name = api_info.get('name', '')
            if not name:
                continue
            
            # Calculate similarity
            similarity = self.calculate_similarity(query, name)
            
            if similarity > 0.3:  # Threshold
                matched_count += 1
                results.append({
                    'name': name,
                    'type': api_info.get('type', 'unknown'),
                    'signature': api_info.get('signature', ''),
                    'header': header,
                    'similarity': similarity
                })
                
                if self.debug and similarity > 0.7:
                    self.log(f"High similarity match: {name} ({similarity:.3f})")
        
        self.log(f"Checked {checked_count} APIs in search paths")
        self.log(f"Found {matched_count} matches above threshold")
        
        # Sort by similarity
        results.sort(key=lambda x: x['similarity'], reverse=True)
        
        # Return top results
        return results[:max_results]
    
    def normalize_include_path(self, header_path: str) -> str:
        """Convert header path to include statement."""
        if header_path.startswith("tt_metal/hw/ckernels/wormhole_b0/metal/llk_api"):
            # Extract filename or relative path from llk_api
            parts = header_path.split("llk_api/", 1)
            if len(parts) > 1:
                return f"#include <llk_api/{parts[1]}>"
            else:
                filename = header_path.split('/')[-1]
                return f"#include <llk_api/{filename}>"
        
        elif header_path.startswith("tt_metal/hostdevcommon"):
            # Remove tt_metal/ prefix
            relative = header_path.replace("tt_metal/", "", 1)
            return f"#include <{relative}>"
        
        else:
            # Default case
            return f"#include <{header_path}>"
    
    def format_results(self, results: List[Dict]) -> Dict:
        """Format results for output."""
        formatted = {
            "results": []
        }
        
        for result in results:
            formatted_entry = {
                "name": result['name'],
                "type": result['type'],
                "signature": result['signature'],
                "include": self.normalize_include_path(result['header']),
                "similarity": round(result['similarity'], 3)
            }
            formatted['results'].append(formatted_entry)
        
        return formatted
    
    def search(self, query: str, max_results: int = 10) -> Dict:
        """Main search method - find and format results."""
        try:
            # Find similar symbols
            raw_results = self.find_similar_symbols(query, max_results)
            
            # Format results
            formatted = self.format_results(raw_results)
            
            # Add query to output
            formatted['query'] = query
            
            return formatted
            
        except Exception as e:
            self.log(f"Error during search: {e}")
            return {
                "error": str(e),
                "query": query,
                "results": []
            }


async def find_similar_symbols(
    incorrect_symbol: str,
    max_results: int = 10,
    search_paths: Optional[List[str]] = None,
    debug: bool = False
) -> Dict:
    """
    Find symbols similar to a potentially incorrect symbol name.
    
    Args:
        incorrect_symbol: The symbol to search for
        max_results: Maximum number of results to return
        search_paths: Custom search paths (optional)
        debug: Enable debug output
        
    Returns:
        Dictionary with search results
    """
    try:
        # Create finder instance
        finder = SymbolFinder(debug=debug)
        
        # Override search paths if provided
        if search_paths:
            finder.search_paths = search_paths
        
        # Run search
        return finder.search(incorrect_symbol, max_results)
        
    except Exception as e:
        return {
            "error": f"Search failed: {str(e)}",
            "query": incorrect_symbol,
            "results": []
        }


# Command line interface
def main():
    """Main function for command line usage."""
    import sys
    
    # Check arguments
    if len(sys.argv) < 2:
        print("Usage: python get_similar_symbols.py <symbol> [options]")
        print("Options:")
        print("  --debug          Enable debug output")
        print("  --max N          Maximum results (default: 10)")
        print("\nExamples:")
        print("  python get_similar_symbols.py llk_math_exp")
        print("  python get_similar_symbols.py Buffer --debug")
        sys.exit(1)
    
    # Parse arguments
    args = sys.argv[1:]
    debug = False
    max_results = 10
    symbol = None
    
    i = 0
    while i < len(args):
        if args[i] == '--debug':
            debug = True
        elif args[i] == '--max' and i + 1 < len(args):
            max_results = int(args[i + 1])
            i += 1
        elif not args[i].startswith('--'):
            symbol = args[i]
        i += 1
    
    # Run diagnostic if requested
    
    # Check if symbol provided
    if not symbol:
        print("Error: No symbol provided")
        sys.exit(1)
    
    # Run search
    print(f"Searching for symbols similar to: '{symbol}'")
    if debug:
        print("Debug mode enabled\n")
    
    result = find_similar_symbols(symbol, max_results, debug=debug)
    
    # Print results
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()