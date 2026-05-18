#!/usr/bin/env bash
set -euo pipefail

export QT_QPA_PLATFORMTHEME=generic
export QT_STYLE_OVERRIDE=Fusion

python Helper.py
