"""
Command Type Validator — 命令参数类型验证

防止工具调用语法错误（缺少括号、引号、类型错误等）
在工具调用发送到执行引擎前进行验证和修复。

Usage:
    from agent.command_validator import validate_and_fix_tool_call
    
    is_valid, fixed_args, errors = validate_and_fix_tool_call("terminal", {"command": "ls -la"})
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


# 参数类型定义
PARAMETER_TYPES: Dict[str, Dict[str, type]] = {
    "terminal": {
        "command": str,
        "background": bool,
        "timeout": int,
        "workdir": str,
    },
    "write_file": {
        "path": str,
        "content": str,
    },
    "read_file": {
        "path": str,
        "offset": int,
        "limit": int,
    },
    "execute_code": {
        "code": str,
    },
    "search_files": {
        "pattern": str,
        "target": str,
        "path": str,
    },
    "browser_navigate": {
        "url": str,
    },
    "browser_click": {
        "ref": str,
    },
    "browser_type": {
        "ref": str,
        "text": str,
    },
    "send_message": {
        "action": str,
        "target": str,
        "message": str,
    },
    "memory": {
        "action": str,
        "target": str,
        "content": str,
    },
    "skill_view": {
        "name": str,
    },
    "delegate_task": {
        "goal": str,
        "context": str,
    },
}

# 必需参数
REQUIRED_PARAMS: Dict[str, List[str]] = {
    "terminal": ["command"],
    "write_file": ["path", "content"],
    "read_file": ["path"],
    "execute_code": ["code"],
    "search_files": ["pattern"],
    "browser_navigate": ["url"],
    "browser_click": ["ref"],
    "browser_type": ["ref", "text"],
    "send_message": ["action"],
    "memory": ["action", "target"],
    "skill_view": ["name"],
    "delegate_task": ["goal"],
}


def check_brackets(code: str) -> bool:
    """检查括号是否匹配"""
    stack = []
    pairs = {'(': ')', '[': ']', '{': '}'}
    in_string = False
    string_char = None
    
    for i, char in enumerate(code):
        # 处理字符串内的括号
        if char in ('"', "'") and not in_string:
            in_string = True
            string_char = char
            continue
        if in_string and char == string_char:
            in_string = False
            continue
        if in_string:
            continue
        
        if char in pairs:
            stack.append((char, i))
        elif char in pairs.values():
            if not stack:
                return False
            open_char, _ = stack.pop()
            if pairs[open_char] != char:
                return False
    
    return len(stack) == 0


def fix_brackets(code: str) -> str:
    """自动修复括号"""
    stack = []
    pairs = {'(': ')', '[': ']', '{': '}'}
    in_string = False
    string_char = None
    
    for i, char in enumerate(code):
        if char in ('"', "'") and not in_string:
            in_string = True
            string_char = char
            continue
        if in_string and char == string_char:
            in_string = False
            continue
        if in_string:
            continue
        
        if char in pairs:
            stack.append(char)
        elif char in pairs.values():
            if stack and pairs.get(stack[-1]) == char:
                stack.pop()
    
    # 添加缺失的闭合括号
    closing = ''.join(pairs[c] for c in reversed(stack))
    return code + closing


def check_quotes(code: str) -> bool:
    """检查引号是否匹配"""
    single = code.count("'") % 2 == 0
    double = code.count('"') % 2 == 0
    return single and double


def fix_quotes(code: str) -> str:
    """自动修复引号"""
    # 简单策略：如果奇数个引号，在末尾添加一个
    if code.count('"') % 2 != 0:
        code += '"'
    if code.count("'") % 2 != 0:
        code += "'"
    return code


def validate_and_fix_tool_call(
    tool_name: str,
    args: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any], List[str]]:
    """
    验证并修复工具调用参数
    
    Args:
        tool_name: 工具名称
        args: 工具参数
        
    Returns:
        (is_valid, fixed_args, errors)
        - is_valid: 是否验证通过
        - fixed_args: 修复后的参数
        - errors: 错误信息列表
    """
    errors = []
    fixed_args = args.copy()
    
    # 1. 检查必需参数
    if tool_name in REQUIRED_PARAMS:
        for param in REQUIRED_PARAMS[tool_name]:
            if param not in fixed_args:
                errors.append(f"缺少必需参数: {param}")
    
    # 2. 检查参数类型
    if tool_name in PARAMETER_TYPES:
        for param, value in list(fixed_args.items()):
            if param in PARAMETER_TYPES[tool_name]:
                expected_type = PARAMETER_TYPES[tool_name][param]
                if not isinstance(value, expected_type):
                    try:
                        # 尝试类型转换
                        if expected_type == str:
                            fixed_args[param] = str(value)
                        elif expected_type == int:
                            fixed_args[param] = int(value)
                        elif expected_type == bool:
                            if isinstance(value, str):
                                fixed_args[param] = value.lower() in ('true', '1', 'yes')
                            else:
                                fixed_args[param] = bool(value)
                    except (ValueError, TypeError):
                        errors.append(
                            f"参数 {param} 类型错误: 期望 {expected_type.__name__}, "
                            f"得到 {type(value).__name__}"
                        )
    
    # 3. 检查字符串参数的语法
    for param, value in fixed_args.items():
        if isinstance(value, str):
            if not check_brackets(value):
                errors.append(f"参数 {param} 括号不匹配")
                fixed_args[param] = fix_brackets(value)
            if not check_quotes(value):
                errors.append(f"参数 {param} 引号不匹配")
                fixed_args[param] = fix_quotes(value)
    
    return len(errors) == 0, fixed_args, errors


def validate_python_code(code: str) -> Tuple[bool, List[str]]:
    """
    验证 Python 代码语法
    
    Args:
        code: Python 代码
        
    Returns:
        (is_valid, errors)
    """
    errors = []
    
    # 检查缩进
    lines = code.split('\n')
    for i, line in enumerate(lines):
        if line.strip() and not line.startswith('#'):
            # 检查是否混合 tab 和空格
            if '\t' in line and ' ' in line[:len(line) - len(line.lstrip())]:
                errors.append(f"第 {i+1} 行: 混合使用 tab 和空格缩进")
    
    # 检查常见语法错误
    try:
        compile(code, '<string>', 'exec')
    except SyntaxError as e:
        errors.append(f"语法错误: {e.msg} (行 {e.lineno})")
    
    return len(errors) == 0, errors


def fix_python_indentation(code: str) -> str:
    """
    修复 Python 代码缩进
    
    Args:
        code: Python 代码
        
    Returns:
        修复后的代码
    """
    lines = code.split('\n')
    fixed_lines = []
    
    for line in lines:
        # 统一使用 4 空格缩进
        if line.startswith('\t'):
            # tab 转 4 空格
            indent = len(line) - len(line.lstrip('\t'))
            line = '    ' * indent + line.lstrip('\t')
        fixed_lines.append(line)
    
    return '\n'.join(fixed_lines)
