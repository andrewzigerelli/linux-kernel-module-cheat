#!/bin/sh
# https://cirosantilli.com/linux-kernel-module-cheat#gem5-restore-new-script
m5 checkpoint
tmp="$(mktemp)"
m5 readfile > "$tmp"
m5 resetstats
sh "$tmp"
m5 exit
