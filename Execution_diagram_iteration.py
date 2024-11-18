#!/usr/bin/env python3
"""
Script to analyze a Python project and generate an execution diagram focusing on .py file relations,
including main classes or functions inside each file, outputs, and approximate chronological order of function calls.
"""

import ast
import os
from graphviz import Digraph
import importlib.util

# Global sequence counter
call_sequence_counter = 0  # Start at 0

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
        self.calls_with_sequence = []                # List of tuples: (sequence_number, caller_file, callee_file)

    def visit_Import(self, node):
        for alias in node.names:
            module_name = alias.name
            self.imports.add((self.filename, module_name))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module
        for alias in node.names:
            imported_module = f"{module}.{alias.name}" if module else alias.name
            self.imports.add((self.filename, imported_module))
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        class_name = node.name
        self.classes.add(class_name)
        self.current_class = class_name
        self.generic_visit(node)
        self.current_class = None

    def visit_FunctionDef(self, node):
        function_name = node.name
        if self.current_class is None:
            self.functions.add(function_name)
        self.generic_visit(node)

    def visit_Call(self, node):
        global call_sequence_counter  # Use the global sequence counter
        func_name = self.get_func_name(node)
        if func_name:
            callee_file = self.find_callee_file(func_name)
            caller_file = self.filename
            if callee_file and callee_file != caller_file:
                # Increment the global call sequence counter
                call_sequence_counter += 1
                # Record the function call with sequence number
                self.calls_with_sequence.append((call_sequence_counter, caller_file, callee_file))
            # Check for output functions like print or logger
            if func_name in ('print', 'logging.info', 'logging.debug', 'logging.error'):
                self.outputs.add(func_name)
        self.generic_visit(node)

    def get_func_name(self, node):
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return self.get_attribute_name(node.func)
        return None

    def get_attribute_name(self, node):
        parts = []
        while isinstance(node, ast.Attribute):
            parts.insert(0, node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.insert(0, node.id)
        return '.'.join(parts)

    def find_callee_file(self, func_name):
        return self.func_to_file.get(func_name)

def parse_file(file_path, func_to_file):
    with open(file_path, "r", encoding='utf-8') as file:
        source_code = file.read()
    tree = ast.parse(source_code)
    visitor = ExecutionFlowVisitor(file_path, func_to_file)
    visitor.visit(tree)
    return visitor

def build_function_to_file_map(py_files):
    func_to_file = {}
    for file_path in py_files:
        with open(file_path, "r", encoding='utf-8') as file:
            source_code = file.read()
        tree = ast.parse(source_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_name = node.name
                func_to_file[func_name] = os.path.abspath(file_path)
            elif isinstance(node, ast.ClassDef):
                class_name = node.name
                func_to_file[class_name] = os.path.abspath(file_path)
                for body_item in node.body:
                    if isinstance(body_item, ast.FunctionDef):
                        method_name = body_item.name
                        full_name = f"{class_name}.{method_name}"
                        func_to_file[full_name] = os.path.abspath(file_path)
    return func_to_file

def find_source_file(module_name):
    try:
        spec = importlib.util.find_spec(module_name)
        if spec and spec.origin and spec.origin.endswith('.py'):
            return os.path.abspath(spec.origin)
    except ModuleNotFoundError:
        pass
    return None

def analyze_project():
    visitors = {}
    py_files = []

    # Collect all .py files in the project directory
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                py_files.append(os.path.join(root, file))

    # Build function-to-file map
    func_to_file = build_function_to_file_map(py_files)

    # Parse each file
    for file_path in py_files:
        visitor = parse_file(file_path, func_to_file)
        visitors[os.path.abspath(file_path)] = visitor

    return visitors

def create_execution_diagram(visitors, output_file="execution_flow"):
    dot = Digraph(format="pdf")
    dot.attr(rankdir="LR")

    # Define node styles
    dot.node_attr.update(style='filled', shape='box', fillcolor='lightyellow', fontname='Courier')
    dot.edge_attr.update(arrowsize='0.7')

    # Add nodes for each .py file
    for file_path, visitor in visitors.items():
        filename = os.path.basename(file_path)
        label_parts = [filename]

        # Add horizontal line
        separator = '\n' + '-' * 20 + '\n'

        # Include classes or functions
        if visitor.classes:
            classes = '\n'.join(sorted(visitor.classes))
            label_parts.extend([separator, classes])
        elif visitor.functions:
            functions = '\n'.join(sorted(visitor.functions))
            label_parts.extend([separator, functions])
        else:
            label_parts.extend([separator, "(No classes or functions)"])

        # Include outputs if any
        if visitor.outputs:
            outputs = '\n'.join(sorted(visitor.outputs))
            label_parts.extend([separator, "Outputs:", outputs])

        # Final separator
        label_parts.append(separator)

        label = ''.join(label_parts)
        dot.node(file_path, label=label)

    # Collect all calls with sequence numbers from all visitors
    all_calls_with_sequence = []
    for visitor in visitors.values():
        all_calls_with_sequence.extend(visitor.calls_with_sequence)

    # Sort all calls by sequence number
    all_calls_with_sequence.sort(key=lambda x: x[0])

    # Add edges for function calls between files with sequence numbers
    for seq_num, caller_file, callee_file in all_calls_with_sequence:
        if callee_file and callee_file in visitors:
            dot.edge(caller_file, callee_file, label=f'call {seq_num}', color='black')

    # Add edges for imports
    for visitor in visitors.values():
        for importer_file, imported_module in visitor.imports:
            imported_file = find_source_file(imported_module)
            if imported_file and imported_file in visitors:
                dot.edge(importer_file, imported_file, label='imports', color='blue')

    # Save the graph
    dot.render(output_file, cleanup=False)
    print(f"Execution diagram generated: {output_file}.pdf")
    print(f"DOT source file generated: {output_file}.gv")

if __name__ == "__main__":
    visitors = analyze_project()
    create_execution_diagram(visitors)

