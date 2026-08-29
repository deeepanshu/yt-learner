# Grafana dashboards

Dashboards in `dashboards/*.json` are owned by this repo.

On deploy, the homelab manager copies them into the shared observability stack
(`files/apps/`) and reloads Grafana over HTTP.

See: [homelab app-dashboards docs](https://github.com/deeepanshu/homelab/blob/main/observability/docs/app-dashboards.md)

| File | Grafana folder | UID |
|------|----------------|-----|
| `dashboards/yt-learner.json` | Apps | `yt-learner` |
