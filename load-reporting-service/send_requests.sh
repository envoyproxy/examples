#!/usr/bin/env bash

PORT_PROXY=${PORT_PROXY:-80}

counter=1
while [ $counter -le 50 ]
do
  curl -v "localhost:${PORT_PROXY}/service/load"
  ((counter++))
done
