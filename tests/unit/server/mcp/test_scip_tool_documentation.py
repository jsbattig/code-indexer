"""Tests for SCIP tool documentation in MCP tool registry."""


class TestScipCallchainDocumentation:
    """Tests for scip_callchain tool documentation."""

    def test_scip_callchain_has_enhanced_documentation(self):
        """Should verify that scip_callchain tool description includes all required sections."""
        from code_indexer.server.mcp.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY.get("scip_callchain")
        assert tool is not None, "scip_callchain tool not found in TOOL_REGISTRY"

        description = tool.get("description", "")
        assert description, "scip_callchain description is empty"

        # Verify TL;DR is present
        assert "TL;DR:" in description, "Missing TL;DR section"

        # Verify SUPPORTED SYMBOL FORMATS section
        assert (
            "SUPPORTED SYMBOL FORMATS:" in description
        ), "Missing SUPPORTED SYMBOL FORMATS section"
        assert (
            'Simple names: "chat", "invoke"' in description
        ), "Missing simple names example"
        assert (
            'Class#method: "CustomChain#chat"' in description
        ), "Missing Class#method example"
        assert (
            "Full SCIP identifiers:" in description
        ), "Missing full SCIP identifiers example"

        # Verify USAGE EXAMPLES section
        assert "USAGE EXAMPLES:" in description, "Missing USAGE EXAMPLES section"
        assert "Method to method:" in description, "Missing method to method example"
        assert "Class to class:" in description, "Missing class to class example"
        assert "Within class:" in description, "Missing within class example"

        # Verify KNOWN LIMITATIONS section
        assert "KNOWN LIMITATIONS:" in description, "Missing KNOWN LIMITATIONS section"
        assert (
            "May not capture FastAPI endpoint decorators" in description
        ), "Missing FastAPI limitation"
        assert (
            "Factory functions may not show call chains" in description
        ), "Missing factory functions limitation"
        assert (
            "Cross-repository search:" in description
        ), "Missing cross-repository search tip"

        # Verify RESPONSE INCLUDES section
        assert "RESPONSE INCLUDES:" in description, "Missing RESPONSE INCLUDES section"
        assert "path:" in description, "Missing path field description"
        assert "length:" in description, "Missing length field description"
        assert "has_cycle:" in description, "Missing has_cycle field description"
        assert "diagnostic:" in description, "Missing diagnostic field description"
        assert (
            "scip_files_searched:" in description
        ), "Missing scip_files_searched field description"
        assert (
            "repository_filter:" in description
        ), "Missing repository_filter field description"

        # Verify TIPS FOR BEST RESULTS section
        assert (
            "TIPS FOR BEST RESULTS:" in description
        ), "Missing TIPS FOR BEST RESULTS section"
        assert (
            "Start with simple class or method names" in description
        ), "Missing tip about simple names"
        assert (
            "Use repository_alias to limit search scope" in description
        ), "Missing tip about repository_alias"
        assert (
            "Increase max_depth if chains seem incomplete" in description
        ), "Missing tip about max_depth"
        assert (
            "Check diagnostic message if 0 chains found" in description
        ), "Missing tip about diagnostic message"
