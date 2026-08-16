#!/usr/bin/env bash
set -euo pipefail

echo "Building Asura Scans WASM module..."

# Build the WASM binary
cargo build --release --target wasm32-unknown-unknown

# Strip debug symbols to reduce size
if command -v wasm-strip &> /dev/null; then
    echo "Stripping WASM binary..."
    wasm-strip target/wasm32-unknown-unknown/release/asurascans.wasm
fi

echo "✓ Build complete"
ls -lh target/wasm32-unknown-unknown/release/*.wasm
