#!/usr/bin/env python3
"""
Build a comprehensive database of API signatures AND implementations.
Modified to capture and store full function implementations.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import defaultdict
import hashlib
import re
from api_tools.api_extractors.definition_extractor_impl import (
    extract_apis_from_header,
    extract_member_functions
)

from api_tools.api_extractors.tree_sitter_backend import parse_file, query

class APISignatureDatabase:
    """Database containing full API signatures and implementations."""
    
    def __init__(self, tt_metal_path: str = None):
        self.tt_metal_path = Path(tt_metal_path or os.environ.get("TT_METAL_HOME", "/home/user/tt-metal"))
        self.database = {
            "metadata": {
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "tt_metal_path": str(self.tt_metal_path),
                "description": "Comprehensive API signatures and implementations database"
            },
            "apis": {},
            "headers": {},
            "namespaces": defaultdict(list),
            "implementations": {},  # New: Maps function keys to their implementations
            "implementation_locations": defaultdict(list),  # Track where implementations are found
        }
        # Track what we've seen to avoid duplicates
        self.seen_apis = set()
        # Track declarations waiting for implementations
        self.declarations_needing_impl = {}
        
    def build_database(self, scan_dirs: List[str] = None):
        """Build the database by scanning header and source files."""
        if scan_dirs is None:
            scan_dirs = [
                "ttnn",
                "tt_metal"
            ]
        
        print(f"Building Enhanced API Signatures and Implementations Database")
        print(f"Scanning directories: {scan_dirs}")
        print("=" * 80)
        
        # Step 1: Find all header and source files
        all_files = self._find_all_files(scan_dirs)
        
        # Step 2: Extract and store APIs with implementations
        self._extract_and_store_signatures(all_files)
        
        # Step 3: Build indices
        self._build_indices()
        
        # Step 4: Add common STL APIs
        self._add_standard_library_apis()
        
        # Step 5: Link declarations with implementations
        self._link_declarations_and_implementations()
        
        print(f"\nDatabase built successfully!")
        print(f"Total headers analyzed: {len(self.database['headers'])}")
        print(f"Total unique APIs found: {len(self.database['apis'])}")
        print(f"Total implementations captured: {len(self.database['implementations'])}")
        
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
        """Extract and store API signatures and implementations from files."""
        print(f"\nExtracting API signatures and implementations from {len(files)} files...")
        
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
            
            # Extract APIs using the extractor
            apis = self.extract_apis_with_implementations(str(file_path), str(self.tt_metal_path))
            
            if apis.get("error"):  # Only true if error is not None/empty
                print(f"[DEBUG] Extraction error: {apis['error']}")
                errors += 1
                continue
            
            # Store all extracted APIs
            header_apis = []
            
            # Process functions with implementations
            for func_data in apis.get("functions_with_impl", []):
                api_entry = self._create_api_entry_with_impl(func_data, "function", include_path)
                if api_entry and self._store_api(api_entry):
                    header_apis.append(api_entry["key"])
                    # Store implementation if present
                    if func_data.get("implementation"):
                        self._store_implementation(api_entry["key"], func_data["implementation"], include_path)
            
            # Process template functions with implementations
            for func_data in apis.get("template_functions_with_impl", []):
                api_entry = self._create_api_entry_with_impl(func_data, "template_function", include_path)
                if api_entry and self._store_api(api_entry):
                    header_apis.append(api_entry["key"])
                    if func_data.get("implementation"):
                        self._store_implementation(api_entry["key"], func_data["implementation"], include_path)
            
            # Process member functions with implementations
            for class_name, methods in apis.get("member_functions_with_impl", {}).items():
                for method_data in methods:
                    api_entry = self._create_member_function_entry_with_impl(
                        class_name, method_data, include_path
                    )
                    if api_entry and self._store_api(api_entry):
                        header_apis.append(api_entry["key"])
                        if method_data.get("implementation"):
                            self._store_implementation(api_entry["key"], method_data["implementation"], include_path)
            
            # Process other API types (classes, structs, enums, etc.)
            for class_name in apis.get("classes", []):
                api_entry = self._create_type_entry(class_name, "class", include_path)
                if api_entry and self._store_api(api_entry):
                    header_apis.append(api_entry["key"])
            
            for struct_name in apis.get("structs", []):
                api_entry = self._create_type_entry(struct_name, "struct", include_path)
                if api_entry and self._store_api(api_entry):
                    header_apis.append(api_entry["key"])
            
            for enum_name in apis.get("enums", []):
                api_entry = self._create_type_entry(enum_name, "enum", include_path)
                if api_entry and self._store_api(api_entry):
                    header_apis.append(api_entry["key"])
            
            # Store header's APIs
            if header_apis:
                self.database["headers"][include_path] = header_apis
                
        print(f"\nAPI extraction complete. Errors: {errors}")
    
    def _create_api_entry_with_impl(self, func_data: Dict, api_type: str, header: str) -> Optional[Dict]:
        """Create an API entry for a function that may have an implementation."""
        func_name = func_data.get("name")
        if not func_name:
            return None
        
        signature = func_data.get("signature", "")
        
        # Create entry
        return {
            "name": func_name,
            "type": api_type,
            "signature": signature,
            "header": header,
            "key": f"{api_type}::{func_name}",
            "parameters": func_data.get("parameters", "()"),
            "param_types": func_data.get("param_types", []),
            "return_type": func_data.get("return_type", "void"),
            "is_template": api_type == "template_function",
            "has_implementation": bool(func_data.get("implementation")),
            "implementation_location": header if func_data.get("implementation") else None
        }
    
    def _create_member_function_entry_with_impl(self, class_name: str, method_data: Dict, header: str) -> Optional[Dict]:
        """Create an API entry for a member function that may have an implementation."""
        method_name = method_data.get('name')
        if not method_name:
            return None
        
        # Create a unique key including parameter signature to handle overloads
        params = method_data.get('parameters', '()')
        param_sig = params.replace(' ', '')
        key = f"member_function::{class_name}::{method_name}{param_sig}"
        
        return {
            "name": method_name,
            "type": "member_function",
            "signature": method_data.get('signature', f"{method_name}()"),
            "header": header,
            "class": class_name,
            "key": key,
            "return_type": method_data.get('return_type', ''),
            "parameters": params,
            "param_types": method_data.get('param_types', []),
            "const": method_data.get('const', False),
            "has_implementation": bool(method_data.get("implementation")),
            "implementation_location": header if method_data.get("implementation") else None
        }
    
    def _store_implementation(self, api_key: str, implementation: str, location: str):
        """Store a function implementation."""
        self.database["implementations"][api_key] = {
            "code": implementation,
            "location": location,
            "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.database["implementation_locations"][api_key].append(location)
        #print(implementation)
    
    def _link_declarations_and_implementations(self):
        """Link function declarations with their implementations found in different files."""
        print("\nLinking declarations with implementations...")
        
        # For each API, check if we found its implementation elsewhere
        for api_key, api_info in self.database["apis"].items():
            if api_info["type"] in ["function", "template_function", "member_function"]:
                # Check if this is a declaration without implementation
                if not api_info.get("has_implementation"):
                    # Try to find implementation by matching signature
                    impl_key = self._find_implementation_for_declaration(api_info)
                    if impl_key and impl_key in self.database["implementations"]:
                        api_info["has_implementation"] = True
                        api_info["implementation_key"] = impl_key
                        print(f"  Linked {api_info['name']} to implementation in {self.database['implementations'][impl_key]['location']}")
    
    def _find_implementation_for_declaration(self, api_info: Dict) -> Optional[str]:
        """Try to find an implementation for a declaration."""
        # This is a simplified version - in practice, you'd want more sophisticated matching
        name = api_info["name"]
        
        # Look for implementations with matching names
        for impl_key in self.database["implementations"]:
            if name in impl_key:
                # Could add more sophisticated signature matching here
                return impl_key
        
        return None
    
    def _create_type_entry(self, type_name: str, type_kind: str, header: str) -> Optional[Dict]:
        """Create an API entry for a type (class/struct/enum)."""
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
    
    def _store_api(self, api_entry: Dict) -> bool:
        """Store an API entry with unique hash for overloads."""
        base_key = api_entry["key"]
        
        # For functions and methods, create a unique key based on the full signature
        if api_entry["type"] in ["function", "template_function", "member_function", "method"]:
            signature = api_entry.get("signature", "")
            sig_hash = hashlib.md5(signature.encode()).hexdigest()[:8]
            
            api_entry["key"] = f"{base_key}#{sig_hash}"
            api_entry["base_key"] = base_key
        
        key = api_entry["key"]
        
        if key not in self.database["apis"]:
            self.seen_apis.add(key)
            self.database["apis"][key] = api_entry
            return True
        
        return False
    
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
            return str(file_path)
    
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
    
    def save(self, output_file: str = "api_signatures_database.json"):
        """Save the database to a JSON file."""
        output_path = Path(output_file)
        
        # Update metadata
        self.database["metadata"]["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.database["metadata"]["total_apis"] = len(self.database["apis"])
        self.database["metadata"]["total_headers"] = len(self.database["headers"])
        self.database["metadata"]["total_implementations"] = len(self.database["implementations"])
        
        with open(output_path, 'w') as f:
            json.dump(self.database, f, indent=2, sort_keys=True)
            
        print(f"\nDatabase saved to: {output_path}")
        
        # Save a summary
        self._save_summary(output_path.with_suffix('.txt'))
        
    def _save_summary(self, summary_path: Path):
        """Save a readable summary."""
        with open(summary_path, 'w') as f:
            f.write("Enhanced API Signatures and Implementations Database Summary\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Created: {self.database['metadata']['created']}\n")
            f.write(f"Total APIs: {len(self.database['apis'])}\n")
            f.write(f"Total Headers: {len(self.database['headers'])}\n")
            f.write(f"Total Implementations: {len(self.database['implementations'])}\n\n")
            
            # Count by type
            type_counts = defaultdict(int)
            impl_counts = defaultdict(int)
            for api_info in self.database["apis"].values():
                api_type = api_info["type"]
                type_counts[api_type] += 1
                if api_info.get("has_implementation"):
                    impl_counts[api_type] += 1
            
            f.write("APIs by Type:\n")
            for api_type, count in sorted(type_counts.items()):
                impl_count = impl_counts.get(api_type, 0)
                f.write(f"  {api_type}: {count} (with implementations: {impl_count})\n")
            f.write("\n")
            
            # Show examples with implementations
            f.write("Example APIs with Implementations:\n")
            f.write("-" * 40 + "\n")
            examples_shown = 0
            for api_key, api_info in self.database["apis"].items():
                if api_info.get("has_implementation") and examples_shown < 5:
                    f.write(f"\nAPI: {api_info['name']}\n")
                    f.write(f"Type: {api_info['type']}\n")
                    f.write(f"Signature: {api_info['signature']}\n")
                    f.write(f"Header: {api_info['header']}\n")
                    
                    if api_key in self.database["implementations"]:
                        impl = self.database["implementations"][api_key]
                        f.write(f"Implementation location: {impl['location']}\n")
                        f.write("Implementation preview:\n")
                        # Show first 5 lines
                        lines = impl['code'].split('\n')[:5]
                        for line in lines:
                            f.write(f"  {line}\n")
                        if len(impl['code'].split('\n')) > 5:
                            f.write("  ...\n")
                    
                    examples_shown += 1

    def extract_apis_with_implementations(self, file_path: str, base_path: str) -> Dict[str, Any]:
        """Extract APIs along with their full implementations."""
        tree_id = parse_file(file_path)
        
        # Much simpler query - just find function definitions
        simple_query = """
        (function_definition) @func
        (template_declaration
            (function_definition) @template_func
        )
        """
        
        results = query(tree_id, simple_query)
        
        # Read source file
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            source_code = f.read()
        
        apis = {
            "functions_with_impl": [],
            "template_functions_with_impl": [],
            "member_functions_with_impl": defaultdict(list),
            "classes": [],
            "structs": [], 
            "enums": [],
            "error": None
        }
        
        # Process each function found
        for result in results:
            start, end = result['byte_range']
            full_text = source_code[start-1:end]
            #print(full_text)
            # Extract basic info using regex on the full text
            func_name = extract_function_name_from_text(full_text)
            is_template = result['name'] == 'template_func'
            
            func_data = {
                'name': func_name,
                'signature': extract_signature_from_text(full_text),
                'implementation': full_text,
                'parameters': extract_params_from_text(full_text),
                'param_types': [],  # Can be filled later
                'has_body': '{' in full_text
            }
            
            #print(func_data)

            if is_template:
                apis['template_functions_with_impl'].append(func_data)
            else:
                apis['functions_with_impl'].append(func_data)
        
        return apis

    def _extract_signature_from_impl(self, full_text: str) -> str:
        """Extract just the signature from a full implementation."""
        # Find the opening brace
        brace_pos = full_text.find('{')
        if brace_pos != -1:
            return full_text[:brace_pos].strip()
        return full_text.strip()


def extract_parameter_types_from_text(param_text: str) -> List[str]:
    """Extract parameter types from parameter list text."""
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
    brace_depth = 0
    current_param = []
    
    for char in param_text:
        if char in '<([':
            depth += 1
        elif char in '>)]':
            depth -= 1
        elif char == '{':
            brace_depth += 1
        elif char == '}':
            brace_depth -= 1
        elif char == ',' and depth == 0 and brace_depth == 0:
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

def extract_function_name_from_text(text: str) -> str:
    """Extract function name from function definition text."""
    # Find the function name before the first (
    import re
    # Handle operators
    if 'operator' in text:
        match = re.search(r'operator[^(]+', text)
        if match:
            return match.group(0).strip()
    
    # Normal functions - find identifier before (
    match = re.search(r'(\w+)\s*\(', text)
    if match:
        return match.group(1)
    return "unknown"

def extract_signature_from_text(text: str) -> str:
    """Extract just the signature (everything before {)."""
    if '{' in text:
        return text[:text.index('{')].strip()
    return text.strip()

def extract_params_from_text(text: str) -> str:
    """Extract parameter list."""
    match = re.search(r'\(([^)]*)\)', text)
    if match:
        return f"({match.group(1)})"
    return "()"

def main():
    """Build the enhanced API signatures and implementations database."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Build a comprehensive database of API signatures and implementations"
    )
    
    parser.add_argument(
        "--tt-metal-path",
        default="/home/user/tt-metal",
        help="Path to TT-Metal repository"
    )
    
    parser.add_argument(
        "--output",
        default="api_impl_db.json",
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
