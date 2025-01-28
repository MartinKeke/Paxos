#!/bin/bash
id=$1
configfile=$2
python3 mypaxos.py proposer $id $configfile
