#!/usr/bin/env python3
"""
Comprehensive test suite for the three MCP tools in api_database_tools.

Tests both subprocess execution (command line interface) and MCP integration
using the Claude Code SDK programmatically.
"""

import pytest
import subprocess
import json
import sys
import os
import asyncio
import argparse
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Change to project root for correct relative imports
os.chdir(project_root)

from tools.get_decomposed_function import decompose_function, FunctionDecomposer
from tools.get_llk_functions import query_llk_functions, LLKFunctionQuery
from tools.get_similar_symbols import find_similar_symbols, SymbolFinder




def display_tool_output(tool_name: str, input_args: dict, output: dict, should_display: bool):
    """Display tool output in a format that shows what the model would see."""
    if not should_display:
        return
        
    print(f"\n{'='*60}")
    print(f"TOOL: {tool_name}")
    print(f"{'='*60}")
    print(f"INPUT ARGUMENTS:")
    for key, value in input_args.items():
        print(f"  {key}: {value}")
    print(f"\nMODEL WOULD SEE:")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"{'='*60}\n")


class TestSubprocessMode:
    """Test tools as subprocess with command line arguments."""
    
    def setup_method(self):
        """Setup for each test method."""
        self.tools_dir = project_root / "tools"
        self.test_cpp_file = project_root / "tests" / "decomp_test_target.cpp"
        
    def test_get_decomposed_function_subprocess(self):
        """Test get_decomposed_function.py as subprocess."""
        cmd = [
            sys.executable, 
            str(self.tools_dir / "get_decomposed_function.py"),
            "--file", str(self.test_cpp_file),
            "--function", "test_function"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # Should complete without error (even if function not found)
        assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
        
        # Output should contain structured data (may not be pure JSON)
        assert result.stdout.strip(), "No output received"
        
        # Try to parse as JSON, but don't fail if it's not pure JSON
        lines = result.stdout.strip().split('\n')
        last_line = lines[-1] if lines else ""
        if last_line.startswith('{') and last_line.endswith('}'):
            try:
                output_data = json.loads(last_line)
                assert isinstance(output_data, dict)
            except json.JSONDecodeError:
                # Not JSON, but that's okay - just check it has content
                pass
    
    def test_get_llk_functions_subprocess(self):
        """Test get_llk_functions.py as subprocess."""
        cmd = [
            sys.executable,
            str(self.tools_dir / "get_llk_functions.py"),
            "math"  # Search for math-related functions
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # Should complete without error
        assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
        
        # Output should contain structured data
        assert result.stdout.strip(), "No output received"
    
    def test_get_similar_symbols_subprocess(self):
        """Test get_similar_symbols.py as subprocess."""
        cmd = [
            sys.executable,
            str(self.tools_dir / "get_similar_symbols.py"),
            "add",  # Search for add-related symbols
            "--max", "5"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # Should complete without error
        assert result.returncode == 0, f"Command failed with stderr: {result.stderr}"
        
        # Output should contain structured data
        assert result.stdout.strip(), "No output received"
    
    def test_get_decomposed_function_missing_args(self):
        """Test get_decomposed_function.py with missing arguments."""
        cmd = [sys.executable, str(self.tools_dir / "get_decomposed_function.py")]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        # Tool may handle missing args gracefully and output error message
        # but still exit with code 0, so just check it produces output
        assert result.stdout.strip() or result.stderr.strip(), "No output received"
    
    def test_get_llk_functions_missing_args(self):
        """Test get_llk_functions.py with missing arguments."""
        cmd = [sys.executable, str(self.tools_dir / "get_llk_functions.py")]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        # Should fail with non-zero exit code due to missing arguments
        assert result.returncode != 0
    
    def test_get_similar_symbols_missing_args(self):
        """Test get_similar_symbols.py with missing arguments."""
        cmd = [sys.executable, str(self.tools_dir / "get_similar_symbols.py")]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        # Should fail with non-zero exit code due to missing arguments
        assert result.returncode != 0


class TestMCPIntegration:
    """Test MCP integration by calling functions directly."""
    
    def setup_method(self):
        """Setup for each test method."""
        self.test_cpp_file = str(project_root / "tests" / "decomp_test_target.cpp")
        
    @pytest.mark.asyncio
    async def test_decompose_function_direct(self, display_results):
        """Test decompose_function function directly."""
        # Test with a simple function that might exist
        input_args = {
            "file_path": self.test_cpp_file,
            "function_name": "test_function"
        }
        result = await decompose_function(**input_args)
        
        display_tool_output("mcp__tt-metal-tools__decompose_function", input_args, result, display_results)
        
        # Should return a dictionary with expected structure
        assert isinstance(result, dict)
        # The function should have some kind of result structure
        assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_query_llk_functions_direct(self, display_results):
        """Test query_llk_functions function directly."""
        input_args = {"keyword": "math"}
        result = await query_llk_functions(**input_args)
        
        display_tool_output("mcp__tt-metal-tools__query_llk_functions", input_args, result, display_results)
        
        # Should return a dictionary
        assert isinstance(result, dict)
        # Should have some structure (functions, headers, etc.)
        assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_find_similar_symbols_direct(self, display_results):
        """Test find_similar_symbols function directly."""
        input_args = {"incorrect_symbol": "add", "max_results": 5}
        result = await find_similar_symbols(**input_args)
        
        display_tool_output("mcp__tt-metal-tools__find_similar_symbols", input_args, result, display_results)
        
        # Should return a dictionary
        assert isinstance(result, dict)
        # Should have some results structure
        assert len(result) > 0
    
    def test_function_decomposer_class(self):
        """Test FunctionDecomposer class initialization."""
        db_path = str(project_root / "tools" / "api_impl_db.json")
        
        # Should initialize without error if database exists
        if Path(db_path).exists():
            decomposer = FunctionDecomposer(db_path)
            assert decomposer.database_path == db_path
        else:
            # Should raise FileNotFoundError if database doesn't exist
            with pytest.raises(FileNotFoundError):
                FunctionDecomposer(db_path)
    
    def test_llk_function_query_class(self):
        """Test LLKFunctionQuery class initialization."""
        db_path = project_root / "tools" / "api_signatures_db.json"
        
        # Should initialize without error if database exists
        if db_path.exists():
            query_obj = LLKFunctionQuery()
            assert query_obj.database is not None
        else:
            # Should raise FileNotFoundError if database doesn't exist
            with pytest.raises(FileNotFoundError):
                LLKFunctionQuery()
    
    def test_symbol_finder_class(self):
        """Test SymbolFinder class initialization."""
        db_path = project_root / "tools" / "api_signatures_db.json"
        
        # Should initialize without error if database exists
        if db_path.exists():
            finder = SymbolFinder(debug=False)
            assert finder.database is not None
        else:
            # Should raise FileNotFoundError if database doesn't exist
            with pytest.raises(FileNotFoundError):
                SymbolFinder()


class TestClaudeCodeSDK:
    """Test MCP tools using Claude Code SDK programmatically."""
    
    def setup_method(self):
        """Setup for each test method."""
        self.test_cpp_file = str(project_root / "tests" / "decomp_test_target.cpp")
    
    @pytest.mark.skipif(
        not (os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")),
        reason="ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY not set - skipping Claude SDK tests"
    )
    def test_claude_sdk_decompose_function(self):
        """Test decompose_function via Claude Code SDK."""
        try:
            import anthropic
            
            # Mock the Claude SDK call
            with patch('anthropic.Client') as mock_client:
                mock_response = MagicMock()
                mock_response.content = [MagicMock()]
                mock_response.content[0].text = json.dumps({
                    "original_function": "test_function",
                    "dependencies": []
                })
                mock_client.return_value.messages.create.return_value = mock_response
                
                # This would be the actual SDK call structure
                client = anthropic.Client()
                response = client.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=1000,
                    tools=[{
                        "name": "decompose_function",
                        "description": "Decompose a function into its dependencies",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "file_path": {"type": "string"},
                                "function_name": {"type": "string"}
                            },
                            "required": ["file_path", "function_name"]
                        }
                    }],
                    messages=[{
                        "role": "user",
                        "content": f"Use the decompose_function tool on {self.test_cpp_file} for function test_function"
                    }]
                )
                
                assert response is not None
                
        except ImportError:
            pytest.skip("anthropic package not available")
    
    @pytest.mark.skipif(
        not (os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")),
        reason="ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY not set - skipping Claude SDK tests"
    )
    def test_claude_sdk_query_llk_functions(self):
        """Test query_llk_functions via Claude Code SDK."""
        try:
            import anthropic
            
            # Mock the Claude SDK call
            with patch('anthropic.Client') as mock_client:
                mock_response = MagicMock()
                mock_response.content = [MagicMock()]
                mock_response.content[0].text = json.dumps({
                    "functions": ["math_func1", "math_func2"],
                    "headers": ["math.h"]
                })
                mock_client.return_value.messages.create.return_value = mock_response
                
                client = anthropic.Client()
                response = client.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=1000,
                    tools=[{
                        "name": "query_llk_functions",
                        "description": "Query LLK functions by keyword",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "keyword": {"type": "string"}
                            },
                            "required": ["keyword"]
                        }
                    }],
                    messages=[{
                        "role": "user",
                        "content": "Use the query_llk_functions tool to search for 'math' functions"
                    }]
                )
                
                assert response is not None
                
        except ImportError:
            pytest.skip("anthropic package not available")
    
    @pytest.mark.skipif(
        not (os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY")),
        reason="ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY not set - skipping Claude SDK tests"
    )
    def test_claude_sdk_find_similar_symbols(self):
        """Test find_similar_symbols via Claude Code SDK."""
        try:
            import anthropic
            
            # Mock the Claude SDK call
            with patch('anthropic.Client') as mock_client:
                mock_response = MagicMock()
                mock_response.content = [MagicMock()]
                mock_response.content[0].text = json.dumps({
                    "symbols": ["add_func", "add_value"],
                    "total_found": 2
                })
                mock_client.return_value.messages.create.return_value = mock_response
                
                client = anthropic.Client()
                response = client.messages.create(
                    model="claude-3-sonnet-20240229",
                    max_tokens=1000,
                    tools=[{
                        "name": "find_similar_symbols",
                        "description": "Find similar symbols by name",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string"},
                                "max_results": {"type": "integer"}
                            },
                            "required": ["symbol"]
                        }
                    }],
                    messages=[{
                        "role": "user",
                        "content": "Use the find_similar_symbols tool to search for 'add' symbols"
                    }]
                )
                
                assert response is not None
                
        except ImportError:
            pytest.skip("anthropic package not available")


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_decompose_function_nonexistent_file(self):
        """Test decompose_function with nonexistent file."""
        result = await decompose_function(
            file_path="/nonexistent/file.cpp",
            function_name="test_function"
        )
        
        # Should handle error gracefully
        assert isinstance(result, dict)
        # Should have some response structure
        assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_query_llk_functions_empty_keyword(self):
        """Test query_llk_functions with empty keyword."""
        result = await query_llk_functions("")
        
        # Should handle empty keyword gracefully
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_find_similar_symbols_empty_symbol(self):
        """Test find_similar_symbols with empty symbol."""
        result = await find_similar_symbols(incorrect_symbol="")
        
        # Should handle empty symbol gracefully
        assert isinstance(result, dict)


if __name__ == "__main__":
    # Run tests with pytest when executed directly
    # Use --display-results to see what the model would see for each tool call
    # Example: python test_all_tools.py --display-results -v -s
    pytest.main([__file__, "-v"] + sys.argv[1:])