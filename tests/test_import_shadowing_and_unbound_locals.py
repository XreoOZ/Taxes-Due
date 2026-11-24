"""
Unit tests verifying that all files have zero local import shadowing and zero UnboundLocalError risks.
"""
import ast
import os
import unittest


class TestImportShadowingAndUnboundLocals(unittest.TestCase):
    def test_repo_has_zero_unbound_locals_from_imports(self):
        """No module or function should load a name before an indented local import."""
        issues = []
        for root, dirs, files in os.walk("."):
            if any(p in root for p in [".git", "__pycache__", "dist", "build", ".venv"]):
                continue
            for f in files:
                if f.endswith(".py"):
                    filepath = os.path.join(root, f)
                    with open(filepath, "r", encoding="utf-8") as fp:
                        try:
                            tree = ast.parse(fp.read(), filename=filepath)
                        except Exception:
                            continue

                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            global_names = set()
                            for child in ast.walk(node):
                                if isinstance(child, ast.Global):
                                    global_names.update(child.names)

                            for child in ast.walk(node):
                                if isinstance(child, (ast.Import, ast.ImportFrom)):
                                    for alias in child.names:
                                        imported_name = alias.asname or alias.name.split(".")[0]
                                        if imported_name in global_names:
                                            continue
                                        for other in ast.walk(node):
                                            if (
                                                isinstance(other, ast.Name)
                                                and isinstance(other.ctx, ast.Load)
                                                and other.id == imported_name
                                                and other.lineno < child.lineno
                                            ):
                                                issues.append(
                                                    f"{filepath}::{node.name}(): line {other.lineno} uses {imported_name} before import at line {child.lineno}"
                                                )

        self.assertEqual(issues, [], f"Found unbound local risks:\n" + "\n".join(issues))
