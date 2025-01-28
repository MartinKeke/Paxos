#!/bin/bash
id=$1
configfile=$2
echo "Starting Client $id with values from $configfile"
python3 mypaxos.py client $id $configfile
