"""
Visual display demonstration and manual testing.

Run this script to see the actual display behavior and verify visually
that the layouts and streaming work correctly.
"""

import time

from rich.console import Console

from src.code_indexer.utils.status_display import (
    FreeScrollStreamDisplay,
    StatusEvent,
    StatusDisplayManager,
    StatusDisplayMode,
    VisualCues,
)


def demo_free_scroll_display():
    """Demonstrate the free scroll display with dynamic status band."""
    print("=== Free Scroll Display Demo ===")
    print("This will show the dynamic status band and tool activities.")
    print("Press Ctrl+C to stop the demo.\n")

    console = Console()
    display = FreeScrollStreamDisplay(
        console=console, max_status_lines=4, max_info_lines=2
    )

    try:
        # Start display
        display.start("Demo: Claude Analysis")
        time.sleep(1)

        # Simulate initial status
        display.update_status_info(
            ["⏱️ Query starting... | Tools used: cidx(0) grep(0)"]
        )
        time.sleep(1)

        # Simulate tool activities with timing
        tools = [
            ("🔍✨", "Semantic search: 'authentication system'"),
            ("📖", "Reading: src/auth/handlers.py"),
            ("🔍✨", "Semantic search: 'user login'"),
            ("📖", "Reading: src/models/user.py"),
            ("🌿", "Git: git diff HEAD~1"),
            ("📖", "Reading: tests/test_auth.py"),
        ]

        for i, (visual_cue, message) in enumerate(tools):
            # Update running clock
            elapsed = (i + 1) * 3
            total_cidx = sum(1 for _, msg in tools[: i + 1] if "Semantic search" in msg)
            total_tools = i + 1

            status_lines = [
                f"⏱️ Query running: {elapsed}s | Tools used: cidx({total_cidx}) grep(0)"
            ]

            if total_tools > 2:
                avg_time = elapsed / total_tools
                status_lines.append(
                    f"📊 Total operations: {total_tools} | Avg time per tool: {avg_time:.1f}s"
                )

            display.update_status_info(status_lines)

            # Add tool activity
            event = StatusEvent(
                message=message, visual_cue=visual_cue, event_type="tool_activity"
            )
            display.update(event)

            time.sleep(2)

        # Final status
        display.update_status_info(
            [
                "✅ Query completed in 18s | Final tool count: cidx(2) grep(0)",
                "📊 Total operations: 6 | Avg time per tool: 3.0s",
            ]
        )

        time.sleep(2)

        # Show final summary
        summary = """## 🤖 Claude's Problem-Solving Approach

Claude used 6 tools during analysis:

- ✅ **Preferred Approach**: Used semantic search (2x) with `cidx` for intelligent code discovery
   • Semantic search: 'authentication system'
   • Semantic search: 'user login'

- 📖 **Code Exploration**: Accessed 4 files for detailed analysis

- ⏱️ **Performance**: Average tool execution time 3.0s

## 📊 Tool Usage Statistics
• **Total Operations**: 6
• **Tools Used**: Bash, Read
• **Completed Successfully**: 6
• **Total Execution Time**: 18.00s
• **Average Duration**: 3.0s

**Operation Breakdown**:
• 🔍✨ cidx_semantic_search: 2
• 📄 file_operation: 3  
• 🌿 git_operation: 1"""

        display.show_final_summary(summary)
        time.sleep(3)

    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
    finally:
        display.stop()
        print("\nDemo completed.")


def demo_layout_transitions():
    """Demonstrate layout transitions between single and dual modes."""
    print("\n=== Layout Transition Demo ===")
    print("This will show how layout changes between single and dual modes.")
    print("Watch the display structure change.\n")

    console = Console()
    display = FreeScrollStreamDisplay(
        console=console, max_status_lines=3, max_info_lines=1
    )

    try:
        # Start with single layout (tool activities only)
        display.start("Demo: Layout Transitions")
        time.sleep(1)

        console.print("Phase 1: Single layout (tool activities only)")

        event = StatusEvent(
            message="Initial tool activity", visual_cue="📖", event_type="tool_activity"
        )
        display.update(event)
        time.sleep(3)

        console.print("Phase 2: Adding status info (transitioning to dual layout)")

        # Add status info to trigger dual layout
        display.update_status_info(["⏱️ Status info added - layout should expand"])
        time.sleep(3)

        console.print("Phase 3: Adding more activities to dual layout")

        # Add more activities
        activities = [
            ("🔍✨", "Semantic search activity"),
            ("🌿", "Git operation"),
            ("📖", "Another file read"),
        ]

        for visual_cue, message in activities:
            event = StatusEvent(
                message=message, visual_cue=visual_cue, event_type="tool_activity"
            )
            display.update(event)
            time.sleep(1.5)

        console.print("Phase 4: Updating status info dynamically")

        # Update status info
        display.update_status_info(["⏱️ Updated status - layout structure maintained"])
        time.sleep(2)

    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
    finally:
        display.stop()
        print("\nLayout transition demo completed.")


