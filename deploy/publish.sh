#!/bin/sh
# Publish site/ to the gh-pages branch of the public repository, as one single commit (no history growth).
# Run every 2 minutes by xc-publish.timer. It reads how GitHub Pages builds the site (read-only token):
# - "legacy" (branch builder, about 10 builds per hour at most): publishes at most every 6 minutes;
# - "workflow" (Settings > Pages > Source = GitHub Actions): publishes every run, with deploy/pages-workflow.yml.
set -eu
cd "$HOME/xcl-campaigns"
REPO="${XC_PAGES_REPO:-git@github.com:GreemSC/xcl-campaigns.git}"
API="${XC_PAGES_API:-https://api.github.com/repos/GreemSC/xcl-campaigns/pages}"
export GIT_SSH_COMMAND="ssh -i $HOME/xcl-campaigns/.deploy-key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
W="$HOME/xcl-campaigns/.pages"
[ -d site ] || exit 0
MODE=$(curl -s -m 15 -H "Authorization: Bearer $(cat .github-token)" "$API" \
       | python3 -c 'import sys,json; print(json.load(sys.stdin).get("build_type",""))' 2>/dev/null || true)
if [ "$MODE" != workflow ] && [ -n "$(find "$W.last" -mmin -6 2>/dev/null)" ]; then exit 0; fi
# Content fingerprint without the timestamps, so an unchanged board is not re-published.
NEW=$(flock site.lock find site -type f | sort | xargs cat | sed -E 's/[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC//g' | sha256sum | cut -c1-16)
[ "$NEW" = "$(cat "$W.last" 2>/dev/null || true)" ] && exit 0
rm -rf "$W" && mkdir -p "$W"
flock site.lock cp -a site/. "$W/"     # render.py holds this lock while it writes site/
if [ "$MODE" = workflow ]; then         # deploy with GitHub Actions (no 10 builds/hour limit), see pages-workflow.yml
    mkdir -p "$W/.github/workflows" && cp deploy/pages-workflow.yml "$W/.github/workflows/pages.yml"
fi
cd "$W"
git init -q -b gh-pages
git -c user.name="xcl-campaigns bot" -c user.email="xcl-campaigns@users.noreply.github.com" add -A
git -c user.name="xcl-campaigns bot" -c user.email="xcl-campaigns@users.noreply.github.com" commit -q -m "Board update $(date -u +%Y-%m-%dT%H:%MZ) ($MODE)"
git push -q -f "$REPO" gh-pages
echo "$NEW" > "$W.last"
echo "${MODE:-legacy} $(date -u +%Y-%m-%d\ %H:%M) UTC" > "$HOME/xcl-campaigns/.pages-mode"   # shown on the health page
echo "published $(date -u +%H:%M:%S) mode=$MODE"
