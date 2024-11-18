#!/usr/bin/env python3
"""
Script to analyze a Python project and generate an execution diagram focusing on .py file relations,
including main classes or functions inside each file, and outputs if any.
"""

import ast                     # Module for parsing Python source code into an AST (Abstract Syntax Tree)
import os                      # Module for interacting with the operating system (e.g., file paths)
from graphviz import Digraph   # Module for creating graph visualizations
import importlib.util          # Module for utilities related to import mechanisms

class ExecutionFlowVisitor(ast.NodeVisitor):
    """
    AST Visitor class that traverses the AST of a Python file to collect information
    about imports, function calls, classes, functions, and outputs.
    """
    def __init__(self, filename, func_to_file):
        self.filename = os.path.abspath(filename)    # Absolute path of the file being analyzed
        self.func_to_file = func_to_file             # Mapping of function names to file paths
        self.imports = set()                         # Set of tuples (importer_file, imported_module)
        self.function_calls = set()                  # Set of tuples (caller_file, callee_file)
        self.outputs = set()                         # Set of output functions used in this file
        self.classes = set()                         # Set of class names defined in this file
        self.functions = set()                       # Set of function names defined in this file (not in classes)
        self.current_class = None                    # Name of the current class being visited
        self.current_function = None                 # Name of the current function being visited

    def visit_Import(self, node):
        """
        Visit 'import' statements and collect imported modules.
        """
        for alias in node.names:
            module_name = alias.name
            # Add a tuple of (current file, imported module) to the imports set
            self.imports.add((self.filename, module_name))
        self.generic_visit(node)  # Continue traversing the AST

    def visit_ImportFrom(self, node):
        """
        Visit 'from ... import ...' statements and collect imported modules.
        """
        module = node.module
        for alias in node.names:
            # Construct the full module name
            imported_module = f"{module}.{alias.name}" if module else alias.name
            self.imports.add((self.filename, imported_module))
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        """
        Visit class definitions and collect class names.
        """
        class_name = node.name
        self.classes.add(class_name)  # Add the class name to the set
        self.current_class = class_name  # Set the current class context
        self.generic_visit(node)      # Visit child nodes (e.g., methods)
        self.current_class = None     # Reset the current class context

    def visit_FunctionDef(self, node):
        """
        Visit function definitions and collect function names.
        """
        function_name = node.name
        if self.current_class is None:
            # Only collect functions that are not within a class (top-level functions)
            self.functions.add(function_name)
        self.generic_visit(node)  # Visit child nodes

    def visit_Call(self, node):
        """
        Visit function calls to collect function calls between files and outputs.
        """
        func_name = self.get_func_name(node)
        if func_name:
            # Attempt to find the file where the called function is defined
            callee_file = self.find_callee_file(func_name)
            if callee_file and callee_file != self.filename:
                # Record the function call between files
                self.function_calls.add((self.filename, callee_file))
            # Check if the function is an output function
            if func_name in ('print', 'logging.info', 'logging.debug', 'logging.error'):
                self.outputs.add(func_name)
        self.generic_visit(node)

    def get_func_name(self, node):
        """
        Extract the function name from a Call node.
        """
        if isinstance(node.func, ast.Name):
            # Simple function call: func()
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            # Method call or attribute access: obj.method()
            return self.get_attribute_name(node.func)
        return None  # Could not determine the function name

    def get_attribute_name(self, node):
        """
        Recursively extract the full attribute name from an Attribute node.
        """
        parts = []
        while isinstance(node, ast.Attribute):
            parts.insert(0, node.attr)  # Insert attribute name at the beginning
            node = node.value
        if isinstance(node, ast.Name):
            parts.insert(0, node.id)    # Insert the base object name
        return '.'.join(parts)          # Combine parts into a full name

    def find_callee_file(self, func_name):
        """
        Find the file where a given function or class is defined using the func_to_file map.
        """
        return self.func_to_file.get(func_name)

def parse_file(file_path, func_to_file):
    """
    Parse a single Python file and return an ExecutionFlowVisitor instance with collected data.
    """
    with open(file_path, "r", encoding='utf-8') as file:
        source_code = file.read()
    tree = ast.parse(source_code)          # Parse the source code into an AST
    visitor = ExecutionFlowVisitor(file_path, func_to_file)
    visitor.visit(tree)                    # Traverse the AST
    return visitor

