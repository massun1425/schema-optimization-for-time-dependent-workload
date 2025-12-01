#!/bin/bash

if [[ "$OSTYPE" == "darwin"* ]]; then
    RUSTLIB=librustlib.dylib
else
    RUSTLIB=librustlib.so
fi
PYLIB=rustlib.so
SCRIPT_DIR=`dirname "$0"`
LIB_DIR=$SCRIPT_DIR/target/release
INSTALL_DIR=$SCRIPT_DIR/..

export RUSTFLAGS="-C link-arg=-undefined -C link-arg=dynamic_lookup"
cargo +nightly build --release || exit $?
cp "$LIB_DIR/$RUSTLIB" "$INSTALL_DIR/$PYLIB" || exit $?
echo "Installed $INSTALL_DIR/$PYLIB"
