#!/bin/bash
for commit in $(git log --oneline -30 | cut -d' ' -f1); do
    if git show "$commit" 2>/dev/null | grep -q "class EmbeddingProvider.*Enum"; then
        echo "Found in commit: $commit"
        git log --oneline -1 "$commit"
    fi
done