"""
Code formatting and validation layer
Standardizes LLM-generated code using real formatters and linters
"""

import re
import subprocess
import tempfile
import os
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class CodeFormatter:
    """Format and validate code using language-specific tools"""

    # Language-specific formatters
    FORMATTERS = {
        'python': ['black', '--quiet', '--line-length', '88'],
        'python_fallback': ['autopep8', '--aggressive', '--aggressive'],
        'javascript': ['prettier', '--parser', 'babel'],
        'typescript': ['prettier', '--parser', 'typescript'],
        'json': ['prettier', '--parser', 'json'],
        'css': ['prettier', '--parser', 'css'],
        'html': ['prettier', '--parser', 'html'],
        'go': ['gofmt'],
        'rust': ['rustfmt'],
    }

    # Language-specific linters
    LINTERS = {
        'python': ['flake8', '--select=E9,F63,F7,F82', '--show-source'],
        'javascript': ['eslint', '--no-eslintrc', '--no-ignore'],
        'typescript': ['eslint', '--no-eslintrc', '--no-ignore'],
    }

    @staticmethod
    def extract_code_blocks(text: str) -> list[Dict[str, str]]:
        """Extract all code blocks from markdown text"""
        # Pattern for fenced code blocks with optional language
        pattern = r'```(\w+)?\n(.*?)```'
        matches = re.finditer(pattern, text, re.DOTALL)

        code_blocks = []
        for match in matches:
            language = match.group(1) or 'text'
            code = match.group(2).strip()
            code_blocks.append({
                'language': language.lower(),
                'code': code,
                'original': match.group(0)
            })

        return code_blocks

    @staticmethod
    def check_tool_available(tool: str) -> bool:
        """Check if a tool is installed"""
        try:
            subprocess.run(
                ['which', tool],
                capture_output=True,
                check=True,
                timeout=2
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            return False

    @staticmethod
    def format_code(code: str, language: str) -> Tuple[str, bool, str]:
        """
        Format code using language-specific formatter

        Returns:
            (formatted_code, success, error_message)
        """
        if language not in CodeFormatter.FORMATTERS:
            # No formatter for this language, return as-is
            return code, True, ""

        formatter_cmd = CodeFormatter.FORMATTERS[language]
        tool = formatter_cmd[0]

        # Check if tool is available
        if not CodeFormatter.check_tool_available(tool):
            # Try fallback for Python
            if language == 'python' and 'python_fallback' in CodeFormatter.FORMATTERS:
                fallback_cmd = CodeFormatter.FORMATTERS['python_fallback']
                fallback_tool = fallback_cmd[0]
                if CodeFormatter.check_tool_available(fallback_tool):
                    formatter_cmd = fallback_cmd
                    tool = fallback_tool
                else:
                    logger.warning(f"No formatter available for {language} (tried {tool}, {fallback_tool})")
                    return code, True, f"Formatter {tool} not installed"
            else:
                logger.warning(f"Formatter {tool} not available for {language}")
                return code, True, f"Formatter {tool} not installed"

        # Write code to temp file
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{language}', delete=False) as f:
                f.write(code)
                temp_path = f.name

            # Run formatter
            try:
                result = subprocess.run(
                    formatter_cmd + [temp_path],
                    capture_output=True,
                    timeout=10,
                    text=True
                )

                # Read formatted code
                with open(temp_path, 'r') as f:
                    formatted = f.read()

                if result.returncode == 0:
                    return formatted, True, ""
                else:
                    logger.warning(f"Formatter {tool} failed: {result.stderr}")
                    return code, False, result.stderr

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except:
                    pass

        except Exception as e:
            logger.error(f"Error formatting {language} code: {e}")
            return code, False, str(e)

    @staticmethod
    def lint_code(code: str, language: str) -> Tuple[bool, list[str]]:
        """
        Lint code to find syntax errors

        Returns:
            (is_valid, errors)
        """
        if language not in CodeFormatter.LINTERS:
            # No linter for this language, assume valid
            return True, []

        linter_cmd = CodeFormatter.LINTERS[language]
        tool = linter_cmd[0]

        # Check if tool is available
        if not CodeFormatter.check_tool_available(tool):
            logger.debug(f"Linter {tool} not available for {language}")
            return True, []

        # Write code to temp file
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{language}', delete=False) as f:
                f.write(code)
                temp_path = f.name

            try:
                result = subprocess.run(
                    linter_cmd + [temp_path],
                    capture_output=True,
                    timeout=10,
                    text=True
                )

                # Parse errors
                errors = []
                if result.returncode != 0 and result.stdout:
                    errors = [line.strip() for line in result.stdout.split('\n') if line.strip()]

                is_valid = len(errors) == 0
                return is_valid, errors

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_path)
                except:
                    pass

        except Exception as e:
            logger.error(f"Error linting {language} code: {e}")
            return True, []  # Assume valid on error

    @staticmethod
    def validate_syntax(code: str, language: str) -> Tuple[bool, Optional[str]]:
        """
        Basic syntax validation without external tools

        Returns:
            (is_valid, error_message)
        """
        if language == 'python':
            try:
                compile(code, '<string>', 'exec')
                return True, None
            except SyntaxError as e:
                return False, f"Syntax error at line {e.lineno}: {e.msg}"

        # Add more language validators as needed
        return True, None

    @staticmethod
    def standardize_response(response: str, language_hint: str = 'python') -> str:
        """
        Standardize LLM response by formatting all code blocks

        Args:
            response: Raw LLM response with markdown
            language_hint: Default language if not specified in code blocks

        Returns:
            Response with formatted code blocks
        """
        # Extract all code blocks
        code_blocks = CodeFormatter.extract_code_blocks(response)

        if not code_blocks:
            logger.debug("No code blocks found in response")
            return response

        logger.info(f"Found {len(code_blocks)} code block(s) to format")

        # Format each code block
        standardized = response
        for block in code_blocks:
            language = block['language'] if block['language'] != 'text' else language_hint
            code = block['code']
            original = block['original']

            # Validate syntax first
            is_valid, syntax_error = CodeFormatter.validate_syntax(code, language)
            if not is_valid:
                logger.warning(f"Syntax error in {language} code: {syntax_error}")
                # Add error comment but keep original code
                formatted_block = f"```{language}\n# ⚠️ Syntax Error: {syntax_error}\n{code}\n```"
                standardized = standardized.replace(original, formatted_block)
                continue

            # Format the code
            formatted_code, success, error = CodeFormatter.format_code(code, language)

            if success and formatted_code != code:
                logger.info(f"Formatted {language} code block ({len(code)} -> {len(formatted_code)} chars)")
                # Replace original with formatted version
                formatted_block = f"```{language}\n{formatted_code}\n```"
                standardized = standardized.replace(original, formatted_block)
            elif not success:
                logger.warning(f"Failed to format {language} code: {error}")
                # Keep original

            # Lint the code (informational)
            is_valid, lint_errors = CodeFormatter.lint_code(formatted_code if success else code, language)
            if not is_valid and lint_errors:
                logger.warning(f"Linting found {len(lint_errors)} issue(s) in {language} code")
                for err in lint_errors[:3]:  # Log first 3 errors
                    logger.warning(f"  - {err}")

        return standardized


def install_formatters():
    """
    Install common formatters and linters
    This should be run during Hydra setup
    """
    tools = {
        'python': ['black', 'autopep8', 'flake8'],
        'javascript': ['prettier', 'eslint'],
    }

    for lang, tool_list in tools.items():
        for tool in tool_list:
            if not CodeFormatter.check_tool_available(tool):
                print(f"Installing {tool} for {lang}...")
                try:
                    if tool in ['black', 'autopep8', 'flake8']:
                        subprocess.run(['pip', 'install', tool], check=True)
                    elif tool in ['prettier', 'eslint']:
                        subprocess.run(['npm', 'install', '-g', tool], check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Failed to install {tool}: {e}")
