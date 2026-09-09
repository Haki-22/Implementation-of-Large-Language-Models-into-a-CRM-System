# Model configuration

Trimmed offline fixture of code.claude.com/docs/en/model-config.md
(structure as of 2026-08-29) for the claude_docs parser tests.

### `default` model setting

The behavior of `default` depends on your account type:

* **Max, Team Premium, Enterprise pay-as-you-go, and Anthropic API**: defaults to Opus 5
* **Claude Platform on AWS, Amazon Bedrock, and Google Cloud's Agent Platform**: defaults to Opus 5
* **Pro, Team Standard, and Enterprise subscription seats**: defaults to Sonnet 5
* **Microsoft Foundry**: defaults to Sonnet 4.5

Enterprise pay-as-you-go means an Enterprise organization billed by usage rather than by subscription seat.

### Extended context

On Max, Team, and Enterprise plans, including both Team Standard and Team Premium seats, Opus is automatically upgraded to 1M context with no additional configuration.
