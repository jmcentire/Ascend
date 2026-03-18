# Ascend

AI-powered engineering management CLI. Track your team, analyze performance, prepare for 1:1s, and detect risks — all from the terminal.

## What It Does

- **Roster Management** — Members, teams, flags, bulk import from CSV
- **Meeting Transcripts** — Parse transcripts, auto-summarize, extract action items, analyze sentiment (Claude AI)
- **Performance Tracking** — Aggregate GitHub commits, Linear issues, Slack activity into daily snapshots
- **Risk Detection** — Algorithmic alerts for flight risk, burnout, bus factor, underperformance
- **Coaching** — STAR assessments, 1:1 prep plans, AI-powered coaching suggestions
- **Reports** — Individual, team, git analytics, progress trends, free-form AI reports
- **Planning** — Goals (OKRs), PIPs, career development tracking
- **Scheduling** — Automated task scheduling with macOS launchd integration
- **Interactive TUI** — Full terminal UI with mouse support, keyboard navigation, command palette

## Quick Start

### Install

```bash
# Clone and install
git clone git@github.com:jmcentire/Ascend.git
cd Ascend
pip install -e .

# Initialize workspace
ascend init
```

### Configure

```bash
# Set your Anthropic API key for AI features
export ASCEND_ANTHROPIC_API_KEY="sk-ant-..."

# Optional: Linear and Slack integration
export LINEAR_API_KEY="lin_api_..."
export SLACK_BOT_TOKEN="xoxb-..."

# View and edit config
ascend config show
ascend config set github_org your-org
```

### Import Your Team

```bash
# From CSV (columns: name, email, slack, github)
ascend roster import team.csv

# Or add individually
ascend roster add "Alice Smith" --email alice@co.com --github alicesmith --title "Senior Engineer"

# Create teams
ascend team create "Platform" --lead alicesmith
ascend team add Platform alicesmith
```

### Sync Data

```bash
# Pull GitHub + Linear + Slack data and take performance snapshots
ascend sync

# Or sync individual sources
ascend sync github
ascend sync linear
ascend sync snapshot
```

### Ingest Meeting Transcripts

```bash
# Single file
ascend meeting ingest transcript.txt --member alicesmith

# Entire directory
ascend meeting ingest ~/transcripts/

# Preview without ingesting
ascend meeting ingest ~/transcripts/ --dry-run
```

### View Reports

```bash
# Org-wide dashboard
ascend report dashboard

# Individual performance
ascend report performance --member alicesmith

# Team health
ascend report team --team Platform

# Stale high-priority tickets (48h weekday / 72h Monday)
ascend report stale
ascend report stale --save   # writes to reports directory
ascend report stale --all    # include old backlog items

# Risk dashboard
ascend coach risks

# Free-form AI report
ascend report custom "Who needs the most attention this week?"
```

### Launch the TUI

```bash
ascend tui
```

Navigate with number keys (1-6), arrow keys, mouse clicks. Press `Ctrl+P` for the command palette, `?` for help.

## Command Reference

### Init & Config
| Command | Description |
|---------|-------------|
| `ascend init` | Initialize `~/.ascend` workspace |
| `ascend doctor` | Check config, DB, API keys |
| `ascend config show` | Display configuration |
| `ascend config set KEY VALUE` | Update a config value |

### Roster
| Command | Description |
|---------|-------------|
| `ascend roster list` | List members (filterable: `--team`, `--flag`, `--status`) |
| `ascend roster add NAME` | Add member (`--email`, `--github`, `--title`, `--team`) |
| `ascend roster edit MEMBER` | Edit member fields |
| `ascend roster show MEMBER` | Full member profile |
| `ascend roster flag MEMBER FLAG` | Set flag (oncall, pto, pip, flight_risk) |
| `ascend roster unflag MEMBER FLAG` | Remove flag |
| `ascend roster search QUERY` | Search across name, email, GitHub, title |
| `ascend roster import FILE` | Bulk import from CSV or team-tracker dir |

### Teams
| Command | Description |
|---------|-------------|
| `ascend team list` | List teams |
| `ascend team create NAME` | Create team (`--lead`, `--parent`) |
| `ascend team add TEAM MEMBER` | Add member to team |
| `ascend team show TEAM` | Team details |

