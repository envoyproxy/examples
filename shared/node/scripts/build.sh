#!/bin/bash

[[ -d node_modules ]] || { echo "node_modules missing - image must be rebuilt" >&2; exit 1; }
yarn build
