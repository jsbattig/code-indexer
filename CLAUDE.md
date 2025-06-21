- When bumping the version label, you need to always update the readme installs instructions to the command to install matches the latest version
- If you are troubleshooting docker-related issues that appear to be related to security, DON'T try modifying dockerfiles by adding user setup to the dockerfiles. You will make things worse and confuse the troubleshooting process. The files are fine without user setup. Look somewhere else.
- When working on modifying the behavior of a well documented function or if adding a new user-accesible function or --setting to the application you will always read and update the readme file, and you will make sure the --help command reflects the true state of the behavior and functionality of the application
- Don't use fallbacks to using Claude CLI in this project. If you find an issue, you research using your web search tools, and you propose a solution. Claude CLI must be used always when using the "claude" tool within this project. Claude CLI has full access to the disk, and all its files, which is the entire point of the "claude" function. Any fallback is mooth, makes no sense, it's a waste of time and money. Don't go ever, don't even propose a "fallback". A fallback in this context is simply cheating, and we don't want cheating.
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

  The Claude CLI integration uses subprocess calls to avoid JSON serialization issues. Always start with the minimal working configuration and
  avoid the problematic patterns listed above.

  This prompt captures the key learnings and provides clear guidance to avoid repeating this debugging process.
- When I ask you to lint, or when you decide on your own that you need to lint, always run ruff, black and mypy. We will refer to all as "linting".
- When I tell you about failed tests in the context of full-automation.sh, it's so you know, you are not supposed to run that script from your Claude context, they are two slow. You are going to research why they may fail in that context, run them individually to troubleshoot. Eventually, when ready, ask the user to run the full-automation.sh himself/herself
- For end to end test, integration tests, long running tests, that rely on real services, you are not going to stop or uninstall services, but rather on test setup you will ensure that what you need running (using the applications capabilities, don't manipulate containers from the outside) is running. If ollama is needed, and is not running because prior tests used voyage, you will stop, re-init adding ollama, and start services. If then services need Voyage, you will re-init, and ensure the collection is clean so the vector data matches the size of voyage vs. ollama. In essence, we are going to leave stuff running at the end of our tests, but ensure pre-requisites for our tests are met on test setup. The worst you can do is start uninstalling stuff at the end, you are making it harder for the next test and they are already slow to run.
- Tests that are part of our full-automation.sh script are relatively slow tests. To speed them up, we don't shutdown containers or services in the test teardown, but rather leave them running. Instead, the tests should have a comprehensive "setup" procedure that checks for pre-requesites to enable the test to execute properly. They can ensure containers are running (using high level functionality provided by our application, don't manipulate containers directly), they can cleanup or re-create qdrant collections, they can re-init the app with the proper params, and call "start" again if necessary, in esence, they ensure the conditions are properly set for the test to run properly. We are doing this as a strategy to accelerate test execution. In the past, we were tearing down everything on tear down of the test, and they take way too long to run. Keep this in mind any time you are writing an integration test, end to end e2e test, and any test that uses th real ollama, qdrant or voyage services.