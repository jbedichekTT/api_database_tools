# TT-Metal API Analysis Tools

A comprehensive toolkit for analyzing and querying the TT-Metal API codebase using tree-sitter for general code parsing and analysis. This project provides both database generation tools and query interfaces exposed through an MCP (Model Context Protocol) server.

## Overview

This project consists of three main components:

1. **Database Generators** - Build comprehensive databases of API signatures and implementations
2. **Analysis Tools** - Query and analyze functions, find dependencies, and search for similar symbols
3. **MCP Server** - Expose the tools through a standardized protocol for integration with AI assistants

## What is Tree-sitter?

Tree-sitter is a parser generator tool and incremental parsing library that builds concrete syntax trees for source code. Unlike regular expressions or simple text parsing, tree-sitter understands the actual structure of code.

### Tree-sitter Basics

When you feed code to tree-sitter, it produces an Abstract Syntax Tree (AST). For example, this C++ code:

```cpp
int add(int a, int b) {
    return a + b;
}
```

Gets parsed into a tree structure where tree-sitter identifies:
- `function_definition` node
- `primitive_type` node for "int"
- `function_declarator` node containing the function name and parameters
- `compound_statement` node for the function body
- etc.

This allows us to query code structurally rather than textually. Instead of using regex to find function definitions (error-prone), we can query for all `function_definition` nodes.

### Tree-sitter in This Project

We use tree-sitter to:
1. Parse C++ header and source files
2. Extract function declarations, definitions, classes, enums, etc.
3. Analyze function dependencies by finding all `call_expression` nodes
4. Build comprehensive API databases with accurate signatures

## Database Types

### 1. API Signatures Database (`api_signatures_db.json`)

Contains function signatures, parameter types, and metadata for all APIs in the codebase.

**Example Entry:**
```json
"function::CreateSemaphore#b6c82da5": {
  "base_key": "function::CreateSemaphore",
  "header": "api/tt-metalium/program.hpp",
  "is_template": false,
  "key": "function::CreateSemaphore#b6c82da5",
  "name": "CreateSemaphore",
  "param_types": [
    "Program&",
    "const std::variant<CoreRange, CoreRangeSet>&",
    "uint32_t",
    "CoreType"
  ],
  "parameters": "( Program& program, const std::variant<CoreRange, CoreRangeSet>& core_spec, uint32_t initial_value, CoreType core_type)",
  "signature": "friend uint32_t CreateSemaphore( Program& program, const std::variant<CoreRange, CoreRangeSet>& core_spec, uint32_t initial_value, CoreType core_type)",
  "type": "function"
}
```

The hash suffix (`#b6c82da5`) handles function overloads - multiple functions with the same name but different signatures.

### 2. API Implementations Database (`api_impl_db.json`)

Contains the actual implementation code for functions, not just their signatures.

**Example Entry:**
```json
"function::DataMovementKernel#b46e2749": {
  "code": "DataMovementKernel(const KernelSource& kernel_src, const CoreRangeSet& cr_set, const DataMovementConfig& config) :\n        KernelImpl(kernel_src, cr_set, config.compile_args, config.defines), config_(config) {\n        this->dispatch_class_ =\n            magic_enum::enum_integer(HalProcessorClassType::DM) + magic_enum::enum_integer(config.processor);\n    }\n",
  "extracted_at": "2025-07-28 21:41:34",
  "location": "impl/kernels/kernel_impl.hpp"
}
```

## Project Structure

### Core Components

#### `api_extractors/tree_sitter_backend.py`
The foundation of the parsing system. This module:
- Manages tree-sitter parser initialization
- Builds the C++ grammar if needed
- Provides functions to parse files and run queries
- Caches parsed trees for efficiency
- Handles the tree-sitter query language

Key functions:
- `parse_file()` - Parse a C++ file and return a tree ID
- `query()` - Run a tree-sitter query against a parsed tree
- `replace_span()` - Modify code and reparse

#### `api_extractors/definition_extractor.py`
Extracts API signatures from headers using tree-sitter. It:
- Finds all function declarations, classes, structs, enums
- Handles templates, member functions, overloads
- Builds a complete API signature database

