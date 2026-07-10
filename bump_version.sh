#!/bin/bash
# Bump version and create release commit + tag
# Usage: ./bump_version.sh 0.3.0

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <new_version>"
    echo "Example: $0 0.3.0"
    exit 1
fi

NEW_VERSION="$1"

# Validate version format
if ! echo "$NEW_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "❌ Error: Version must be in format X.Y.Z (e.g., 0.3.0)"
    exit 1
fi

# Check if git working directory is clean
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ Error: Git working directory is not clean"
    echo "Please commit or stash your changes first"
    git status --short
    exit 1
fi

# Get current version
CURRENT_VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')

echo "📦 Version Bump"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Current version: $CURRENT_VERSION"
echo "New version:     $NEW_VERSION"
echo ""

# Ask for confirmation
read -p "Proceed with version bump? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Update pyproject.toml
sed -i '' "s/^version = .*/version = \"$NEW_VERSION\"/" pyproject.toml

echo "✅ Updated pyproject.toml"

# Git operations
echo ""
echo "📝 Creating git commit and tag..."
git add pyproject.toml
git commit -m "chore: bump version to $NEW_VERSION"
git tag -a "v$NEW_VERSION" -m "Release version $NEW_VERSION"

echo "✅ Created commit and tag v$NEW_VERSION"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Version bump complete!"
echo ""
echo "Next steps:"
echo "  1. Push: git push origin $(git branch --show-current) --tags"
echo "  2. Create GitHub Release: https://github.com/rapkin/osm2geojson/releases/new"
echo "     - Select tag: v$NEW_VERSION"
echo "     - This will automatically publish to PyPI!"
echo ""
echo "Or to undo:"
echo "  git reset --hard HEAD~1"
echo "  git tag -d v$NEW_VERSION"
