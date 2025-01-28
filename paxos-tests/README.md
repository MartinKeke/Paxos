# Paxos Implementation

This is an implementation of the Paxos consensus protocol using IP multicast, supporting atomic broadcast with multiple proposers, acceptors, and learners.

## Requirements

- Python 3.8 or higher
- A POSIX-compliant system (Linux/Unix/WSL)
- Network support for IP multicast

## Project Structure

```
.
├── MyPaxos/
│   └── mypaxos.py       # Main implementation file
├── acceptor.sh          # Script to start acceptor
├── proposer.sh          # Script to start proposer
├── learner.sh          # Script to start learner
├── client.sh           # Script to start client
├── run.sh              # Script to run mypaxos.py
├── ...
└── README.md           # This file
```

## Running the Implementation

0. First, make sure all scripts have executable permissions:

   chmod +x *.sh
   cd MyPaxos && chmod +x *.sh && cd ..

1. To run a standard test with 2 clients, 2 proposers, 3 acceptors, and 2 learners , for 100 values:
   
   ./run.sh MyPaxos 100

2. To kill running processes:
   ./clean.sh

3. To run the script with 2 acceptors, 100 values:
   ./run_2acceptor.sh MyPaxos 100

4. To run the script with 1 acceptors, 100 values:
   ./run_1acceptor.sh MyPaxos 100

5. To run the script with message loss, 100 values:
   ./run_loss.sh MyPaxos 100

6. To run the script for learners catch-up, 100 values:
   ./run_catch_up.sh MyPaxos 100   

## Implementation Details

The implementation follows the basic Paxos protocol with the following features:
- Uses IP multicast for all communication
- Supports multiple concurrent proposers without leader election
- Maintains total order of messages
- Handles crash failures
- In-memory state management (no persistent storage)

## Known Limitations and Behaviors


1. **Message Loss Handling**: 
   - The implementation includes retry mechanisms and backoff strategies.
   - Under high load (1000+ values), some message loss might occur, for example running for 1000 values results in 1950. values learned, and running for 10000 values results in around 15000 values learned.

3. **No Leader Election**:
   - As per project specifications, there is no leader election mechanism
   - Multiple proposers might compete, leading to temporary delays in consensus

## Testing

The implementation has been tested against all required scenarios:
1. Multiple values per client (100, 1000, 10000)
2. Reduced acceptor count (2 acceptors, 1 acceptor)
3. Message loss scenarios
4. Acceptor failure scenarios
5. Learner catch-up scenarios

Best performance is achieved with:
- Moderate message rates
- All three acceptors running
- Proper timing between component startups (as shown in run scripts)
- Enough time to process every value (when using run.sh , etc)

## Troubleshooting

If you encounter issues:
1. Ensure all multicast addresses and ports are available
2. Check that no other instances are running (`pkill -f "paxos.conf"`)
3. Allow sufficient time between starting components
4. For catch-up scenarios, ensure adequate wait times as specified in run scripts