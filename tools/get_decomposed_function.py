#!/usr/bin/env python3
"""
Function Decomposer - Outputs all functions in dependency order, original form.
"""

import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import defaultdict, OrderedDict
from dataclasses import dataclass, field
import tempfile

from api_database_tools.api_extractors.tree_sitter_backend import parse_file, query

@dataclass
class FunctionCall:
    """Represents a function call found in code."""
    name: str
    full_match: str
    start_pos: int
    end_pos: int
    qualified_name: Optional[str] = None
    template_params: Optional[str] = None
    is_macro_arg: bool = False

@dataclass
class FunctionInfo:
    """Information about a function."""
    name: str
    body: str
    dependencies: Set[str] = field(default_factory=set)
    depth_level: int = 0  # Distance from original function

@dataclass
class AnalysisResult:
    """Result of dependency analysis."""
    functions: OrderedDict[str, FunctionInfo] = field(default_factory=OrderedDict)
    original_function_name: str = ""
    missing_functions: Set[str] = field(default_factory=set)
    atomic_functions: Set[str] = field(default_factory=set)

class FunctionDecomposer:
    """Analyzes function dependencies and outputs them in dependency order."""
    
    def __init__(self, database_path: str):
        self.database_path = database_path
        self.database = None
        self.implementations = {}
        self.function_index = {}
        self._load_database()
        
    def _load_database(self):
        """Load the API database and build indices."""
        with open(self.database_path, 'r') as f:
            self.database = json.load(f)
        
        self.implementations = self.database.get("implementations", {})
        
        # Build comprehensive function index with all variants
        for api_key, api_info in self.database.get("apis", {}).items():
            if api_info["type"] in ["function", "template_function", "member_function"]:
                name = api_info["name"]
                
                # Index by original name
                self.function_index[name] = api_key
                
                # Generate and index all variants
                variants = self._build_name_variants(name)
                for variant in variants:
                    if variant not in self.function_index:
                        self.function_index[variant] = api_key
                
                # For template functions, also index without template suffix
                if '<' in name:
                    base_name = name[:name.index('<')]
                    self.function_index[base_name] = api_key
                    
                    # And all variants of the base name
                    base_variants = self._build_name_variants(base_name)
                    for variant in base_variants:
                        if variant not in self.function_index:
                            self.function_index[variant] = api_key
    
    def analyze_dependencies(self, 
                           file_path: str, 
                           function_name: str) -> AnalysisResult:
        """Analyze all dependencies starting from the given function."""
        # Find the initial function
        original_code = self.find_function_in_file(file_path, function_name)
        
        if not original_code:
            # Try looking in the database
            impl = self._find_implementation(function_name)
            if impl:
                original_code = impl
            else:
                result = AnalysisResult()
                result.original_function_name = function_name
                result.missing_functions.add(function_name)
                return result
        
        # Create result
        result = AnalysisResult()
        result.original_function_name = function_name
        
        # Recursively analyze dependencies
        visited = set()
        self._analyze_function_recursive(function_name, original_code, result, visited, 0)
        
        # Reorder functions by dependency (dependencies first)
        ordered_functions = self._topological_sort(result.functions)
        result.functions = ordered_functions
        
        return result
    
    def _analyze_function_recursive(self,
                                  func_name: str,
                                  func_body: str,
                                  result: Result,
                                  visited: Set[str],
                                  depth: int):
        """Recursively analyze a function and its dependencies."""
        if func_name in visited:
            return
        
        visited.add(func_name)
        
        # Create function info
        func_info = FunctionInfo(
            name=func_name,
            body=func_body,
            depth_level=depth
        )
        
        # Find all calls in this function
        calls = self._find_all_calls_in_code(func_body)
        
        # Process each call
        for call in calls:
            
            # Add as dependency
            func_info.dependencies.add(call.name)
            
            # Find implementation
            impl = self._find_implementation(call.name)
            
            if impl:
                # Recursively analyze this dependency
                self._analyze_function_recursive(call.name, impl, result, visited, depth + 1)
            else:
                result.missing_functions.add(call.name)
        
        # Add this function to results
        result.functions[func_name] = func_info
    
    def _topological_sort(self, functions: Dict[str, FunctionInfo]) -> OrderedDict[str, FunctionInfo]:
        """Sort functions so dependencies come before functions that use them."""
        # Build adjacency list (reverse dependencies)
        dependents = defaultdict(set)
        in_degree = defaultdict(int)
        
        for func_name, func_info in functions.items():
            in_degree[func_name] = len(func_info.dependencies)
            for dep in func_info.dependencies:
                if dep in functions:  # Only count dependencies we have
                    dependents[dep].add(func_name)
        
        # Find all nodes with no dependencies
        queue = [func for func in functions if in_degree[func] == 0]
        ordered = OrderedDict()
        
        while queue:
            # Sort queue by depth level and name for consistent ordering
            queue.sort(key=lambda f: (-functions[f].depth_level, f))
            current = queue.pop(0)
            
            # Add to ordered list
            ordered[current] = functions[current]
            
            # Reduce in-degree for all dependents
            for dependent in dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        # Add any remaining functions (cycles) at the end
        for func_name, func_info in functions.items():
            if func_name not in ordered:
                ordered[func_name] = func_info
        
        return ordered
    
    def _find_all_calls_in_code(self, code: str) -> List[FunctionCall]:
        """Find all function calls in the given code."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        calls = []
        
        try:
            tree_id = parse_file(temp_path)
            
            # Simple query for all call expressions
            call_query = "(call_expression) @call"
            
            results = query(tree_id, call_query)
            
            for result in results:
                call_start, call_end = result['byte_range']
                call_text = code[call_start:call_end]
                
                # Extract function name from the call text
                # Updated regex to handle template parameters
                import re
                match = re.match(r'((?:\w+::)*\w+)(?:<[^>]+>)?\s*\(', call_text)
                if match:
                    func_name = match.group(1)
                    
                    # Skip control structures but NOT MATH (we want to analyze MATH calls)
                    if func_name not in ['if', 'while', 'for', 'switch', 'return', 'sizeof', 
                                    'static_cast', 'dynamic_cast', 'reinterpret_cast', 
                                    'const_cast']:  # Removed 'MATH' from here
                        calls.append(FunctionCall(
                            name=func_name,
                            full_match=call_text,
                            start_pos=call_start,
                            end_pos=call_end,
                            template_params=None,
                            is_macro_arg=False
                        ))
        finally:
            import os
            os.unlink(temp_path)
        
        return calls
    
    def find_function_in_file(self, file_path: str, function_name: str) -> Optional[str]:
        """Find a function implementation in a specific file."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
            
            # Simple regex to find function definition
            pattern = rf'(?:inline\s+)?(?:void|int|auto|ALWI)\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{'
            match = re.search(pattern, content)
            
            if match:
                # Extract the full function body
                start = match.start()
                brace_count = 0
                i = content.find('{', start)
                end = i
                
                while i < len(content):
                    if content[i] == '{':
                        brace_count += 1
                    elif content[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end = i + 1
                            break
                    i += 1
                
                return content[start:end]
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
        
        return None
    
    def _build_name_variants(self, name: str) -> List[str]:
        """Generate all possible variants of a function name for lookup."""
        variants = [name]
        
        # Handle namespace separators (:: vs _)
        if '::' in name:
            # Try with underscores
            variants.append(name.replace('::', '_'))
            
            # Try just the last component
            parts = name.split('::')
            variants.append(parts[-1])
            
            # Try joining with single underscore
            variants.append('_'.join(parts))
        elif '_' in name:
            # Try with :: at various positions
            parts = name.split('_')
            
            # Try different namespace splits
            for i in range(1, len(parts)):
                namespace = '_'.join(parts[:i])
                func = '_'.join(parts[i:])
                variants.append(f"{namespace}::{func}")
        
        return variants
    
    def _find_implementation(self, function_name: str) -> Optional[str]:
        """Find the implementation of a function using name variants."""
        # Generate all possible name variants
        variants = self._build_name_variants(function_name)
        
        # Try each variant
        for variant in variants:
            if variant in self.function_index:
                api_key = self.function_index[variant]
                if api_key in self.implementations:
                    return self.implementations[api_key]["code"]
        
        return None
    
    def format_output(self, result: Result, include_comments: bool = False) -> str:
        """Format the analysis result as requested."""
        output = []
        
        # Output each function in dependency order
        for func_name, func_info in result.functions.items():
            # Skip the original function for now
            if func_name == result.original_function_name:
                continue
            
            # Add comment about why this function is included
            if include_comments:
                if func_info.dependencies:
                    deps_list = ", ".join(sorted(func_info.dependencies))
                    output.append(f"// Used by: functions that depend on {func_name}")
                else:
                    output.append(f"// Leaf function (no dependencies)")
            
            # Output the function
            output.append(func_info.body)
            output.append("")  # Blank line
        
        # Output the original function last
        if result.original_function_name in result.functions:
            if include_comments:
                output.append("// Original function")
            output.append(result.functions[result.original_function_name].body)
        
        # Add summary at the end
        if include_comments:
            output.append("\n/*")
            output.append(f"Dependency Analysis Summary:")
            output.append(f"  Total functions: {len(result.functions)}")
            output.append(f"  Maximum depth: {max((f.depth_level for f in result.functions.values()), default=0)}")
            
            if result.atomic_functions:
                output.append(f"  Atomic functions called: {len(result.atomic_functions)}")
                for func in sorted(result.atomic_functions)[:10]:
                    output.append(f"    - {func}")
                if len(result.atomic_functions) > 10:
                    output.append(f"    ... and {len(result.atomic_functions) - 10} more")
            
            if result.missing_functions:
                output.append(f"  Missing implementations: {len(result.missing_functions)}")
                for func in sorted(result.missing_functions)[:5]:
                    output.append(f"    - {func}")
            
            output.append("*/")
        
        return '\n'.join(output)

async def decompose_function(file_path: str, function_name: str, database_path: str) -> Dict[str, Any]:
    """Async wrapper for function decomposition."""
    try:
        analyzer = FunctionDecomposer(database_path)
        result = analyzer.analyze_dependencies(file_path, function_name)
        
        # Format the output
        output = analyzer.format_output(result)
        
        return {
            "function": function_name,
            "file": file_path,
            "total_functions": len(result.functions),
            "missing_functions": list(result.missing_functions),
            "decomposed_code": output
        }
    except Exception as e:
        return {
            "error": str(e),
            "function": function_name,
            "file": file_path
        }

def main():
    parser = argparse.ArgumentParser(
        description="Analyze function dependencies and output in dependency order"
    )
    
    parser.add_argument("--database", help="Path to the API database JSON file", default = './api_impl_db.json')
    parser.add_argument("--file", help="Source file containing the function")
    parser.add_argument("--function", help="Function name to analyze")
    parser.add_argument("--output", help="Output file for dependency-ordered code")
    parser.add_argument("--comments", help="Display comments explaining the dependency scope of the function", action="store_true")
    
    args = parser.parse_args()
    
    # Create analyzer
    analyzer = FunctionDecomposer(args.database, args.comments)
    
    # Perform analysis
    print(f"\nAnalyzing dependencies for '{args.function}' from {args.file}")
    
    result = analyzer.analyze_dependencies(
        args.file,
        args.function
    )
    
    # Format output
    output = analyzer.format_output(result, args.comments)
    
    # Output the result
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"\nOutput written to: {args.output}")
    else:
        print("\n" + output)


if __name__ == "__main__":
    main()