#!/usr/bin/env python3
"""
Build a comprehensive database of API signatures for validation purposes.
Uses enhanced extraction to capture ALL APIs.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, List, Set, Optional
from collections import defaultdict
import hashlib

from api_database_tools.api_extractors.definition_extractor import (
    extract_apis_from_header,
    extract_member_functions
)

from api_database_tools.api_extractors.tree_sitter_backend import parse_file, query

class APISignatureDatabase:
    """Database containing full API signatures for validation."""
    
    def __init__(self, tt_metal_path: str = None):
        self.tt_metal_path = Path(tt_metal_path or os.environ.get("TT_METAL_HOME", "/home/user/tt-metal"))
        self.database = {
            "metadata": {
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "tt_metal_path": str(self.tt_metal_path),
                "version": "2.0",  # Enhanced version
                "description": "Comprehensive API signatures database"
            },
            "apis": {},
            "headers": {},
            "namespaces": defaultdict(list),
        }
        # Track what we've seen to avoid duplicates
        self.seen_apis = set()
        
    def build_database(self, scan_dirs: List[str] = None):
        """Build the database by scanning header files."""
        if scan_dirs is None:
            scan_dirs = [
                "ttnn",
                "tt_metal"
                #"tt_metal/api/"
            ]
        
        print(f"Building Enhanced API Signatures Database")
        print(f"Scanning directories: {scan_dirs}")
        print("=" * 80)
        
        # Step 1: Find all header files
        all_headers = self._find_all_files(scan_dirs)
        
        # Step 2: Extract and store APIs
        self._extract_and_store_signatures(all_headers)
        
        # Step 3: Build indices
        self._build_indices()
        
        # Step 4: Add common STL APIs
        self._add_standard_library_apis()
        
        print(f"\nDatabase built successfully!")
        print(f"Total headers analyzed: {len(self.database['headers'])}")
        print(f"Total unique APIs found: {len(self.database['apis'])}")
        
    def _find_all_files(self, scan_dirs: List[str]) -> List[Path]:
        """Find all header and source files."""
        all_files = []
        
        for scan_dir in scan_dirs:
            dir_path = self.tt_metal_path / scan_dir
            
            if not dir_path.exists():
                print(f"  Warning: Directory not found: {dir_path}")
                continue
                
            print(f"  Scanning {scan_dir}...")
            
            # Find header and source files
            extensions = ["*.hpp", "*.h", "*.cpp", "*.cc"]
            files = []
            for ext in extensions:
                files.extend(dir_path.rglob(ext))
            
            # Filter out test and example files
            skip_patterns = [
                "/tests/", "/test/", "/testing/",
                "/examples/", "/programming_examples/",
                "/tracy/", "/build/",
                "_test.", "test_"
            ]
            
            filtered_files = []
            for file in files:
                file_str = str(file)
                if not any(pattern in file_str for pattern in skip_patterns):
                    filtered_files.append(file)
                    
            all_files.extend(filtered_files)
            print(f"    Found {len(filtered_files)} files")
                
        print(f"\nTotal files found: {len(all_files)}")
        return all_files
        
    def _extract_and_store_signatures(self, files: List[Path]):
        """Extract and store API signatures from files."""
        print(f"\nExtracting API signatures from {len(files)} files...")
        
        processed = 0
        errors = 0
        
        for file_path in files:
            processed += 1
            
            if processed % 100 == 0:
                print(f"  Processed {processed}/{len(files)} files...")
            
            # Get the include path
            include_path = self._get_include_path(file_path)
            if not include_path:
                continue
            
            try:
                # Extract APIs using the new universal extractor
                apis = extract_apis_from_header(str(file_path), str(self.tt_metal_path))
                
                if "error" in apis:
                    errors += 1
                    continue
                
                # Extract member functions
                member_funcs = extract_member_functions(str(file_path), str(self.tt_metal_path))
                
                # Store all extracted APIs
                header_apis = []
                
                # Process functions
                try:
                    func_declarations = extract_function_declarations(str(file_path))
                    for func_data in func_declarations:
                        if 'name' in func_data:
                            # Build signature from components
                            signature = f"{func_data.get('return_type', 'void')} {func_data['name']}{func_data.get('parameters', '()')}"
                            
                            api_entry = {
                                "name": func_data['name'],
                                "type": "function" if not func_data.get('is_template') else "template_function",
                                "signature": signature,
                                "header": include_path,
                                "key": f"function::{func_data['name']}",
                                "parameters": func_data.get('parameters', '()'),
                                "param_types": func_data.get('param_types', []),
                                "return_type": func_data.get('return_type', 'void'),
                                "is_template": func_data.get('is_template', False)
                            }
                            
                            if self._store_api(api_entry):
                                header_apis.append(api_entry["key"])
                except Exception as e:
                    print(f"  Tree-sitter extraction failed: {e}")

                # Also use the original regex-based extraction as fallback
                # This ensures we don't miss functions that tree-sitter couldn't parse
                for func_sig in apis.get("functions", []):
                    # Check if we already have this function
                    func_name = self._extract_function_name(func_sig)
                    if func_name and f"function::{func_name}" not in self.seen_apis:
                        api_entry = self._create_api_entry(func_sig, "function", include_path)
                        if api_entry and self._store_api(api_entry):
                            header_apis.append(api_entry["key"])
                
                # Process template functions
                for func_sig in apis.get("template_functions", []):
                    api_entry = self._create_api_entry(func_sig, "template_function", include_path)
                    if api_entry and self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                
                # Process classes
                for class_name in apis.get("classes", []):
                    api_entry = self._create_type_entry(class_name, "class", include_path)
                    if api_entry and self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                
                # Process structs
                for struct_name in apis.get("structs", []):
                    api_entry = self._create_type_entry(struct_name, "struct", include_path)
                    if api_entry and self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                
                # Process enums
                for enum_name in apis.get("enums", []):
                    api_entry = self._create_type_entry(enum_name, "enum", include_path)
                    if api_entry and self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                
                # Process enum values (now directly from the main API extraction)
                for enum_value in apis.get("enum_values", []):
                    api_entry = self._create_enum_value_entry(enum_value, include_path)
                    if api_entry and self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                
                # Process member functions
                if isinstance(member_funcs, dict) and "error" not in member_funcs:
                    for class_name, methods in member_funcs.items():
                        for method in methods:
                            api_entry = self._create_member_function_entry(
                                class_name, method, include_path
                            )
                            if api_entry and self._store_api(api_entry):
                                header_apis.append(api_entry["key"])
                
                # Process methods from general extraction
                for method_name in apis.get("methods", []):
                    # Try to create a simple method entry
                    api_entry = {
                        "name": method_name,
                        "type": "method",
                        "signature": method_name,
                        "header": include_path,
                        "key": f"method::{method_name}"
                    }
                    if self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                
                # Process typedefs
                for typedef in apis.get("typedefs", []):
                    api_entry = {
                        "name": self._extract_typedef_name(typedef),
                        "type": "typedef",
                        "signature": typedef,
                        "header": include_path,
                        "key": f"typedef::{self._extract_typedef_name(typedef)}"
                    }
                    if api_entry["name"] and self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                
                # Process using declarations
                for using_decl in apis.get("usings", []):
                    api_entry = {
                        "name": self._extract_using_name(using_decl),
                        "type": "using",
                        "signature": using_decl,
                        "header": include_path,
                        "key": f"using::{self._extract_using_name(using_decl)}"
                    }
                    if api_entry["name"] and self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                
                # Process macros
                for macro in apis.get("macros", []):
                    api_entry = {
                        "name": macro.split('(')[0] if '(' in macro else macro,
                        "type": "macro",
                        "signature": macro,
                        "header": include_path,
                        "key": f"macro::{macro}"
                    }
                    if self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                
                # Process constants
                for constant in apis.get("constants", []):
                    api_entry = {
                        "name": self._extract_constant_name(constant),
                        "type": "constant",
                        "signature": constant,
                        "header": include_path,
                        "key": f"constant::{self._extract_constant_name(constant)}"
                    }
                    if api_entry["name"] and self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                
                # Store header's APIs
                if header_apis:
                    self.database["headers"][include_path] = header_apis
                    
            except Exception as e:
                print(f"\n  Error processing {file_path}: {str(e)}")
                errors += 1
                continue
                
        print(f"\nAPI extraction complete. Errors: {errors}")
    
    def _create_type_entry(self, type_name: str, type_kind: str, header: str) -> Optional[Dict]:
        """Create an API entry for a type (class/struct/enum)."""
        # Clean the name
        type_name = type_name.strip()
        if not type_name:
            return None
        
        return {
            "name": type_name,
            "type": type_kind,
            "signature": f"{type_kind} {type_name}",
            "header": header,
            "key": f"{type_kind}::{type_name}"
        }
    
    def _create_api_entry(self, signature: str, api_type: str, header: str) -> Optional[Dict]:
        """Create an API entry for a function."""
        # Extract function name
        func_name = self._extract_function_name(signature)
        if not func_name:
            return None
        
        # Clean signature
        signature = ' '.join(signature.split())
        
        # Extract parameters
        params = self._extract_parameters(signature)
        
        # Extract parameter types
        param_types = extract_parameter_types_from_text(params)  # NOT self._extract_parameter_types
        
        # Create entry with param_types
        return {
            "name": func_name,
            "type": api_type,
            "signature": signature,
            "header": header,
            "key": f"{api_type}::{func_name}",
            "parameters": params,
            "param_types": param_types,  # Make sure this is included
            "is_template": api_type == "template_function"
        }

    def _count_parameters(self, params: str) -> int:
        """Count the number of parameters in a parameter list."""
        if not params or params == '()':
            return 0
        
        # Remove outer parentheses
        params = params.strip('()')
        
        if params == 'void':
            return 0
        
        # Count commas at depth 0
        count = 1  # Start with 1 for the first parameter
        depth = 0
        
        for char in params:
            if char in '<([':
                depth += 1
            elif char in '>)]':
                depth -= 1
            elif char == ',' and depth == 0:
                count += 1
        
        return count
    
    def _create_parameter_key(self, params: str) -> str:
        """Create a simplified parameter signature for unique keys."""
        # Remove outer parentheses
        params = params.strip('()')
        
        if not params:
            return "()"
        
        # Parse parameters more carefully
        param_types = []
        current = []
        depth = 0
        
        for char in params:
            if char in '<([':
                depth += 1
            elif char in '>)]':
                depth -= 1
            elif char == ',' and depth == 0:
                param = ''.join(current).strip()
                # Extract just the type, not the parameter name
                param_type = self._extract_parameter_type_for_key(param)
                if param_type:
                    param_types.append(param_type)
                current = []
                continue
            current.append(char)
        
        # Don't forget the last parameter
        if current:
            param = ''.join(current).strip()
            param_type = self._extract_parameter_type_for_key(param)
            if param_type:
                param_types.append(param_type)
        
        # Create a simplified key
        return f"({','.join(param_types)})"

    def _extract_parameter_type_for_key(self, param: str) -> str:
        """Extract a simplified type for the key."""
        # Remove default values
        if '=' in param:
            param = param[:param.index('=')].strip()
        
        # For the key, we want a simplified version
        # Remove const, &, * but keep the core type
        param = param.replace('const ', '').replace('&', '').replace('*', '').strip()
        
        # If there's a space, the last word is likely the parameter name
        words = param.split()
        if len(words) > 1:
            # Remove the parameter name (last word if it starts with lowercase)
            if words[-1][0].islower():
                param = ' '.join(words[:-1])
        
        # Simplify common types
        if 'std::' in param:
            param = param.replace('std::', '')
        
        return param
    
    def _create_enum_value_entry(self, enum_value: str, header: str) -> Optional[Dict]:
        """Create an API entry for an enum value."""
        if not enum_value:
            return None
        
        # Extract the simple value name
        if '::' in enum_value:
            parts = enum_value.split('::')
            value_name = parts[-1]
        else:
            value_name = enum_value
        
        return {
            "name": value_name,
            "type": "enum_value",
            "signature": enum_value,
            "header": header,
            "key": f"enum_value::{enum_value}",
            "full_name": enum_value
        }
    
    def _create_member_function_entry(self, class_name: str, method_info: Dict, header: str) -> Optional[Dict]:
        """Create an API entry for a member function."""
        method_name = method_info.get('name')
        if not method_name:
            return None
        
        # Create a unique key including parameter signature to handle overloads
        params = method_info.get('params', '()')
        param_sig = params.replace(' ', '')
        key = f"member_function::{class_name}::{method_name}{param_sig}"
        
        return {
            "name": method_name,
            "type": "member_function",
            "signature": method_info.get('signature', f"{method_name}()"),
            "header": header,
            "class": class_name,
            "key": key,
            "return_type": method_info.get('return_type', ''),
            "parameters": params,
            "const": method_info.get('const', False),
            "defined_inside": method_info.get('defined_inside', False),
            "defined_outside": method_info.get('defined_outside', False)
        }
    
    def _store_api(self, api_entry: Dict) -> bool:
        """Store an API entry with unique hash for overloads."""
        base_key = api_entry["key"]
        
        # For functions and methods, create a unique key based on the full signature
        if api_entry["type"] in ["function", "template_function", "member_function", "method"]:
            # Create a hash of the signature to ensure uniqueness
            
            signature = api_entry.get("signature", "")
            sig_hash = hashlib.md5(signature.encode()).hexdigest()[:8]
            
            # Modify the key to include the hash
            api_entry["key"] = f"{base_key}#{sig_hash}"
            api_entry["base_key"] = base_key  # Store original key for searching
        
        key = api_entry["key"]
        
        # Always store (no duplicate checking for functions)
        if key not in self.database["apis"]:
            self.seen_apis.add(key)
            self.database["apis"][key] = api_entry
            return True
        
        return False
 
    def _extract_function_name(self, signature: str) -> str:
        """Extract function name from signature."""
        # Remove template prefix if present
        if signature.startswith("template"):
            signature = signature[signature.find('>') + 1:].strip()
        
        # Handle operator functions
        if "operator" in signature:
            import re
            match = re.search(r'operator\s*[^\s(]+', signature)
            if match:
                return match.group(0)
        
        # Remove return type and get function name
        if '(' in signature:
            before_params = signature.split('(')[0].strip()
            parts = before_params.split()
            if parts:
                # Handle qualified names (e.g., Class::method)
                name = parts[-1]
                # Handle destructors
                if '~' in name:
                    name = name[name.rfind('~'):]
                return name
        
        return ""
    
    def _extract_parameters(self, signature: str) -> str:
        """Extract parameter list from signature."""
        start = signature.find('(')
        end = signature.rfind(')')
        if start != -1 and end != -1:
            return signature[start:end+1]
        return "()"
    
    def _extract_typedef_name(self, typedef: str) -> str:
        """Extract name from typedef declaration."""
        # Simple extraction - last identifier before semicolon
        import re
        # Remove 'typedef' keyword
        if typedef.startswith('typedef'):
            typedef = typedef[7:].strip()
        # Find the last identifier
        match = re.search(r'(\w+)\s*;?\s*$', typedef)
        if match:
            return match.group(1)
        return ""
    
    def _extract_using_name(self, using_decl: str) -> str:
        """Extract name from using declaration."""
        import re
        # Handle 'using name = ...' or 'using namespace ...'
        if '=' in using_decl:
            match = re.search(r'using\s+(\w+)\s*=', using_decl)
        else:
            match = re.search(r'using\s+(?:namespace\s+)?(\w+)', using_decl)
        if match:
            return match.group(1)
        return ""
    
    def _extract_constant_name(self, constant: str) -> str:
        """Extract name from constant declaration."""
        import re
        # Look for common patterns like 'const type name' or 'constexpr type name'
        match = re.search(r'(?:const|constexpr)\s+\w+\s+(\w+)', constant)
        if match:
            return match.group(1)
        # Try to find any identifier that looks like a constant name
        words = constant.split()
        for word in reversed(words):
            if word.isidentifier() and not word in ['const', 'constexpr', 'static']:
                return word
        return ""
    
    def _get_include_path(self, file_path: Path) -> str:
        """Convert absolute path to include path."""
        try:
            # Try different base paths
            for base in ["ttnn/cpp", "tt_metal/include", "tt_metal", ""]:
                base_path = self.tt_metal_path / base if base else self.tt_metal_path
                try:
                    rel_path = file_path.relative_to(base_path)
                    include_path = str(rel_path)
                    
                    # Clean up the path
                    if include_path.startswith("ttnn/ttnn/"):
                        include_path = include_path[5:]
                    
                    return include_path
                except ValueError:
                    continue
            
            # Fallback
            return str(file_path.relative_to(self.tt_metal_path))
            
        except ValueError:
            return str(file_path.name)
    
    def _build_indices(self):
        """Build namespace and other indices."""
        for api_key, api_info in self.database["apis"].items():
            # Extract namespace from name
            name = api_info["name"]
            if '::' in name:
                namespace = '::'.join(name.split('::')[:-1])
            else:
                # Infer from header path
                header = api_info["header"]
                if header.startswith("ttnn/"):
                    namespace = "ttnn"
                elif header.startswith("tt_metal/"):
                    namespace = "tt_metal"
                else:
                    namespace = "global"
            
            self.database["namespaces"][namespace].append(api_key)
        
        # Convert defaultdict to regular dict
        self.database["namespaces"] = dict(self.database["namespaces"])
    
    def _add_standard_library_apis(self):
        """Add common standard library APIs."""
        std_apis = [
            # Common functions
            {"name": "move", "signature": "template<typename T> T&& move(T&& t)", "namespace": "std"},
            {"name": "forward", "signature": "template<typename T> T&& forward(T&& t)", "namespace": "std"},
            {"name": "max", "signature": "template<typename T> const T& max(const T& a, const T& b)", "namespace": "std"},
            {"name": "min", "signature": "template<typename T> const T& min(const T& a, const T& b)", "namespace": "std"},
            
            # Common template classes
            {"name": "vector", "signature": "template<typename T> class vector", "namespace": "std"},
            {"name": "optional", "signature": "template<typename T> class optional", "namespace": "std"},
            {"name": "unique_ptr", "signature": "template<typename T> class unique_ptr", "namespace": "std"},
        ]
        
        # Common methods that might be called
        common_methods = [
            {"name": "push_back", "signature": "void push_back(const T& value)", "class": "vector"},
            {"name": "size", "signature": "size_t size() const", "class": "container"},
            {"name": "empty", "signature": "bool empty() const", "class": "container"},
            {"name": "buffer_type", "signature": "BufferType buffer_type() const", "class": "Buffer"},
        ]
        
        for api in std_apis:
            key = f"std_library::{api['namespace']}::{api['name']}"
            self.database["apis"][key] = {
                "name": f"{api['namespace']}::{api['name']}",
                "type": "std_library",
                "signature": api["signature"],
                "namespace": api["namespace"],
                "header": "<standard_library>",
                "key": key
            }
        
        for method in common_methods:
            key = f"common_method::{method['name']}"
            self.database["apis"][key] = {
                "name": method["name"],
                "type": "method",
                "signature": method["signature"],
                "header": "<common>",
                "key": key,
                "class": method.get("class", "")
            }
    
    def save(self, output_file: str = "api_signatures_database.json"):
        """Save the database to a JSON file."""
        output_path = Path(output_file)
        
        # Update metadata
        self.database["metadata"]["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.database["metadata"]["total_apis"] = len(self.database["apis"])
        self.database["metadata"]["total_headers"] = len(self.database["headers"])
        
        with open(output_path, 'w') as f:
            json.dump(self.database, f, indent=2, sort_keys=True)
            
        print(f"\nDatabase saved to: {output_path}")
        
        # Save a summary
        self._save_summary(output_path.with_suffix('.txt'))
        
    def _save_summary(self, summary_path: Path):
        """Save a human-readable summary."""
        with open(summary_path, 'w') as f:
            f.write("Enhanced API Signatures Database Summary\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Created: {self.database['metadata']['created']}\n")
            f.write(f"Total APIs: {len(self.database['apis'])}\n")
            f.write(f"Total Headers: {len(self.database['headers'])}\n\n")
            
            # Count by type
            type_counts = defaultdict(int)
            for api_info in self.database["apis"].values():
                type_counts[api_info["type"]] += 1
            
            f.write("APIs by Type:\n")
            for api_type, count in sorted(type_counts.items()):
                f.write(f"  {api_type}: {count}\n")
            f.write("\n")
            
            # Show some examples of each type
            examples_by_type = defaultdict(list)
            for api_key, api_info in self.database["apis"].items():
                api_type = api_info["type"]
                if len(examples_by_type[api_type]) < 5:
                    examples_by_type[api_type].append(api_info)
            
            for api_type, examples in sorted(examples_by_type.items()):
                f.write(f"\nExample {api_type}s:\n")
                f.write("-" * 40 + "\n")
                for ex in examples:
                    f.write(f"  {ex['name']}\n")
                    if ex.get('signature'):
                        f.write(f"    Signature: {ex['signature']}\n")
                    f.write(f"    Header: {ex['header']}\n")

def extract_function_declarations(file_path: str) -> List[Dict]:
    """Extract ONLY function declarations, not usage."""
    
    tree_id = parse_file(file_path)
    
    # Query that explicitly excludes call_expression contexts
    declaration_only_query = """
    [
        ; Function declarations
        (declaration
            type: (_) @decl_type
            declarator: (function_declarator
                declarator: (_) @decl_name
                parameters: (parameter_list) @decl_params
            )
        ) @declaration_node
        
        ; Function definitions
        (function_definition
            type: (_) @def_type
            declarator: (function_declarator
                declarator: (_) @def_name
                parameters: (parameter_list) @def_params
            )
        ) @definition_node
        
        ; Member function declarations in classes
        (field_declaration
            type: (_) @member_type
            declarator: (function_declarator
                declarator: (_) @member_name
                parameters: (parameter_list) @member_params
            )
        ) @member_declaration
        
        ; Template function declarations
        (template_declaration
            (declaration
                type: (_) @template_decl_type
                declarator: (function_declarator
                    declarator: (_) @template_decl_name
                    parameters: (parameter_list) @template_decl_params
                )
            )
        ) @template_decl_node
        
        ; Template function definitions
        (template_declaration
            (function_definition
                type: (_) @template_def_type
                declarator: (function_declarator
                    declarator: (_) @template_def_name  
                    parameters: (parameter_list) @template_def_params
                )
            )
        ) @template_def_node
    ]
    """
    
    results = query(tree_id, declaration_only_query)
    
    # Process results
    functions = []
    seen_nodes = set()
    
    for result in results:
        # Skip if we've seen this byte range
        if result['byte_range'] in seen_nodes:
            continue
            
        node_type = result['name']
        
        # Only process the main declaration nodes
        if node_type in ['declaration_node', 'definition_node', 'member_declaration', 'template_decl_node', 'template_def_node']:
            seen_nodes.add(result['byte_range'])
            
            # Collect components for this declaration
            func_info = {
                'range': result['byte_range'],
                'is_template': 'template' in node_type
            }
            
            # Find associated components
            for component in results:
                # Must be within the declaration's range
                if (component['byte_range'][0] >= func_info['range'][0] and
                    component['byte_range'][1] <= func_info['range'][1]):
                    
                    comp_name = component['name']
                    if comp_name.endswith('_type'):
                        func_info['return_type'] = component['text']
                    elif comp_name.endswith('_name'):
                        func_info['name'] = component['text']
                    elif comp_name.endswith('_params'):
                        func_info['parameters'] = component['text']
            
            # Verify this is NOT inside a call_expression
            if not is_inside_call_expression(tree_id, func_info['range']):
                if 'name' in func_info and 'parameters' in func_info:
                    # Additional check: skip if this looks like a macro call
                    # Macros are typically all uppercase or have uppercase naming
                    func_name = func_info.get('name', '')
                    
                    # Skip if it's a likely macro (all uppercase)
                    if func_name.isupper() or (func_name and 
                        all(c.isupper() or c == '_' or c.isdigit() for c in func_name)):
                        continue
                    
                    # Skip if there's no return type (likely a macro or call)
                    if not func_info.get('return_type'):
                        # Unless it's a constructor/destructor
                        if not (func_name.startswith('~') or 
                                (func_info.get('is_template', False) and '::' in func_name)):
                            continue
                    
                    functions.append({
                        'name': func_info.get('name'),
                        'return_type': func_info.get('return_type', 'void'),
                        'parameters': func_info.get('parameters', '()'),
                        'param_types': extract_parameter_types_from_text(func_info.get('parameters', '()')),
                        'is_template': func_info.get('is_template', False),
                        'signature': f"{func_info.get('return_type', 'void')} {func_info.get('name')}{func_info.get('parameters', '()')}"
                    })
    
    return functions

def is_inside_call_expression(tree_id: str, node_range: tuple) -> bool:
    """Check if a node is inside a call_expression."""    
    # Find all call expressions
    call_query = "(call_expression) @call"
    call_results = query(tree_id, call_query)
    
    # Check if our node is inside any call expression
    node_start, node_end = node_range
    for call in call_results:
        call_start, call_end = call['byte_range']
        # If our node is inside this call expression
        if call_start <= node_start and node_end <= call_end:
            return True
    
    return False

def extract_parameter_types_from_ast(tree_id: str, params_node: Dict) -> List[str]:
    """Extract parameter types from a parameter list node."""    
    # Query for parameters within the parameter list
    param_query = """
    (parameter_list
        (parameter_declaration
            type: (_) @param_type
            declarator: (_)? @param_name
        ) @param
    )
    """
    
    results = query(tree_id, param_query)
    
    param_types = []
    # Filter to only parameters within our parameter list
    start, end = params_node['byte_range']
    
    for result in results:
        if result['name'] == 'param_type':
            r_start, r_end = result['byte_range']
            if r_start >= start and r_end <= end:
                param_types.append(result['text'])
    
    return param_types

def extract_parameter_types_from_list(tree_id: str, param_text: str, parent_range: tuple) -> List[str]:
    """Extract parameter types from a parameter list."""    
    # Query for parameter declarations within the parameter list
    param_query = """
    (parameter_list
        [
            (parameter_declaration
                type: (_) @param_type
                declarator: (_)? @param_declarator
            ) @param
            
            (optional_parameter_declaration
                type: (_) @opt_param_type
                declarator: (_)? @opt_param_declarator
            ) @opt_param
            
            (variadic_parameter_declaration) @variadic
        ]
    )
    """
    
    results = query(tree_id, param_query)
    
    param_types = []
    current_params = []
    
    # Filter results to only those within our function's range
    for result in results:
        if (result['byte_range'][0] >= parent_range[0] and 
            result['byte_range'][1] <= parent_range[1]):
            
            if result['name'] in ['param', 'opt_param']:
                # New parameter
                if current_params and 'type' in current_params[-1]:
                    param_types.append(current_params[-1]['type'])
                current_params.append({})
            elif result['name'] in ['param_type', 'opt_param_type']:
                if current_params:
                    current_params[-1]['type'] = result['text']
            elif result['name'] == 'variadic':
                param_types.append('...')
    
    # Don't forget the last parameter
    if current_params and 'type' in current_params[-1]:
        param_types.append(current_params[-1]['type'])
    
    # Fallback: parse from text if tree-sitter fails
    if not param_types and param_text and param_text != '()':
        param_types = extract_parameter_types_from_text(param_text)
    
    return param_types

def extract_parameter_types_from_text(param_text: str) -> List[str]:
    """Extract parameter types from parameter list text - FIXED VERSION."""
    if not param_text or param_text == '()':
        return []
    
    # Remove outer parentheses
    param_text = param_text.strip('()')
    if not param_text or param_text == 'void':
        return []
    
    # Handle variadic
    if param_text == '...':
        return ['...']
    
    # Simple parameter splitting (handles most cases)
    param_types = []
    depth = 0
    brace_depth = 0  # NEW: Track brace depth separately
    current_param = []
    
    for char in param_text:
        if char in '<([':
            depth += 1
        elif char in '>)]':
            depth -= 1
        elif char == '{':  # NEW: Track opening brace
            brace_depth += 1
        elif char == '}':  # NEW: Track closing brace
            brace_depth -= 1
        elif char == ',' and depth == 0 and brace_depth == 0:  # NEW: Check brace depth too
            param = ''.join(current_param).strip()
            param_type = extract_type_from_parameter(param)
            if param_type:
                param_types.append(param_type)
            current_param = []
            continue
        current_param.append(char)
    
    # Last parameter
    if current_param:
        param = ''.join(current_param).strip()
        param_type = extract_type_from_parameter(param)
        if param_type:
            param_types.append(param_type)
    
    return param_types

def extract_type_from_parameter(param: str) -> str:
    """Extract type from a parameter declaration."""
    param = param.strip()
    if not param:
        return ''
    
    # Handle special cases
    if param == '...':
        return '...'
    if param == 'void':
        return ''
    
    # Remove default arguments (everything after =)
    if '=' in param:
        param = param[:param.index('=')].strip()
    
    # Handle function pointers: void (*func)(int)
    if '(*' in param or '(*)' in param:
        return param  # Return full function pointer type
    
    # Split into words, handling templates and qualified names
    words = []
    current_word = []
    depth = 0
    
    for char in param:
        if char in '<([':
            depth += 1
            current_word.append(char)
        elif char in '>)]':
            depth -= 1
            current_word.append(char)
        elif char in ' \t' and depth == 0:
            if current_word:
                words.append(''.join(current_word))
                current_word = []
        else:
            current_word.append(char)
    
    if current_word:
        words.append(''.join(current_word))
    
    if not words:
        return param
    
    # Identify the parameter name (last identifier that's not a modifier)
    param_type_words = []
    param_name_found = False
    
    # Walk backwards through words
    for i in range(len(words) - 1, -1, -1):
        word = words[i]
        
        # Skip references and pointers at the end
        if word in ['&', '*', '&&']:
            param_type_words.insert(0, word)
            continue
        
        # If we haven't found a parameter name yet
        if not param_name_found:
            # Check if this looks like a parameter name
            if word and (word[0].islower() or word[0] == '_') and word.isidentifier():
                # This is likely the parameter name, skip it
                param_name_found = True
                continue
            # If it's an array suffix, it's part of the type
            elif '[' in word:
                param_type_words.insert(0, word)
                continue
            # If it's all caps or starts with uppercase, it might be a type
            elif word and (word[0].isupper() or word.isupper()):
                param_type_words.insert(0, word)
                param_name_found = True  # Assume no param name
                continue
        
        # Everything else is part of the type
        param_type_words.insert(0, word)
    
    # Reconstruct the type
    param_type = ' '.join(param_type_words)
    
    # Clean up multiple spaces
    param_type = ' '.join(param_type.split())
    
    # Handle common patterns where our heuristic might fail
    if not param_type and len(words) == 1:
        # Single word - likely just a type
        param_type = words[0]
    elif not param_type:
        # Fallback: assume last word is param name, rest is type
        param_type = ' '.join(words[:-1])
    
    return param_type.strip()  

def main():
    """Build the enhanced API signatures database."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Build a comprehensive database of API signatures"
    )
    
    parser.add_argument(
        "--tt-metal-path",
        default="/home/user/tt-metal",
        help="Path to TT-Metal repository"
    )
    
    parser.add_argument(
        "--output",
        default="api_signatures_db.json",
        help="Output database file"
    )
    
    parser.add_argument(
        "--scan-dirs",
        nargs="+",
        help="Directories to scan (relative to tt-metal root)"
    )
    
    args = parser.parse_args()
    
    # Create database builder
    builder = APISignatureDatabase(args.tt_metal_path)
    
    # Build the database
    builder.build_database(args.scan_dirs)
    
    # Save it
    builder.save(args.output)


if __name__ == "__main__":
    main()