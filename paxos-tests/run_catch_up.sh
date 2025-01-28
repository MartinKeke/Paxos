#!/usr/bin/env bash

projdir="$1"
conf="$(pwd)/paxos.conf"
n="$2"

if [[ x$projdir == "x" || x$n == "x" ]]; then
    echo "Usage: $0 <project dir> <number of values per proposer>"
    exit 1
fi

# Calculate timeouts based on number of values - adjusted for better reliability
# More initial wait to ensure system is stable before starting clients
INITIAL_WAIT=$((20 + n / 50))
# More time before starting learner 2 to ensure first learner has processed enough values
CATCHUP_WAIT=$((n / 10))
# Much more time for completion to ensure all values are properly processed
FINAL_WAIT=$((n / 2 + 90))

# Kill any existing processes using the config
pkill -f "$conf"

# Change to project directory
cd $projdir

# Generate input values
../generate.sh $n >../prop1
../generate.sh $n >../prop2

echo "starting acceptors..."
./acceptor.sh 1 "$conf" &
./acceptor.sh 2 "$conf" &
./acceptor.sh 3 "$conf" &

# Wait for acceptors to initialize
echo "waiting for acceptors to initialize..."
sleep 5

echo "starting learner 1..."
./learner.sh 1 "$conf" >../learn1 &

# Wait for first learner to initialize
echo "waiting for learner 1 to initialize..."
sleep 5

echo "starting proposers..."
./proposer.sh 1 "$conf" &
./proposer.sh 2 "$conf" &

# Wait before starting clients
echo "waiting to start clients ($INITIAL_WAIT seconds)..."
sleep $INITIAL_WAIT

echo "starting client 1..."
./client.sh 1 "$conf" <../prop1 &

# Wait before starting learner 2 (catch-up scenario)
echo "waiting $CATCHUP_WAIT seconds before starting learner 2..."
sleep $CATCHUP_WAIT

echo "starting learner 2..."
./learner.sh 2 "$conf" >../learn2 &

# Wait before starting client 2
echo "waiting 5 seconds before starting client 2..."
sleep 5

echo "starting client 2..."
./client.sh 2 "$conf" <../prop2 &

echo "waiting for completion ($FINAL_WAIT seconds)..."
sleep $FINAL_WAIT

echo "Starting graceful shutdown..."
# Give extra time for final messages to be processed
sleep 10

echo "Shutting down..."
pkill -f "$conf"
wait

cd ..
