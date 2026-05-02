# Security Audit Report

**Generated:** 2026-03-22T22:19:23.191479

## Summary

- Critical: 4
- High: 1
- Medium: 0
- Low: 1
- Info: 0
- **Total: 6**

## CRITICAL (4)

- **cmd_doctor** (src/ascend/commands/init.py:53) [NOT COVERED]
  - Pattern: variable: api_key
  - Complexity: 17
  - Suggestion: Ensure branch on 'api_key' is tested with both truthy and falsy values
- **cmd_report_stale** (src/ascend/commands/report.py:620) [NOT COVERED]
  - Pattern: variable: api_key
  - Complexity: 26
  - Suggestion: Ensure branch on 'api_key' is tested with both truthy and falsy values
- **_run_linear** (src/ascend/commands/sync.py:246) [NOT COVERED]
  - Pattern: variable: api_key
  - Complexity: 9
  - Suggestion: Ensure branch on 'api_key' is tested with both truthy and falsy values
- **_run_slack** (src/ascend/commands/sync.py:277) [NOT COVERED]
  - Pattern: variable: token
  - Complexity: 5
  - Suggestion: Ensure branch on 'token' is tested with both truthy and falsy values

## HIGH (1)

- **get_client** (src/ascend/summarizer.py:90) [NOT COVERED]
  - Pattern: variable: api_key
  - Complexity: 3
  - Suggestion: Ensure branch on 'api_key' is tested with both truthy and falsy values

## LOW (1)

- **fetch_channel_activity** (src/ascend/integrations/slack.py:108) [covered]
  - Pattern: variable: token
  - Complexity: 10
  - Suggestion: Ensure branch on 'token' is tested with both truthy and falsy values