def build_function_to_file_map(py_files):
    """
    Build a mapping from function and class names to the files where they are defined.
    """
    func_to_file = {}
    for file_path in py_files:
        with open(file_path, "r", encoding='utf-8') as file:
            source_code = file.read()
        tree = ast.parse(source_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Top-level function
                func_name = node.name
                func_to_file[func_name] = os.path.abspath(file_path)
            elif isinstance(node, ast.ClassDef):
                # Class definition
                class_name = node.name
                func_to_file[class_name] = os.path.abspath(file_path)
                for body_item in node.body:
                    if isinstance(body_item, ast.FunctionDef):
                        # Method within a class
                        method_name = body_item.name
                        full_name = f"{class_name}.{method_name}"
                        func_to_file[full_name] = os.path.abspath(file_path)
    return func_to_file

def find_source_file(module_name):
    """
    Find the source file for a given module name.
    """
    try:
        spec = importlib.util.find_spec(module_name)
        if spec and spec.origin and spec.origin.endswith('.py'):
            return os.path.abspath(spec.origin)
    except ModuleNotFoundError:
        pass
    return None  # Could not find the source file

def analyze_project():
    """
    Analyze the Python project by parsing all .py files and collecting information.
    """
    visitors = {}    # Mapping from file paths to ExecutionFlowVisitor instances
    py_files = []    # List of all .py files in the project

    # Collect all .py files in the current directory and subdirectories
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                py_files.append(os.path.join(root, file))

    # Build the function-to-file mapping
    func_to_file = build_function_to_file_map(py_files)

    # Parse each file and collect data
    for file_path in py_files:
        visitor = parse_file(file_path, func_to_file)
        visitors[os.path.abspath(file_path)] = visitor

    return visitors

def create_execution_diagram(visitors, output_file="execution_flow"):
    """
    Create an execution diagram using Graphviz based on the collected information.
    """
    dot = Digraph(format="pdf")   # Create a new directed graph
    dot.attr(rankdir="LR")        # Set the direction of the graph (Left to Right)

    # Define node styles
    dot.node_attr.update(
        style='filled',
        shape='box',
        fillcolor='lightyellow',
        fontname='Courier'
    )
    dot.edge_attr.update(arrowsize='0.7')

    # Add nodes for each .py file with detailed labels
    for file_path, visitor in visitors.items():
        filename = os.path.basename(file_path)
        label_parts = [filename]

        # Add horizontal separator
        separator = '\n' + '-' * 20 + '\n'

        # Include classes or functions
        if visitor.classes:
            # If classes are defined in the file
            classes = '\n'.join(sorted(visitor.classes))
            label_parts.extend([separator, classes])
        elif visitor.functions:
            # If functions are defined in the file
            functions = '\n'.join(sorted(visitor.functions))
            label_parts.extend([separator, functions])
        else:
            # If no classes or functions are defined
            label_parts.extend([separator, "(No classes or functions)"])

        # Include outputs if any
        if visitor.outputs:
            outputs = '\n'.join(sorted(visitor.outputs))
            label_parts.extend([separator, "Outputs:", outputs])

        # Final separator
        label_parts.append(separator)

        # Combine label parts into a single string
        label = ''.join(label_parts)

        # Add the node to the graph
        dot.node(file_path, label=label)

    # Add edges for imports between files
    for visitor in visitors.values():
        for importer_file, imported_module in visitor.imports:
            imported_file = find_source_file(imported_module)
            if imported_file and imported_file in visitors:
                # Add an edge from the importing file to the imported file
                dot.edge(importer_file, imported_file, label='imports', color='blue')

    # Add edges for function calls between files
    for visitor in visitors.values():
        for caller_file, callee_file in visitor.function_calls:
            if callee_file and callee_file in visitors:
                # Add an edge from the caller file to the callee file
                dot.edge(caller_file, callee_file, label='calls', color='black')

    # Render the graph to a PDF file and keep the DOT source
    dot.render(output_file, cleanup=False)
    print(f"Execution diagram generated: {output_file}.pdf")
    print(f"DOT source file generated: {output_file}.gv")

if __name__ == "__main__":
    # Main execution starts here
    visitors = analyze_project()           # Analyze the project and collect data
    create_execution_diagram(visitors)     # Create the execution diagram
