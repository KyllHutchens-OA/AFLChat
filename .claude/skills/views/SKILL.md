---
name: views
description: Check website analytics and page views
argument-hint: "[hours] [--ips]"
allowed-tools: Bash
---

Run the website analytics script to show page views, unique visitors, and IP addresses.

## Instructions

Run the check_views.py script located at `scripts/check_views.py` using:

```bash
cd /Users/kyllhutchens/Code/AFL\ App/backend && pip3 install -q sqlalchemy psycopg2-binary 2>/dev/null; python3 ../scripts/check_views.py $ARGUMENTS
```

## Arguments

- `--hours N`: Look back N hours instead of the default 24 (e.g., `--hours 48`)
- `--ips`: Show detailed list of all IP addresses with first/last seen times

## Examples

- `/views` - Show last 24 hours of analytics
- `/views --hours 48` - Show last 48 hours
- `/views --ips` - Include detailed IP address breakdown
- `/views --hours 72 --ips` - Last 72 hours with IP details
