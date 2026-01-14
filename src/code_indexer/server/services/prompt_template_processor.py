"""
Prompt Template Processor for Delegation Functions.

Story #719: Execute Delegation Function with Async Job

Processes function templates with parameter substitution and prepends
impersonation instructions for Claude Server delegation.
"""

from typing import Any, Dict


class PromptTemplateProcessor:
    """
    Process delegation function templates with parameter substitution.

    Renders function templates by:
    1. Prepending impersonation instruction with target user
    2. Substituting {{param_name}} placeholders with parameter values
    3. Substituting {{user_prompt}} placeholder with user's additional prompt
    """

    IMPERSONATION_INSTRUCTION = '''CRITICAL: As your FIRST action before any other operations, call the MCP tool `set_session_impersonation` with username "{impersonation_user}". All your subsequent queries to CIDX must use this impersonated identity.

'''

    def render(
        self,
        template: str,
        parameters: Dict[str, Any],
        user_prompt: str,
        impersonation_user: str,
    ) -> str:
        """
        Render template with parameter values and impersonation instruction.

        Processing order:
        1. PREPEND impersonation instruction with impersonation_user
        2. Substitute {{param_name}} placeholders with values from parameters
        3. Substitute {{user_prompt}} placeholder with user's prompt

        Args:
            template: The function prompt template with {{placeholders}}
            parameters: Dictionary mapping parameter names to values
            user_prompt: User's additional prompt/query
            impersonation_user: Username to impersonate in Claude Server

        Returns:
            Fully rendered prompt string with impersonation instruction prepended
        """
        # Step 1: Prepend impersonation instruction
        impersonation_header = self.IMPERSONATION_INSTRUCTION.format(
            impersonation_user=impersonation_user
        )

        # Step 2: Substitute parameter placeholders
        result = template
        for param_name, param_value in parameters.items():
            placeholder = "{{" + param_name + "}}"
            result = result.replace(placeholder, str(param_value))

        # Step 3: Substitute user_prompt placeholder
        result = result.replace("{{user_prompt}}", user_prompt)

        # Combine impersonation header with rendered template
        return impersonation_header + result