### Meetings
| Command | Description |
|---------|-------------|
| `ascend meeting ingest FILE` | Parse and store transcript(s) |
| `ascend meeting list` | List meetings (`--member`, `--from`, `--to`) |
| `ascend meeting show ID` | Full meeting details |
| `ascend meeting search QUERY` | Full-text search (FTS5) |
| `ascend meeting items` | List action items (`--member`, `--status`) |
| `ascend meeting item close ID` | Close an action item |
| `ascend meeting prep MEMBER` | AI-generated 1:1 prep plan |

### Sync
| Command | Description |
|---------|-------------|
| `ascend sync` | Run all integrations + snapshots |
| `ascend sync github` | Fetch GitHub commits and PRs |
| `ascend sync linear` | Fetch Linear issues |
| `ascend sync slack` | Fetch Slack channel activity |
| `ascend sync snapshot` | Take performance snapshots |

### Reports
| Command | Description |
|---------|-------------|
| `ascend report performance` | Individual metrics (`--member`, `--team`) |
| `ascend report team` | Team health overview |
| `ascend report progress` | Snapshot trends over time |
| `ascend report git` | Git analytics |
| `ascend report dashboard` | Org-wide summary |
| `ascend report stale` | Stale high-priority/urgent tickets (`--save`, `--all`) |
| `ascend report custom PROMPT` | Free-form AI-powered report |

### Planning
| Command | Description |
|---------|-------------|
| `ascend plan cycle` | Current planning cycle |
| `ascend plan goal create TITLE` | Create goal/OKR |
| `ascend plan goal list` | List goals |
| `ascend plan goal update ID` | Update progress |
| `ascend plan pip create MEMBER` | Create PIP |
| `ascend plan pip show MEMBER` | PIP status |
| `ascend plan career MEMBER` | Career development plan |

### Coaching
| Command | Description |
|---------|-------------|
| `ascend coach analyze MEMBER` | Comprehensive AI analysis |
| `ascend coach risks` | Risk dashboard (algorithmic) |
| `ascend coach star MEMBER` | Record STAR assessment |
| `ascend coach suggest MEMBER` | AI coaching suggestions for next 1:1 |

### Schedules
| Command | Description |
|---------|-------------|
| `ascend schedule list` | List schedules |
| `ascend schedule add NAME CMD` | Add (`--daily`, `--weekdays`, `--weekly DAY`) |
| `ascend schedule remove NAME` | Remove schedule |
| `ascend schedule run NAME` | Run immediately |
| `ascend schedule enable NAME` | Enable |
| `ascend schedule disable NAME` | Disable |

### TUI
| Command | Description |
|---------|-------------|
| `ascend tui` | Launch interactive terminal interface |

All commands support `--json` for machine-readable output. Report and show commands support `--copy` to copy output to clipboard.

## Architecture

```
~/.ascend/
  config.yaml          # Configuration
  ascend.db            # SQLite database (WAL mode)
  history/audit.jsonl  # Operation audit log
  transcripts/         # Ingested transcript files
  schedules/           # launchd plists

src/ascend/
  cli.py               # Entry point, argument parsing
  config.py            # Pydantic config model
  db.py                # SQLite schema + connection
  audit.py             # JSONL audit log
  output.py            # Terminal formatting + clipboard
  transcript.py        # Transcript parser
  summarizer.py        # Claude AI integration
  scheduler.py         # Cron + launchd
  models/member.py     # Pydantic data models
  commands/            # Command handlers (roster, meeting, sync, report, plan, coach, schedule)
  integrations/        # GitHub, Linear, Slack fetchers + snapshot scoring
  tui/                 # Interactive terminal interface (Textual)
    app.py             # Main app, sidebar, command palette
    screens/           # Dashboard, Roster, Meetings, Reports, Coaching, Schedules
    widgets/           # MemberCard, MetricBar
    styles/app.tcss    # Styles
```

## Requirements

- Python >= 3.12
- macOS (for clipboard and launchd scheduling)
- Optional: Anthropic API key for AI features (summarization, coaching, custom reports)
- Optional: GitHub CLI (`gh`) for PR data
- Optional: Linear API key, Slack bot token for integrations

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run specific test file
pytest tests/test_tui.py -v
```

## License

MIT License. See [LICENSE](LICENSE) for details.
