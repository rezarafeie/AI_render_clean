#!/bin/sh
cd /home/claude/intro/b3d
for c in "wide day" "wide dusk" "wide night" "wide morning" "med day" "med night" "screen day" "screen night" "mascot dusk" "mascot night" "low night"; do set -- $c
  [ -f out/$1_$2.png ] || nice -n 5 python3 scene.py -- $1 $2 out/$1_$2.png 40 80 > out/$1_$2.log 2>&1
  echo "done $1 $2 $(date +%T)"
done
echo ALLDONE
