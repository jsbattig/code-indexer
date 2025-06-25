- When I give a list of e2e, functional, integration, long running tests to troubleshoot and fix, keep in mind that tests don't leave a clean a state at the end to improve running performance, they leave service running and dirty collections. Tests should be aware of this, of noisy neighboor, and have comprehensive setup that ensure conditions are adjusted execute the tests succesfully.

- When I ask you to "lint" you will run the ./lint.sh file and address all and every error reported in a systematic way

- When bumping the version label, you need to always update the readme installs instructions to the command to install matches the latest version
- If you are troubleshooting docker-related issues that appear to be related to security, DON'T try modifying dockerfiles by adding user setup to the dockerfiles. You will make things worse and confuse the troubleshooting process. The files are fine without user setup. Look somewhere else.
- When working on modifying the behavior of a well documented function or if adding a new user-accesible function or --setting to the application you will always read and update the readme file, and you will make sure the --help command reflects the true state of the behavior and functionality of the application
- Don't use fallbacks to using Claude CLI in this project. If you find an issue, you research using your web search tools, and you propose a solution. Claude CLI must be used always when using the "claude" tool within this project. Claude CLI has full access to the disk, and all its files, which is the entire point of the "claude" function. Any fallback is mooth, makes no sense, it's a waste of time and money. Don't go ever, don't even propose a "fallback". A fallback in this context is simply cheating, and we don't want cheating.

- ⚠️  ⚠️  ⚠️  CRITICAL PROGRESS REPORTING WARNING ⚠️  ⚠️  ⚠️  
  The CLI progress bar behavior is EXTREMELY DELICATE and depends on this exact pattern:
  
  ✅ SETUP MESSAGES (show as ℹ️ scrolling):
     progress_callback(0, 0, Path(""), info="Setup message here")
     - total=0 triggers ℹ️ message display in CLI
  
  ✅ FILE PROGRESS (show as progress bar):
     progress_callback(current, total_files, file_path, info="X/Y files (%) | emb/s | threads | filename")
     - total>0 triggers progress bar display in CLI
     - info MUST follow format: "files (%) | emb/s | threads | filename"
  
  ❌ DO NOT CHANGE without understanding the CLI logic in cli.py progress_callback!
  ❌ Breaking this pattern will cause either no progress bar or scrolling spam
  
  Files with progress calls: BranchAwareIndexer, SmartIndexer, HighThroughputProcessor
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
- When I ask you to lint, or when you decide on my own that you need to lint, always run ruff, black and mypy. We will refer to all as "linting".
- When I tell you about failed tests in the context of full-automation.sh, it's so you know, you are not supposed to run that script from your Claude context, they are two slow. You are going to research why they may fail in that context, run them individually to troubleshoot. Eventually, when ready, ask the user to run the full-automation.sh himself/herself
- For end to end test, integration tests, long running tests, that rely on real services, you are not going to stop or uninstall services, but rather on test setup you will ensure that what you need running (using the applications capabilities, don't manipulate containers from the outside) is running. If ollama is needed, and is not running because prior tests used voyage, you will stop, re-init adding ollama, and start services. If then services need Voyage, you will re-init, and ensure the collection is clean so the vector data matches the size of voyage vs. ollama. In essence, we are going to leave stuff running at the end of our tests, but ensure pre-requisites for our tests are met on test setup. The worst you can do is start uninstalling stuff at the end, you are making it harder for the next test and they are already slow to run.
- Tests that are part of our full-automation.sh script are relatively slow tests. To speed them up, we don't shutdown containers or services in the test teardown, but rather leave them running. Instead, the tests should have a comprehensive "setup" procedure that checks for pre-requesites to enable the test to execute properly. They can ensure containers are running (using high level functionality provided by our application, don't manipulate containers directly), they can cleanup or re-create qdrant collections, they can re-init the app with the proper params, and call "start" again if necessary, in esence, they ensure the conditions are properly set for the test to run properly. We are doing this as a strategy to accelerate test execution. In the past, we were tearing down everything on tear down of the test, and they take way too long to run. Keep this in mind any time you are writing an integration test, end to end e2e test, and any test that uses th real ollama, qdrant or voyage services.
- Ensure that slow, e2e, integration and any code that rely on Voyage AI API don't bleed into github actions and ci-github.sh scripts. Those are supposed to be fast tests. All tests are discovered and run on full-automation.sh
- Every time you finish implementing a significant new feature or change, you will execute the lint.sh application, AND you will perform a comprehensive documentation check, the README.md file and the help, against what's implemented in the codebase. You will correct any errors, and you will do a second run after that.
- When working on improvements for the smart indexer, always consider the --reconcile function (non git-aware) and ensure consistency across both indexing processes. Treat the --reconcile aspect as equally important, maintaining feature parity and functionality, except for semantically specific module considerations.
- NEVER, EVER, remove functionality related to our enhanced processing of git projects. The git-awarness aspects, how we optimize processing branches, and keeping track of relationships, deduplication of indexing is what make this project unique. If you ever go into a refactoring rabbit hole and you will start removing functionality to that enables this capability you must stop, immediately, and ask if that's the true intent of the work you been asked to do.
- When working on fixing quick feedback unit tests, or fast tests, always use ./ci-github.sh. This shell file is specifically tuned to run test that run fast, so they can be run efficiently from within Claude Code as a first layer of protection ensuring our tests pass and we didn't introduce regressions.
- When indexing, progress reporting is done real-time, in a single line at the bottom, showing a progress bar, and right next to it we show speed metrics and current file being processed. Don't change this approach without confirmation from the user. This is how it is, and it should be for all indexing operations, we don't show feedback scrolling the console, EVER, NEVER, EVER. Ask for confirmation if you are about to change this behavior. If the user ask you to change it, ask question, confirm the user is sure it wants to remove the single line, fixed to the bottom, progress bar, speed and currently file being processed.