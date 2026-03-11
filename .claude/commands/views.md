Run the website analytics script to check page views, unique visitors, and IP addresses.

Run this command:

```bash
cd /Users/kyllhutchens/Code/AFL\ App/backend && pip3 install -q sqlalchemy psycopg2-binary 2>/dev/null; python3 ../scripts/check_views.py $ARGUMENTS
```

Arguments (optional):
- `--hours N`: Look back N hours (default: 24)
- `--ips`: Show detailed IP address list

Present the results clearly to the user.
