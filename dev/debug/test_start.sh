#!/bin/bash

echo "🔍 Testing start command in test directory"
cd /home/jsbattig/.tmp/shared_test_containers

echo "📁 Current directory: $(pwd)"
echo "📄 Config file exists: $(ls -la .code-indexer/config.json)"

echo ""
echo "🚀 Running init command:"
code-indexer init --force --embedding-provider voyage-ai

echo ""
echo "🚀 Running start command (verbose):"
code-indexer start

echo ""
echo "📊 Running status command:"
code-indexer status