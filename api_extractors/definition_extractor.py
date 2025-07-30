import os
import re
from pathlib import Path
from typing import List, Dict, Set, Optional, Any, Tuple
from collections import defaultdict
from api_database_tools.api_extractors.tree_sitter_backend import parse_file, query

class ASTNodeAnalyzer:
    """Analyzes AST nodes to extract semantic information."""
    
    def __init__(self, source_code: str):
        self.source_code = source_code
        self.lines = source_code.split('\n')
    
    def get_node_text(self, node: Dict) -> str:
        """Extract text for a node given its byte range."""
        start, end = node['byte_range']
        return self.source_code[start:end]
    
    def get_line_content(self, node: Dict) -> str:
        """Get the full line(s) containing this node."""
        start_byte = node['byte_range'][0]
        end_byte = node['byte_range'][1]
        
        # Find line numbers
        current_pos = 0
        start_line = 0
        end_line = 0
        
        for i, line in enumerate(self.lines):
            line_end = current_pos + len(line) + 1  # +1 for newline
            if current_pos <= start_byte < line_end:
                start_line = i
            if current_pos <= end_byte <= line_end:
                end_line = i
                break
            current_pos = line_end
            
        return '\n'.join(self.lines[start_line:end_line + 1])

class UniversalAPIExtractor:
    """Extract all APIs by first parsing everything, then classifying."""
    
    def __init__(self, header_path: str, base_path: Optional[str] = None):
        self.header_path = header_path
        self.base_path = Path(base_path or os.environ.get("TT_METAL_PATH", "/home/user/tt-metal"))
        self.apis = {
            "functions": [],
            "template_functions": [],
            "classes": [],
            "structs": [],
            "enums": [],
            "enum_values": [],
            "typedefs": [],
            "namespaces": [],
            "usings": [],
            "macros": [],
            "constants": [],
            "variables": [],
            "methods": [],
            "constructors": []
        }
        self.full_path = None
        self.source_code = ""
        self.analyzer = None
        
    def extract(self) -> Dict[str, List[str]]:
        """Main extraction method."""
        # Find the file
        if not self._resolve_path():
            return self.apis
            
        # Parse the file
        tree_id = parse_file(str(self.full_path))
        
        # Read source code for analysis
        try:
            with open(self.full_path, 'r', encoding='utf-8', errors='ignore') as f:
                self.source_code = f.read()
            self.analyzer = ASTNodeAnalyzer(self.source_code)
        except Exception as e:
            print(f"[API Extractor] Error reading file: {e}")
            return {"error": f"Could not read file: {self.header_path}"}
        
        # Step 1: Collect ALL nodes that could be declarations
        all_nodes = self._collect_all_nodes(tree_id)
        
        # Step 2: Build a context map (namespace/class hierarchy)
        context_map = self._build_context_map(all_nodes)
        
        # Step 3: Classify each node based on its AST structure
        for node in all_nodes:
            self._classify_and_extract(node, context_map)
        
        # Step 4: Post-process to remove duplicates while keeping all unique signatures
        self._post_process()
        
        return self.apis
    
    def _resolve_path(self) -> bool:
        """Resolve the header file path."""
        # Handle device-relative paths
        if self.header_path.startswith("device/"):
            self.apis["error"] = f"Local file (will be generated): {self.header_path}"
            self.apis["local"] = True
            return False
        
        # Common include path mappings
        path_mappings = [
            ("ttnn/", "ttnn/cpp/ttnn/"),
            ("tt_metal/", "tt_metal/"),
            ("", ""),
            ("", "tt_metal/include/"),
            ("", "tt_metal/api/"),
        ]
        
        for include_prefix, file_prefix in path_mappings:
            if self.header_path.startswith(include_prefix) or include_prefix == "":
                relative_path = self.header_path
                if include_prefix:
                    relative_path = self.header_path[len(include_prefix):]
                
                test_path = self.base_path / file_prefix / relative_path
                if test_path.exists():
                    self.full_path = test_path
                    return True
        
        # Fallback: search for the file
        header_name = Path(self.header_path).name
        search_dirs = ["ttnn", "tt_metal", "tt_eager"]
        
        for search_dir in search_dirs:
            dir_path = self.base_path / search_dir
            if dir_path.exists():
                matches = list(dir_path.rglob(header_name))
                if matches:
                    self.full_path = matches[0]
                    return True
        
        self.apis["error"] = f"Header file not found: {self.header_path}"
        return False
    
    def _collect_all_nodes(self, tree_id: Any) -> List[Dict]:
        """Collect all potentially interesting nodes from the AST."""
        # Enhanced query that specifically looks for class/struct members
        universal_query = """
        [
            ;; Top-level declarations
            (declaration) @declaration
            (function_definition) @function_definition
            (template_declaration) @template_declaration
            (namespace_definition) @namespace_definition
            (class_specifier) @class_specifier
            (struct_specifier) @struct_specifier
            (enum_specifier) @enum_specifier
            (type_definition) @type_definition
            (using_declaration) @using_declaration
            (alias_declaration) @alias_declaration
            
            ;; Class/struct member declarations - ENHANCED
            (class_specifier
                body: (field_declaration_list
                    [
                        ; Method declarations
                        (field_declaration
                            type: (_)
                            declarator: (function_declarator
                                declarator: (field_identifier) @method_name
                                parameters: (parameter_list) @method_params
                            )
                        ) @method_declaration
                        
                        ; Inline method definitions
                        (function_definition
                            type: (_) @inline_method_return
                            declarator: (function_declarator
                                declarator: (field_identifier) @inline_method_name
                                parameters: (parameter_list) @inline_method_params
                            )
                            body: (_)
                        ) @inline_method_definition
                        
                        ; Other field declarations
                        (field_declaration) @field_declaration
                    ]
                )
            )
            
            ;; Same for structs
            (struct_specifier
                body: (field_declaration_list
                    [
                        (field_declaration
                            type: (_)
                            declarator: (function_declarator
                                declarator: (field_identifier) @struct_method_name
                                parameters: (parameter_list) @struct_method_params
                            )
                        ) @struct_method_declaration
                        
                        (function_definition
                            declarator: (function_declarator
                                declarator: (field_identifier) @struct_inline_method_name
                            )
                        ) @struct_inline_method
                        
                        (field_declaration) @struct_field_declaration
                    ]
                )
            )
            
            ;; Member declarations
            (field_declaration) @field_declaration
            (friend_declaration) @friend_declaration
            
            ;; Preprocessor
            (preproc_def) @preproc_def
            (preproc_function_def) @preproc_function_def
            
            ;; Other constructs
            (linkage_specification) @linkage_specification
            (static_assert_declaration) @static_assert_declaration
            
            ;; Capture nested elements too
            (function_declarator) @function_declarator
            (qualified_identifier) @qualified_identifier
            (template_type) @template_type
            (type_identifier) @type_identifier
            (namespace_identifier) @namespace_identifier
            (field_identifier) @field_identifier
            (enumerator) @enumerator
            
            ;; Expressions that might be API usage
            (call_expression) @call_expression
            (field_expression) @field_expression
        ]
        """
        
        results = query(tree_id, universal_query)
        return results

    def _get_call_expression_ranges(self, tree_id: Any) -> List[Tuple[int, int]]:
        """Get byte ranges of all call expressions to exclude them."""
        call_query = """
        (call_expression) @call
        """
        
        call_results = query(tree_id, call_query)
        return [result['byte_range'] for result in call_results] 

    def _build_context_map(self, nodes: List[Dict]) -> Dict[int, Dict]:
        """Build a map of node positions to their context (namespace/class)."""
        context_map = {}
        context_stack = []
        
        # Sort nodes by start position
        sorted_nodes = sorted(nodes, key=lambda n: n['byte_range'][0])
        
        for node in sorted_nodes:
            start, end = node['byte_range']
            
            # Pop contexts that we've exited
            while context_stack and context_stack[-1]['end'] <= start:
                context_stack.pop()
            
            # Add new contexts
            if node['name'] in ['namespace_definition', 'class_specifier', 'struct_specifier']:
                context_info = {
                    'type': node['name'],
                    'start': start,
                    'end': end,
                    'name': self._extract_context_name(node, nodes)
                }
                context_stack.append(context_info)
            
            # Record context for this node
            context_map[start] = list(context_stack)
        
        return context_map
    
    def _extract_context_name(self, node: Dict, all_nodes: List[Dict]) -> str:
        """Extract the name of a namespace/class/struct."""
        start, end = node['byte_range']
        
        # Look for child nodes that are identifiers
        for other in all_nodes:
            if (other['name'] in ['type_identifier', 'namespace_identifier'] and 
                other['byte_range'][0] >= start and 
                other['byte_range'][1] <= end):
                return other['text']
        
        return "anonymous"
    
    def _classify_and_extract(self, node: Dict, context_map: Dict):
        """Classify a node and extract its API information."""
        node_type = node['name']
        node_text = node['text'].strip()
        
        # Skip empty or invalid nodes
        if not node_text:
            return
            
        # Get context for this node
        context = context_map.get(node['byte_range'][0], [])
        
        # Dispatch based on node type
        if node_type == 'function_definition':
            self._extract_function_definition(node, context)
        elif node_type == 'declaration':
            self._extract_declaration(node, context)
        elif node_type == 'template_declaration':
            self._extract_template_declaration(node, context)
        elif node_type == 'class_specifier':
            self._extract_class(node, context)
        elif node_type == 'struct_specifier':
            self._extract_struct(node, context)
        elif node_type == 'enum_specifier':
            self._extract_enum(node, context)
        elif node_type == 'type_definition':
            self._extract_typedef(node, context)
        elif node_type in ['using_declaration', 'alias_declaration']:
            self._extract_using(node, context)
        elif node_type in ['preproc_def', 'preproc_function_def']:
            self._extract_macro(node, context)
        elif node_type == 'field_declaration':
            self._extract_field_declaration(node, context)
        elif node_type == 'enumerator':
            self._extract_enum_value(node, context)
        elif node_type == 'qualified_identifier':
            self._extract_qualified_usage(node, context)
        elif node_type == 'constructor_destructor':
            self._extract_function_definition(node, context)
        elif node_type == 'operator_cast':
            self._extract_function_definition(node, context)
        elif node_type == 'function_declarator':
            # Function declarators often contain the actual function signature
            parent_text = self.analyzer.get_line_content(node)
            if '(' in parent_text and ')' in parent_text:
                self.apis['functions'].append(parent_text.strip())
        elif node_type == 'enumerator_list':
            # Process all enumerators in the list
            self._extract_enum(node, context)
        elif node_type == 'call_expression':
            self._extract_call_expression(node, context)
        elif node_type in ['method_declaration', 'inline_method_definition', 
                   'struct_method_declaration', 'struct_inline_method']:
            self._extract_class_method(node, context)
    
    def _extract_function_definition(self, node: Dict, context: List[Dict]):
        """Extract a function definition."""
        text = node['text']
        
        # Skip function bodies - just get the signature
        if '{' in text:
            text = text[:text.index('{')].strip()
        
        # Check if it's a member function (contains ::)
        if '::' in text and '(' in text:
            # This is a member function definition outside the class
            self.apis['functions'].append(text)
        else:
            # Regular function or in-class method
            if self._is_inside_class(context):
                self.apis['methods'].append(text)
            else:
                self.apis['functions'].append(text)
    
    def _extract_declaration(self, node: Dict, context: List[Dict]):
        """Extract a declaration (could be function, variable, etc.)."""
        text = node['text'].strip()
        
        # Skip if it's just a semicolon or empty
        if not text or text == ';':
            return
        
        # Skip variable declarations with function call initializers
        # Pattern: auto x = Function(...);
        if '=' in text and '(' in text and ')' in text:
            equals_pos = text.find('=')
            first_paren = text.find('(')
            if equals_pos < first_paren:
                # This is a variable initialization, not a function declaration
                return
        
        # Function declaration (has parentheses)
        if '(' in text and ')' in text:
            # Check if it's a function pointer or function declaration
            if self._is_function_declaration(text):
                self.apis['functions'].append(text.rstrip(';'))
    
    def _extract_template_declaration(self, node: Dict, context: List[Dict]):
        """Extract a template declaration."""
        text = node['text']
        
        # Template function
        if '(' in text and ')' in text:
            # Extract just the signature
            if '{' in text:
                text = text[:text.index('{')].strip()
            self.apis['template_functions'].append(text)
        # Template class/struct
        elif 'class' in text or 'struct' in text:
            # Already handled by class/struct extraction
            pass
    
    def _extract_class(self, node: Dict, context: List[Dict]):
        """Extract a class declaration."""
        text = node['text']
        
        # Extract class name
        match = re.search(r'class\s+([A-Za-z_]\w*)', text)
        if match:
            class_name = match.group(1)
            self.apis['classes'].append(class_name)
    
    def _extract_struct(self, node: Dict, context: List[Dict]):
        """Extract a struct declaration."""
        text = node['text']
        
        # Extract struct name
        match = re.search(r'struct\s+([A-Za-z_]\w*)', text)
        if match:
            struct_name = match.group(1)
            self.apis['structs'].append(struct_name)
    
    def _extract_enum(self, node: Dict, context: List[Dict]):
        """Extract an enum declaration with better handling of enum classes."""
        text = node['text']
        
        # Handle enum class with underlying type
        # Pattern: enum class Name : type { ... }
        match = re.search(r'enum\s+(?:class\s+)?(\w+)(?:\s*:\s*(\w+))?\s*{', text)
        if match:
            enum_name = match.group(1)
            underlying_type = match.group(2)  # Could be uint8_t, etc.
            
            # Store the enum
            self.apis['enums'].append(enum_name)
            
            # Also extract enum values from the body
            # Find the content between { and }
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                enum_body = text[start+1:end]
                
                # Extract enum values (handle various patterns)
                # Pattern 1: NAME = value,
                # Pattern 2: NAME,
                # Pattern 3: NAME = 0x1234,
                enum_values = re.findall(r'(\w+)\s*(?:=\s*[^,}]+)?\s*[,}]', enum_body)
                
                for value in enum_values:
                    if value and not value in ['enum', 'class']:  # Skip keywords
                        # Store with full qualification
                        self.apis['enum_values'].append(f"{enum_name}::{value}")
    
    def _extract_typedef(self, node: Dict, context: List[Dict]):
        """Extract a typedef."""
        text = node['text'].strip()
        self.apis['typedefs'].append(text)
    
    def _extract_using(self, node: Dict, context: List[Dict]):
        """Extract a using declaration or alias."""
        text = node['text'].strip()
        self.apis['usings'].append(text)
    
    def _extract_macro(self, node: Dict, context: List[Dict]):
        """Extract a macro definition."""
        text = node['text'].strip()
        
        # Extract macro signature
        if node['name'] == 'preproc_function_def':
            # Function-like macro
            match = re.match(r'#\s*define\s+(\w+\([^)]*\))', text)
            if match:
                self.apis['macros'].append(match.group(1))
        else:
            # Object-like macro
            match = re.match(r'#\s*define\s+(\w+)', text)
            if match:
                self.apis['macros'].append(match.group(1))
    
    def _extract_field_declaration(self, node: Dict, context: List[Dict]):
        """Extract a field declaration (class member)."""
        text = node['text'].strip()
        
        # Method declaration
        if '(' in text and ')' in text:
            self.apis['methods'].append(text.rstrip(';'))
    
    def _extract_enum_value(self, node: Dict, context: List[Dict]):
        """Extract an enum value."""
        text = node['text'].strip()
        
        # Get the enum context if available
        enum_context = None
        for ctx in reversed(context):
            if ctx['type'] == 'enum_specifier':
                enum_context = ctx['name']
                break
        
        if enum_context and enum_context != 'anonymous':
            self.apis['enum_values'].append(f"{enum_context}::{text}")
        else:
            self.apis['enum_values'].append(text)
    
    def _extract_qualified_usage(self, node: Dict, context: List[Dict]):
        """Extract usage of qualified identifiers (might be function calls, enum values, etc.)."""
        text = node['text']
        
        # Skip if it's too short or doesn't contain ::
        if '::' not in text:
            return
        
        # Try to classify based on pattern
        parts = text.split('::')
        last_part = parts[-1]
        
        # Likely enum value (all caps or starts with capital)
        if last_part and (last_part.isupper() or (last_part[0].isupper() and '_' in last_part)):
            self.apis['enum_values'].append(text)
        # Could be a function reference
        elif last_part and last_part[0].islower():
            # Add as potential function
            if text not in [f.split('(')[0] for f in self.apis['functions']]:
                self.apis['functions'].append(f"{text}(...)")
    
    def _extract_call_expression(self, node: Dict, context: List[Dict]):
        """Extract function calls to identify used APIs."""
        text = node['text']
        
        # Extract function name from call
        match = re.match(r'([A-Za-z_][\w:]*)\s*\(', text)
        if match:
            func_name = match.group(1)
            
            # Skip common keywords
            if func_name not in ['if', 'while', 'for', 'switch', 'return', 'sizeof', 'delete', 'new']:
                # DON'T add calls to the functions list!
                # Just track them separately if needed for usage analysis
                pass  # Remove the lines that add to self.apis['functions']
        
    def _is_inside_class(self, context: List[Dict]) -> bool:
        """Check if we're inside a class or struct definition."""
        return any(ctx['type'] in ['class_specifier', 'struct_specifier'] for ctx in context)
    
    def _is_function_declaration(self, text: str) -> bool:
        """Determine if a declaration is a function declaration."""
        # Simple heuristic: has parentheses and doesn't look like a variable initialization
        if '(' not in text or ')' not in text:
            return False
        
        # Check for common non-function patterns
        non_function_patterns = [
            r'=\s*\w+\(',  # Variable initialization
            r'^\s*\(',      # Starts with parenthesis
            r'\)\s*\[',     # Array declaration
        ]
        
        for pattern in non_function_patterns:
            if re.search(pattern, text):
                return False
        
        return True
    
    def _post_process(self):
        """Post-process to clean up and deduplicate while preserving unique signatures."""
        # For each category, remove exact duplicates but keep different signatures
        for category in self.apis:
            if isinstance(self.apis[category], list):
                # Normalize and deduplicate
                seen = {}
                unique_items = []
                
                for item in self.apis[category]:
                    # Normalize whitespace
                    normalized = ' '.join(item.split())
                    
                    # For functions, consider the signature without the body
                    if category in ['functions', 'template_functions', 'methods']:
                        # Remove inline function bodies if present
                        if '{' in normalized:
                            # Check if this is a function body or a default parameter
                            if self._has_function_body(normalized):
                                normalized = normalized[:normalized.index('{')].strip()
                            # Otherwise, it's a default parameter like = {1, 2, 3}, keep it
                    
                    # Remove trailing semicolons
                    normalized = normalized.rstrip(';')
                    
                    # Track unique items
                    if normalized and normalized not in seen:
                        seen[normalized] = True
                        unique_items.append(normalized)
                
                self.apis[category] = unique_items
        
        # Move methods that are actually global functions
        global_methods = []
        for method in self.apis['methods']:
            if '::' in method and not method.strip().startswith('::'):
                # This is actually a member function definition
                self.apis['functions'].append(method)
            else:
                global_methods.append(method)
        self.apis['methods'] = global_methods
        
        # Merge constructors into classes
        for constructor in self.apis['constructors']:
            class_name = constructor.split('(')[0].strip()
            if class_name not in self.apis['classes']:
                self.apis['classes'].append(class_name)
        
        # Final deduplication of functions (might have duplicates from methods)
        self.apis['functions'] = list(dict.fromkeys(self.apis['functions']))

    def _has_function_body(self, text: str) -> bool:
        """
        Check if text contains a function body (not just brace initializers).
        
        Function bodies look like: ) { ... }
        Default parameters look like: = { ... }
        
        Args:
            text: Function signature text
            
        Returns:
            True if the text contains a function body, False otherwise
        """
        if '{' not in text:
            return False
        
        # Find the position of the first {
        brace_pos = text.find('{')
        
        # Look backwards from the { to find what precedes it
        before_brace = text[:brace_pos].rstrip()
        
        # If there's an = before the {, it's a default parameter
        # We need to check after the last ) to avoid cases like: func(int x = f()) { ... }
        last_paren_pos = before_brace.rfind(')')
        
        if last_paren_pos == -1:
            # No closing paren before {, probably not a function
            return False
        
        # Check what's between the ) and {
        between = before_brace[last_paren_pos + 1:].strip()
        
        # If there's an = after the ), it's a weird case, but not a function body
        if '=' in between:
            return False
        
        # Check if it's just qualifiers between ) and {
        # Common qualifiers: const, override, final, noexcept, volatile, mutable
        qualifiers = {'const', 'override', 'final', 'noexcept', 'volatile', 'mutable', ''}
        
        # Split by whitespace and check each word
        words = between.split()
        
        # If all words are qualifiers (or empty), it's a function body
        return all(word in qualifiers for word in words)

    def _extract_class_method(self, node: Dict, context: List[Dict]):
        """Extract a method declared/defined inside a class."""
        # Find the containing class/struct
        class_name = None
        for ctx in reversed(context):
            if ctx['type'] in ['class_specifier', 'struct_specifier']:
                class_name = ctx.get('name', 'unknown')
                break
        
        # Extract method signature
        text = node['text']
        if '{' in text:
            text = text[:text.index('{')].strip()
        
        # Store with class context
        if class_name and class_name != 'anonymous':
            self.apis['methods'].append(f"{class_name}::{text}")
        else:
            self.apis['methods'].append(text)

