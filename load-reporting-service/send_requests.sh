#!/usr/bin/env bash

PORT_PROXY0=${PORT_PROXY0:-80}
PORT_PROXY1=${PORT_PROXY1:-81}

counter=1
while [ $counter -le 50 ]
do
  if ((counter % 2)); then
    port="$PORT_PROXY0"
  else
    port="$PORT_PROXY1"
  fi
  curl -v "localhost:${port}/service/load"
  ((counter++))
done