The extraction process:
1. Parse file with tree-sitter
2. Query for all declaration types
3. Build context map (track namespaces/classes)
4. Classify each node and extract relevant info
5. Post-process to remove duplicates

#### `api_extractors/definition_extractor_impl.py`
Extended version that also captures function implementations:
- Includes everything from `definition_extractor.py`
- Additionally stores the full function body
- Links declarations with their implementations
- Enables dependency analysis

### Database Generators

#### `db_generation/build_api_signature_db.py`
Builds the signatures database by:
1. Scanning specified directories for C++/header files
2. Extracting all API signatures using tree-sitter
3. Creating unique keys for overloaded functions
4. Building namespace indices
5. Adding common STL APIs
6. Saving as JSON with metadata

#### `db_generation/build_api_impl_db.py`
Builds the implementations database by:
1. Using the enhanced extractor to get function bodies
2. Linking declarations with implementations across files
3. Storing complete implementation code
4. Tracking where each implementation was found

### Analysis Tools

#### `tools/get_decomposed_function.py`
Analyzes function dependencies and outputs all required functions in dependency order.

How it works:
1. Find the target function implementation
2. Parse it with tree-sitter to find all `call_expression` nodes
3. For each called function, find its implementation
4. Recursively analyze dependencies
5. Output functions in topological order (dependencies first)

Example usage:
```bash
python get_decomposed_function.py --file kernel.cpp --function compute_kernel --database api_impl_db.json
```

#### `tools/get_llk_functions.py`
Searches for Low-Level Kernel (LLK) functions by keyword.

Features:
- Searches only in specific paths (e.g., `hw/ckernels/wormhole_b0/metal/llk_api`)
- Case-insensitive substring matching
- Groups results by header file
- Provides normalized include statements

Example query for "exp" functions:
```json
{
  "keyword": "exp",
  "headers": [
    {
      "include": "#include <llk_api/llk_sfpu_exp.h>",
      "signatures": [
        "void llk_math_exp_init()",
        "void llk_math_exp(uint dst_index)"
      ]
    }
  ]
}
```

#### `tools/get_similar_symbols.py`
Finds symbols similar to a potentially misspelled or incorrect symbol name.

Similarity algorithm:
- Exact match: score 1.0
- Substring match: score 0.7-0.9
- Character overlap: score based on matching characters

Useful for:
- Finding the correct function name when you have a typo
- Discovering related functions
- Exploring available APIs

### MCP Server

#### `server.py`
Exposes all tools through the Model Context Protocol:
- Lists available tools
- Handles tool invocations
- Returns results as JSON
- Manages async execution

Available tools:
1. `decompose_function` - Analyze function dependencies
2. `query_llk_functions` - Search for LLK functions
3. `find_similar_symbols` - Find similar symbol names

## Usage

### Building the Databases

1. Generate the signatures database:
```bash
python db_generation/build_api_signature_db.py --tt-metal-path /path/to/tt-metal --output api_signatures_db.json
```

2. Generate the implementations database:
```bash
python db_generation/build_api_impl_db.py --tt-metal-path /path/to/tt-metal --output api_impl_db.json
```

### Using the Tools

1. Query LLK functions:
```bash
python tools/get_llk_functions.py exp
```

2. Find similar symbols:
```bash
python tools/get_similar_symbols.py DataMovmentKernel --max 5
```

3. Decompose a function:
```bash
python tools/get_decomposed_function.py --file kernel.cpp --function my_kernel --comments
```

### Running the MCP Server

```bash
python server.py
```

The server will expose all tools through the MCP protocol for integration with AI assistants.

## Requirements

- Python 3.8+
- tree-sitter
- tree-sitter-cpp (C++ grammar)
- mcp (for the server)

Install with:
```bash
pip install -r requirements.txt
```

## How Tree-sitter Queries Work

Tree-sitter uses a Lisp-like query language. For example:

```lisp
(function_definition
  type: (_) @return_type
  declarator: (function_declarator
    declarator: (identifier) @function_name
    parameters: (parameter_list) @params
  )
) @function
```

This query:
1. Matches `function_definition` nodes
2. Captures the return type as `@return_type`
3. Captures the function name as `@function_name`
4. Captures the parameter list as `@params`
5. Captures the entire function as `@function`

The results include the matched text and byte ranges, allowing precise code extraction.