def extract_apis_from_header(header_path: str, base_path: Optional[str] = None) -> Dict[str, List[str]]:
    """
    New version of extract_apis_from_header using universal AST extraction.
    
    This version:
    1. Parses everything first
    2. Classifies based on AST analysis
    3. Handles multiple signatures for the same function
    4. Should achieve near 100% extraction accuracy
    """
    extractor = UniversalAPIExtractor(header_path, base_path)
    return extractor.extract()


def extract_member_functions(header_path: str, base_path: Optional[str] = None) -> Dict[str, List[Dict]]:
    """
    Extract member functions using the new universal approach.
    """
    extractor = UniversalAPIExtractor(header_path, base_path)
    apis = extractor.extract()
    
    # Build member function map from extracted APIs
    member_functions = defaultdict(list)
    
    # Process functions that contain ::
    for func in apis.get('functions', []):
        if '::' in func and '(' in func:
            # Parse out class name and method info
            match = re.match(r'(.*?)\s+(\w+)::(\w+)\s*(\([^)]*\))(?:\s*(const))?', func)
            if match:
                return_type = match.group(1).strip()
                class_name = match.group(2)
                method_name = match.group(3)
                params = match.group(4)
                is_const = match.group(5) is not None
                
                member_functions[class_name].append({
                    'name': method_name,
                    'signature': func,
                    'return_type': return_type,
                    'params': params,
                    'const': is_const,
                    'defined_outside': True
                })
    
    # Also process methods found inside classes
    for method in apis.get('methods', []):
        # These would need additional context to determine their class
        # For now, we'll skip them as they're harder to attribute
        pass
    
    return dict(member_functions)