def demo_streaming_behavior():
    """Demonstrate streaming content behavior."""
    print("\n=== Streaming Behavior Demo ===")
    print("This demonstrates how streaming content and status updates work together.")
    print("Notice how content streams freely while status stays fixed.\n")

    console = Console()
    manager = StatusDisplayManager(
        mode=StatusDisplayMode.FREE_SCROLL_STREAM,
        console=console,
        handle_interrupts=False,
    )

    try:
        manager.start("Demo: Streaming Behavior")
        time.sleep(1)

        # Simulate streaming content chunks
        content_chunks = [
            "## Analyzing authentication system...\n\n",
            "Looking at the user authentication flow, I can see several key components:\n\n",
            "1. **Login Handler** (`src/auth/handlers.py`)\n",
            "   - Handles user credentials validation\n",
            "   - Manages session creation\n\n",
            "2. **User Model** (`src/models/user.py`)\n",
            "   - Defines user schema\n",
            "   - Contains password hashing logic\n\n",
            "3. **Authentication Middleware**\n",
            "   - Validates requests\n",
            "   - Handles token verification\n\n",
            "The system uses **JWT tokens** for stateless authentication.\n\n",
        ]

        # Stream content while updating status
        for i, chunk in enumerate(content_chunks):
            # Update status
            elapsed = (i + 1) * 2
            manager.update_status_info([f"⏱️ Streaming content: {elapsed}s"])

            # Stream content
            manager.update_content(chunk)

            # Occasionally add tool activity
            if i % 2 == 0:
                manager.update(
                    message=f"Processing chunk {i+1}",
                    visual_cue="📖",
                    event_type="tool_activity",
                )

            time.sleep(2)

        # Final status and summary
        manager.update_status_info(["✅ Streaming completed in 16s"])
        time.sleep(1)

        final_summary = "## Summary\n\nStreaming demo completed successfully. Content flowed freely while status remained fixed."
        manager.show_final_summary(final_summary)
        time.sleep(2)

    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
    finally:
        manager.stop()
        print("\nStreaming demo completed.")


def demo_performance_test():
    """Demonstrate performance with rapid updates."""
    print("\n=== Performance Demo ===")
    print("This will rapidly update the display to test performance.")
    print("Watch for smooth updates without lag.\n")

    console = Console()
    display = FreeScrollStreamDisplay(
        console=console, max_status_lines=5, max_info_lines=2
    )

    try:
        display.start("Demo: Performance Test")
        time.sleep(1)

        start_time = time.time()

        # Rapid updates
        for i in range(30):
            elapsed = time.time() - start_time

            # Update status rapidly
            display.update_status_info(
                [
                    f"⏱️ Rapid test: {elapsed:.1f}s | Update #{i+1}",
                    f"📊 Updates per second: {(i+1)/elapsed:.1f}",
                ]
            )

            # Add tool activity
            event = StatusEvent(
                message=f"Rapid activity {i+1}",
                visual_cue=(
                    VisualCues.FILE_READ if i % 2 == 0 else VisualCues.SEMANTIC_SEARCH
                ),
                event_type="tool_activity",
            )
            display.update(event)

            time.sleep(0.2)  # 5 updates per second

        final_time = time.time() - start_time
        display.update_status_info(
            [
                f"✅ Performance test completed in {final_time:.1f}s",
                f"📊 Average: {30/final_time:.1f} updates/sec",
            ]
        )

        time.sleep(2)

    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
    finally:
        display.stop()
        print("\nPerformance demo completed.")


def main():
    """Run all demos."""
    print("🎭 Status Display Framework Visual Demo")
    print("=" * 50)
    print()
    print("This demo will show various aspects of the status display framework:")
    print("1. Free scroll display with dynamic status band")
    print("2. Layout transitions between single and dual modes")
    print("3. Streaming content behavior")
    print("4. Performance with rapid updates")
    print()

    try:
        # Run demos
        demo_free_scroll_display()
        demo_layout_transitions()
        demo_streaming_behavior()
        demo_performance_test()

        print("\n🎉 All demos completed successfully!")
        print("The status display framework is working correctly.")

    except KeyboardInterrupt:
        print("\n\n🛑 Demos interrupted by user.")
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
