- When bumping the version label, you need to always update the readme installs instructions to the command to install matches the latest version
- If you are troubleshooting docker-related issues that appear to be related to security, DON'T try modifying dockerfiles by adding user setup to the dockerfiles. You will make things worse and confuse the troubleshooting process. The files are fine without user setup. Look somewhere else.
- When working on modifying the behavior of a well documented function or if adding a new user-accesible function or --setting to the application you will always read and update the readme file, and you will make sure the --help command reflects the true state of the behavior and functionality of the application
- Don't use fallbacks to using Claude Code SDK in this project. If you find an issue, you research using your web search tools, and you propose a solution. Claude SDK must be used always when using the "claude" tool within this project. Claude SDK has full access to the disk, and all its files, which is the entire point of the "claude" function. Any fallback is mooth, makes no sense, it's a waste of time and money. Don't go ever, don't even propose a "fallback". A fallback in this context is simply cheating, and we don't want cheating.
- If you encounter JSON serialization errors:
  1. Use the _validate_and_debug_prompt() method to analyze prompt issues
  2. Check for non-ASCII characters, very long lines, or unescaped quotes
  3. Test with minimal Claude options first
  4. Gradually add complexity to isolate the problem

  🚨 Error Symptoms:

  - ExceptionGroup: unhandled errors in a TaskGroup
  - json.decoder.JSONDecodeError: Unterminated string
  - CLIJSONDecodeError: Failed to decode JSON
  - Messages containing tool_use_id or tool_result in error logs

  💡 Remember:

  The Claude Code SDK has internal bugs with multi-turn conversations and complex tool configurations. Always start with the minimal working configuration and
  avoid the problematic patterns listed above.

  This prompt captures the key learnings and provides clear guidance to avoid repeating this debugging process.