#!/usr/bin/env bash

projdir="$1"
conf="$(pwd)/paxos.conf"
n="$2"

if [[ x$projdir == "x" || x$n == "x" ]]; then
    echo "Usage: $0 <project dir> <number of values per proposer>"
    exit 1
fi

pkill -f "$conf"

cd $projdir

../generate.sh $n >../prop1
../generate.sh $n >../prop2

echo "starting acceptors..."

./acceptor.sh 1 "$conf" &

sleep 2
echo "starting learners..."

./learner.sh 1 "$conf" >../learn1 &
./learner.sh 2 "$conf" >../learn2 &

sleep 2
echo "starting proposers..."

./proposer.sh 1 "$conf" &
./proposer.sh 2 "$conf" &

echo "waiting to start clients"
sleep 5
echo "starting clients..."

./client.sh 1 "$conf" <../prop1 &
./client.sh 2 "$conf" <../prop2 &

if [ "$2" -gt 1000 ]; then
    sleep 30
else
    sleep 15
fi

pkill -f "$conf"
wait

cd ..
