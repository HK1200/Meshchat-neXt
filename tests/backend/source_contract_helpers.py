# SPDX-License-Identifier: 0BSD
"""Read declaration contracts without dormant mutation-generated copies."""

import ast
import re


def source_declarations(text: str) -> str:
    # The real decorated functions remain the source of the static contract.
    if "from mutmut.mutation.trampoline import" not in text:
        return text
    lines = text.splitlines(keepends=True)
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.fullmatch(
            r"x_.*__mutmut_(?:orig|[0-9]+)", node.name
        ):
            start = min([node.lineno, *[d.lineno for d in node.decorator_list]])
            for index in range(start - 1, node.end_lineno):
                lines[index] = "\n"
    return "".join(lines)
