#!/bin/sh
# Publish site/ to the gh-pages branch of the public repository, as one single commit (no history growth).
# Run every 6 minutes by xc-publish.timer: GitHub Pages builds at most ~10 times per hour from a branch.
set -eu
cd "$HOME/xcl-campaigns"
REPO="${XC_PAGES_REPO:-git@github.com:GreemSC/xcl-campaigns.git}"
export GIT_SSH_COMMAND="ssh -i $HOME/xcl-campaigns/.deploy-key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
W="$HOME/xcl-campaigns/.pages"
[ -d site ] || exit 0
# Content fingerprint without the timestamps, so an unchanged board is not re-published.
NEW=$(find site -type f | sort | xargs cat | sed -E 's/[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC//g' | sha256sum | cut -c1-16)
[ "$NEW" = "$(cat "$W.last" 2>/dev/null || true)" ] && exit 0
rm -rf "$W" && mkdir -p "$W" && cp -a site/. "$W/"
cd "$W"
git init -q -b gh-pages
git -c user.name="xcl-campaigns bot" -c user.email="xcl-campaigns@users.noreply.github.com" add -A
git -c user.name="xcl-campaigns bot" -c user.email="xcl-campaigns@users.noreply.github.com" commit -q -m "Board update $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q -f "$REPO" gh-pages
echo "$NEW" > "$W.last"
echo "published $(date -u +%H:%M:%S)"
