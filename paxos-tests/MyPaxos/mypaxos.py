import socket
import struct
import time
import threading
import sys
import os
import random
from collections import deque
import traceback

def load_config(config_path):
    config = {}
    try:
        with open(config_path, "r") as file:
            for line in file:
                line = line.strip()
                if line:
                    parts = line.split()
                    if len(parts) != 3:
                        print(f"Warning: Invalid line in config '{line}'. Expected format: key ip port.", file=sys.stderr)
                        continue
                    key, ip, port = parts
                    config[key] = (ip, int(port))
                    print(f"Loaded config: {key} -> ({ip}, {port})", file=sys.stderr)
        return config
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

def create_multicast_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2**30)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2**30)
    sock.settimeout(0.02)
    ttl = struct.pack('b', 2)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    return sock

def join_multicast_group(sock, multicast_addr, port):
    sock.bind(('', port))
    mreq = struct.pack("4sl", socket.inet_aton(multicast_addr), socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    return sock

def proposer(CONFIG, proposer_id):
    proposer_socket = create_multicast_socket()
    learner_socket = create_multicast_socket()
    
    proposer_addr, proposer_port = CONFIG['proposers']
    learner_addr, learner_port = CONFIG['learners']
    
    join_multicast_group(proposer_socket, proposer_addr, proposer_port)
    learner_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    
    proposer_socket.settimeout(0.5)
    min_backoff = 0.05
    max_backoff = 1.0
    current_backoff = min_backoff
    
    print(f"Starting Proposer {proposer_id}", file=sys.stderr)
    
    round_number = proposer_id
    proposals = {}
    regular_pending_values = deque(maxlen=10000)
    end_message_queue = deque()
    active_round = None
    phase2_sent = False
    phase1b_responses = set()  # Set to track unique acceptor responses
    phase2b_responses = set()  # Set to track unique acceptor responses
    decided_values = set()
    current_value = None
    
    round_start_time = None
    ROUND_TIMEOUT = 1.5
    
    client_value_counts = {}
    values_decided = 0
    end_messages_received = set()
    expected_clients = 2
    
    total_acceptors = 3  # Total number of acceptors in the system
    ACCEPTOR_MAJORITY = (total_acceptors // 2) + 1
    
    while True:
        try:
            current_time = time.time()
            
            if active_round and round_start_time and (current_time - round_start_time > ROUND_TIMEOUT):
                active_round = None
                current_value = None
                phase2_sent = False
                phase1b_responses.clear()
                phase2b_responses.clear()
                round_start_time = None
                current_backoff = min(current_backoff * 1.5, max_backoff)
                time.sleep(0.001)
                continue

            msg = None
            try:
                msg, addr = proposer_socket.recvfrom(2**16)
                msg = msg.decode()
            except socket.timeout:
                pass

            if msg and msg.startswith("END_"):
                parts = msg.split('_')
                if len(parts) > 2:  # Format: END_clientId_valueCount
                    client_id = int(parts[1])
                    value_count = int(parts[2])
                    client_value_counts[client_id] = value_count
                if msg not in end_messages_received:
                    end_messages_received.add(msg)
                    end_message_queue.append(msg)
                    print(f"Proposer {proposer_id}: Received END message: {msg}", file=sys.stderr)
            
            elif msg and msg.startswith("DECISION"):
                _, value = msg.split()
                if value not in decided_values:
                    decided_values.add(value)
                    if not value.startswith("END_"):
                        values_decided += 1
                    if value.startswith("END_"):
                        if value in end_message_queue:
                            end_message_queue.remove(value)
                    else:
                        if value in regular_pending_values:
                            regular_pending_values.remove(value)
                    print(f"Proposer {proposer_id}: Learned decided value {value} from another proposer", file=sys.stderr)

            elif msg and not msg.startswith("PHASE"):
                value = msg.strip()
                if value not in decided_values and value not in regular_pending_values:
                    regular_pending_values.append(value)
                    print(f"Proposer {proposer_id}: Received new value: {value}", file=sys.stderr)
                    

            if not active_round and regular_pending_values and not current_value:
                current_value = regular_pending_values[0]
                round_number += len(CONFIG['proposers'])
                active_round = round_number
                proposals[round_number] = current_value
                phase1b_responses.clear()
                phase2b_responses.clear()
                phase2_sent = False
                round_start_time = current_time
                
                print(f"Proposer {proposer_id}: Proposing value {current_value} in round {round_number}", file=sys.stderr)
                
                phase1a_message = f"PHASE1A {round_number}"
                proposer_socket.sendto(phase1a_message.encode(), CONFIG['acceptors'])

            elif not active_round and not regular_pending_values and end_message_queue and not current_value:
                current_value = end_message_queue[0]
                round_number += len(CONFIG['proposers'])
                active_round = round_number
                proposals[round_number] = current_value
                phase1b_responses.clear()
                phase2b_responses.clear()
                phase2_sent = False
                round_start_time = current_time
                
                print(f"Proposer {proposer_id}: Proposing END message {current_value} in round {round_number}", file=sys.stderr)
                
                phase1a_message = f"PHASE1A {round_number}"
                proposer_socket.sendto(phase1a_message.encode(), CONFIG['acceptors'])

            if msg and msg.startswith("PHASE1B"):
                parts = msg.split()
                if len(parts) >= 3:  # Must include round and acceptor_id at minimum
                    rnd = int(parts[1])
                    acceptor_id = parts[2]
                    if rnd == active_round and not phase2_sent:
                        phase1b_responses.add(acceptor_id)  # Track unique acceptor responses
                        
                        print(f"Proposer {proposer_id}: Received PHASE1B from acceptor {acceptor_id} for round {rnd}. Count: {len(phase1b_responses)}", file=sys.stderr)
                        
                        if len(phase1b_responses) >= ACCEPTOR_MAJORITY:
                            print(f"Proposer {proposer_id}: Sending PHASE2A for round {rnd} with value {proposals[rnd]}", file=sys.stderr)
                            
                            phase2a_message = f"PHASE2A {rnd} {proposals[rnd]}"
                            proposer_socket.sendto(phase2a_message.encode(), CONFIG['acceptors'])
                            phase2_sent = True
                            current_backoff = min_backoff

            elif msg and msg.startswith("PHASE2B"):
                parts = msg.split()
                if len(parts) >= 4:  # Must include round, value, and acceptor_id
                    rnd = int(parts[1])
                    val = parts[2]
                    acceptor_id = parts[3]
                    if rnd == active_round and val == proposals[rnd]:
                        phase2b_responses.add(acceptor_id)  # Track unique acceptor responses
                        
                        print(f"Proposer {proposer_id}: Received PHASE2B from acceptor {acceptor_id} for round {rnd}. Count: {len(phase2b_responses)}", file=sys.stderr)
                        
                        if len(phase2b_responses) >= ACCEPTOR_MAJORITY:
                            decided_value = proposals[active_round]
                            decided_values.add(decided_value)
                            if not decided_value.startswith("END_"):
                                values_decided += 1
                            
                            print(f"Proposer {proposer_id}: Decided value {decided_value}", file=sys.stderr)
                            
                            decision_message = f"DECISION {decided_value}"
                            learner_socket.sendto(decision_message.encode(), CONFIG['learners'])
                            proposer_socket.sendto(decision_message.encode(), CONFIG['proposers'])
                            
                            if decided_value.startswith("END_"):
                                if decided_value in end_message_queue:
                                    end_message_queue.remove(decided_value)
                            else:
                                if decided_value in regular_pending_values:
                                    regular_pending_values.remove(decided_value)
                            
                            current_value = None
                            active_round = None
                            phase2_sent = False
                            phase1b_responses.clear()
                            phase2b_responses.clear()
                            current_backoff = min_backoff

            total_expected_values = sum(client_value_counts.values())
            if (not active_round and 
                not regular_pending_values and 
                not end_message_queue and 
                len(end_messages_received) >= expected_clients and
                total_expected_values > 0 and
                values_decided >= total_expected_values):
                
                end_message = f"END_{proposer_id}_{values_decided}"
                proposer_socket.sendto(end_message.encode(), CONFIG['acceptors'])
                proposer_socket.sendto(end_message.encode(), CONFIG['learners'])
                print(f"Proposer {proposer_id}: Sent {end_message}, terminating. Processed {values_decided}/{total_expected_values} values", file=sys.stderr)
                break

        except socket.timeout:
            if active_round:
                if active_round in proposals:
                    value = proposals[active_round]
                    if value not in decided_values:
                        time.sleep(current_backoff)
                        current_backoff = min(current_backoff * 1.5, max_backoff)
                        print(f"Proposer {proposer_id}: Timeout in round {active_round}. Backoff: {current_backoff}", file=sys.stderr)
                active_round = None
                phase2_sent = False
                phase1b_responses.clear()
                phase2b_responses.clear()
                current_value = None
            continue

        except Exception as e:
            print(f"Proposer {proposer_id} error: {str(e)}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

def acceptor(CONFIG, id):
    acceptor_socket = create_multicast_socket()
    acceptor_addr, acceptor_port = CONFIG['acceptors']
    join_multicast_group(acceptor_socket, acceptor_addr, acceptor_port)
    
    print(f"Starting Acceptor {id}", file=sys.stderr)
    
    promised_rnd = 0
    accepted_rnd = 0
    accepted_val = None
    last_message_time = time.time()
    MIN_MESSAGE_INTERVAL = 0.0005

    while True:
        try:
            msg, addr = acceptor_socket.recvfrom(2**16)
            msg = msg.decode().strip()
            
            current_time = time.time()
            time_since_last = current_time - last_message_time
            if time_since_last < MIN_MESSAGE_INTERVAL:
                time.sleep(MIN_MESSAGE_INTERVAL - time_since_last)
            last_message_time = current_time
            
            print(f"Acceptor {id} received: {msg}", file=sys.stderr)

            if msg.startswith("PHASE1A"):
                _, rnd = msg.split()
                rnd = int(rnd)
                
                if rnd >= promised_rnd:
                    promised_rnd = rnd
                    response = f"PHASE1B {rnd} {id}"  # Include acceptor ID
                    if accepted_rnd > 0:
                        response = f"{response} {accepted_rnd} {accepted_val}"
                    acceptor_socket.sendto(response.encode(), CONFIG['proposers'])

            elif msg.startswith("PHASE2A"):
                
                _, rnd, value = msg.split()
                rnd = int(rnd)
                
                if rnd >= promised_rnd:
                    promised_rnd = rnd
                    accepted_rnd = rnd
                    accepted_val = value
                    response = f"PHASE2B {rnd} {value} {id}"  # Include acceptor ID
                    acceptor_socket.sendto(response.encode(), CONFIG['proposers'])

            elif msg.startswith("END_"):
                break

        except socket.timeout:
            continue
        except Exception as e:
            print(f"Acceptor {id} error: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)


def learner(CONFIG, id):
    learner_socket = create_multicast_socket()
    proposer_socket = create_multicast_socket()
    
    learner_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2**18)
    
    learner_addr, learner_port = CONFIG['learners']
    join_multicast_group(learner_socket, learner_addr, learner_port)
    
    print(f"Starting Learner {id}", file=sys.stderr)
    
    learned_values = set()
    learned_values_ordered = []
    last_value_time = time.time()
    
    # Timing controls for resends
    last_resend_time = time.time()
    start_time = time.time()
    RESEND_INTERVAL = 0.5
    RESEND_BATCH_SIZE = 100
    
    client_value_counts = {}
    values_learned = 0
    
    # Add a catch-up mechanism when learner starts
    if id == 2:  # For the late-starting learner
        # Request catch-up from other learners
        catch_up_msg = f"CATCHUP_REQUEST_{id}"
        for _ in range(3):  # Send multiple times for reliability
            learner_socket.sendto(catch_up_msg.encode(), CONFIG['learners'])
            time.sleep(0.01)

    while True:
        try:
            current_time = time.time()
            
            # Controlled resend mechanism
            if current_time - last_resend_time > RESEND_INTERVAL:
                total_expected_values = sum(client_value_counts.values())
                if total_expected_values > 0 and values_learned < total_expected_values:
                    unsent_values = [v for v in learned_values_ordered if not v.startswith("END_")]
                    for i in range(0, len(unsent_values), RESEND_BATCH_SIZE):
                        batch = unsent_values[i:i + RESEND_BATCH_SIZE]
                        for value in batch:
                            resend_msg = f"DECISION {value}"
                            learner_socket.sendto(resend_msg.encode(), CONFIG['learners'])
                            time.sleep(0.001)  # Small delay between messages
                        
                last_resend_time = current_time
            
            msg = None
            try:
                msg, addr = learner_socket.recvfrom(2**16)
                msg = msg.decode().strip()
                current_time = time.time()
            except socket.timeout:
                continue

            if msg.startswith("DECISION"):
                time.sleep(0.0005)
                _, value = msg.split()
                
                # Handle END messages with value counts
                if value.startswith("END_"):
                    parts = value.split('_')
                    if len(parts) > 2:  # Format: END_clientId_valueCount
                        client_id = int(parts[1])
                        value_count = int(parts[2])
                        client_value_counts[client_id] = value_count
                
                if value not in learned_values:
                    learned_values.add(value)
                    learned_values_ordered.append(value)
                    last_value_time = current_time
                    
                    if not value.startswith("END_"):
                        values_learned += 1
                        print(value)
                        sys.stdout.flush()
                        
                        # Always forward decisions to help other learners catch up
                        learner_socket.sendto(msg.encode(), CONFIG['learners'])
                        time.sleep(0.0005)

            # Add handling for catch-up requests
            elif msg.startswith("CATCHUP_REQUEST"):
                # Send all known values to the requesting learner
                for value in learned_values_ordered:
                    if not value.startswith("END_"):
                        catch_up_msg = f"DECISION {value}"
                        learner_socket.sendto(catch_up_msg.encode(), CONFIG['learners'])
                        time.sleep(0.001)  # Small delay to prevent overwhelming network

            # Modified termination condition
            total_expected_values = sum(client_value_counts.values())
            if (len(client_value_counts) >= 2 and  # Received counts from both clients
                total_expected_values > 0 and      # Have valid counts
                values_learned >= total_expected_values):  # Learned all values
                if current_time - last_value_time > 3.0:  # Wait a bit to ensure no more values
                    print(f"Learner {id}: Total values learned: {values_learned}/{total_expected_values}", 
                          file=sys.stderr)
                    break

        except socket.timeout:
            continue
            
        except Exception as e:
            print(f"Learner {id} error: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

def client(CONFIG, client_id):
    client_socket = create_multicast_socket()
    proposer_addr, proposer_port = CONFIG['proposers']
    
    print(f"Client {client_id}: Starting. Will send to {proposer_addr}:{proposer_port}", file=sys.stderr)
    
    start_time = time.time()
    values_sent = 0
    last_report_time = time.time()
    
    try:
        while True:
            try:
                value = input().strip()
                if value:
                    print(f"Client {client_id}: Sending value: {value}", file=sys.stderr)
                    for _ in range(3):
                        client_socket.sendto(value.encode(), (proposer_addr, proposer_port))
                        time.sleep(0.01)  # Reduced delay
                    values_sent += 1
                    
                    current_time = time.time()
                    if current_time - last_report_time >= 1.0:
                        print(f"Client {client_id}: Sent {values_sent} values so far", file=sys.stderr)
                        last_report_time = current_time
            except EOFError:
                print(f"Client {client_id}: Reached end of input", file=sys.stderr)
                break
        
        # Send end message with value count
        time.sleep(10.0)
        end_message = f"END_{client_id}_{values_sent}"
        for _ in range(3):
            print(f"Client {client_id}: Sending end message: {end_message}", file=sys.stderr)
            client_socket.sendto(end_message.encode(), (proposer_addr, proposer_port))
            time.sleep(0.5)
        
        time.sleep(1.0)
        
        elapsed_time = time.time() - start_time
        print(f"Client {client_id}: Finished. Total time for {values_sent} values: {elapsed_time:.2f} seconds ({values_sent/elapsed_time:.2f} values/second)", file=sys.stderr)
        
    finally:
        client_socket.close()



if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 mypaxos.py <role> <id> <config_file>", file=sys.stderr)
        sys.exit(1)
    
    role = sys.argv[1]
    node_id = int(sys.argv[2])
    config_file = sys.argv[3]
    
    CONFIG = load_config(config_file)

    if role == "proposer":
        proposer(CONFIG, node_id)
    elif role == "acceptor":
        acceptor(CONFIG, node_id)
    elif role == "learner":
        learner(CONFIG, node_id)
    elif role == "client":
        client(CONFIG, node_id)