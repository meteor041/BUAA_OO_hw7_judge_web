# gen.py
import argparse
import random
import sys
from typing import List, Tuple, Set, Dict

# --- Constants ---
FLOORS = ["B4", "B3", "B2", "B1", "F1", "F2", "F3", "F4", "F5", "F6", "F7"]
FLOOR_MAP = {name: i for i, name in enumerate(FLOORS)} # Map floor name to index for easier comparison
ELEVATOR_IDS = list(range(1, 7))
SCHE_TARGET_FLOORS = ["B2", "B1", "F1", "F2", "F3", "F4", "F5"]
SCHE_SPEEDS = [0.2, 0.3, 0.4, 0.5]
UPDATE_TARGET_FLOORS = ["B2", "B1", "F1", "F2", "F3", "F4", "F5"]
MIN_SCHE_UPDATE_INTERVAL = 8.0
MIN_START_TIME = 1.0
MAX_STRONG_SCHE = 20
MAX_MUTUAL_COMMANDS = 70
MAX_UPDATE_TIMES = 3 # Implicit limit based on 6 elevators

# --- Helper Functions ---
def get_random_floor(exclude: str = None) -> str:
    """Gets a random floor, optionally excluding one."""
    choices = [f for f in FLOORS if f != exclude]
    return random.choice(choices)

def format_command(timestamp: float, command: str) -> str:
    """Formats the command string with timestamp."""
    return f"[{timestamp:.1f}]{command}"

# --- Main Generation Logic ---
def generate_input(mode: str, request_num: int, duplicate_times: int,
                   time_limit: float, sche_times: int, update_times: int,
                   output_file: str):
    """Generates the input file based on parameters."""

    if time_limit < MIN_START_TIME:
        print(f"Error: time_limit ({time_limit}) must be >= {MIN_START_TIME}", file=sys.stderr)
        sys.exit(1)

    if update_times > MAX_UPDATE_TIMES:
         print(f"Warning: update_times ({update_times}) exceeds maximum possible ({MAX_UPDATE_TIMES}). Setting to {MAX_UPDATE_TIMES}.", file=sys.stderr)
         update_times = MAX_UPDATE_TIMES

    commands: List[Tuple[float, str]] = []
    passenger_id_counter = 1
    last_sche_update_time = [0.0] * 7
    updated_elevators: Set[int] = set()
    sched_elevators_mutual: Set[int] = set() # Only for mutual mode constraint

    # 1. Generate Base Passenger Requests
    base_requests = []
    for _ in range(request_num):
        from_floor = get_random_floor()
        to_floor = get_random_floor(exclude=from_floor)
        priority = random.randint(1, 100)
        # Assign a preliminary timestamp for sorting later, will be refined
        timestamp = random.uniform(MIN_START_TIME, time_limit)
        base_requests.append({
            "from": from_floor, "to": to_floor, "priority": priority, "base_time": timestamp
        })

    # 2. Duplicate Passenger Requests
    for base_req in base_requests:
        for _ in range(duplicate_times):
            # Refine timestamp: ensure it's around base_time but non-decreasing overall later
            timestamp = max(MIN_START_TIME, random.uniform(base_req["base_time"] * 0.9, base_req["base_time"] * 1.1))
            timestamp = min(time_limit, timestamp) # Ensure within limit

            command_str = (f"{passenger_id_counter}-PRI-{base_req['priority']}"
                           f"-FROM-{base_req['from']}-TO-{base_req['to']}")
            commands.append((timestamp, command_str))
            passenger_id_counter += 1

    # 3. Generate SCHE Requests
    actual_sche_times = 0
    max_sche = MAX_STRONG_SCHE if mode == 'strong' else len(ELEVATOR_IDS) # Mutual: max 1 per elevator
    sche_limit = min(sche_times, max_sche)

    available_for_sche = list(set(ELEVATOR_IDS) - updated_elevators)
    if mode == 'mutual':
        available_for_sche = list(set(available_for_sche) - sched_elevators_mutual)

    random.shuffle(available_for_sche)

    for i in range(sche_limit):
        if not available_for_sche:
            print(f"Warning: Not enough available elevators for {sche_limit} SCHE requests. Generated {actual_sche_times}.", file=sys.stderr)
            break

        elevator_id = available_for_sche.pop()
        target_floor = random.choice(SCHE_TARGET_FLOORS)
        speed = random.choice(SCHE_SPEEDS)

        # Ensure time constraints
        timestamp = max(MIN_START_TIME, last_sche_update_time[target_floor] + MIN_SCHE_UPDATE_INTERVAL)
        timestamp = random.uniform(timestamp, time_limit) # Add some randomness
        timestamp = min(time_limit, timestamp) # Ensure within limit

        if timestamp > time_limit: # Cannot generate more within time limit
             print(f"Warning: Cannot generate SCHE request within time limit. Generated {actual_sche_times}.", file=sys.stderr)
             break

        command_str = f"SCHE-{elevator_id}-{speed}-{target_floor}"
        commands.append((timestamp, command_str))
        last_sche_update_time[target_floor] = timestamp
        actual_sche_times += 1
        if mode == 'mutual':
            sched_elevators_mutual.add(elevator_id)


    # 4. Generate UPDATE Requests
    actual_update_times = 0
    available_for_update = list(set(ELEVATOR_IDS) - updated_elevators)

    for _ in range(update_times):
        if len(available_for_update) < 2:
            print(f"Warning: Not enough available elevators for UPDATE request. Generated {actual_update_times}.", file=sys.stderr)
            break

        elevator_a, elevator_b = random.sample(available_for_update, 2)
        target_floor = random.choice(UPDATE_TARGET_FLOORS)

        # Ensure time constraints
        timestamp = MIN_START_TIME
        timestamp = random.uniform(timestamp, time_limit) # Add some randomness
        timestamp = min(time_limit, timestamp) # Ensure within limit

        if timestamp > time_limit: # Cannot generate more within time limit
             print(f"Warning: Cannot generate UPDATE request within time limit. Generated {actual_update_times}.", file=sys.stderr)
             break

        command_str = f"UPDATE-{elevator_a}-{elevator_b}-{target_floor}"
        commands.append((timestamp, command_str))
        last_sche_update_time = timestamp
        actual_update_times += 1

        # Remove updated elevators from available lists
        updated_elevators.add(elevator_a)
        updated_elevators.add(elevator_b)
        available_for_update.remove(elevator_a)
        available_for_update.remove(elevator_b)
        if elevator_a in available_for_sche: available_for_sche.remove(elevator_a)
        if elevator_b in available_for_sche: available_for_sche.remove(elevator_b)
        if mode == 'mutual':
             if elevator_a in sched_elevators_mutual: sched_elevators_mutual.remove(elevator_a)
             if elevator_b in sched_elevators_mutual: sched_elevators_mutual.remove(elevator_b)


    # 5. Sort and Finalize Commands
    commands.sort(key=lambda x: x[0])

    # Ensure timestamps are strictly non-decreasing after sort and apply final formatting
    final_commands: List[str] = []
    current_time = 0.0
    for i, (ts, cmd) in enumerate(commands):
        # Ensure non-decreasing timestamp, respecting MIN_START_TIME
        adjusted_ts = max(MIN_START_TIME, ts, current_time)
        # Ensure interval for SCHE/UPDATE if it's the first command or previous wasn't SCHE/UPDATE
        is_sche_update = cmd.startswith("SCHE") or cmd.startswith("UPDATE")
        if i > 0 and is_sche_update:
             prev_ts, prev_cmd = commands[i-1]
             is_prev_sche_update = prev_cmd.startswith("SCHE") or prev_cmd.startswith("UPDATE")
             if is_prev_sche_update:
                  adjusted_ts = max(adjusted_ts, round(prev_ts + MIN_SCHE_UPDATE_INTERVAL, 1))

        # Ensure timestamp is within the overall limit
        adjusted_ts = min(time_limit, adjusted_ts)

        # Check mutual mode command limit
        if mode == 'mutual' and len(final_commands) >= MAX_MUTUAL_COMMANDS:
             print(f"Warning: Reached mutual mode command limit ({MAX_MUTUAL_COMMANDS}). Truncating.", file=sys.stderr)
             break

        # Check mutual mode time limits
        if mode == 'mutual':
            if adjusted_ts < 1.0: # Should be handled by max(MIN_START_TIME, ...)
                adjusted_ts = 1.0
            if adjusted_ts > 70.0:
                 print(f"Warning: Command timestamp {adjusted_ts:.1f} exceeds mutual mode time limit (70.0). Truncating.", file=sys.stderr)
                 break # Stop adding commands if time limit exceeded

        final_commands.append(format_command(round(adjusted_ts, 1), cmd))
        current_time = round(adjusted_ts, 1) # Update current time based on the written command

        # If we adjusted the time significantly, we might violate the time_limit for subsequent commands
        if current_time >= time_limit and i < len(commands) - 1:
             print(f"Warning: Timestamp adjustments reached time limit ({time_limit}). Further commands truncated.", file=sys.stderr)
             break


    # 6. Write to Output File
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in final_commands:
                f.write(line + '\n')
        print(f"Successfully generated {len(final_commands)} commands to {output_file}")
    except IOError as e:
        print(f"Error writing to file {output_file}: {e}", file=sys.stderr)
        sys.exit(1)

# --- Argument Parsing ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate elevator simulation input data.")
    parser.add_argument("--mode", choices=['strong', 'mutual'], default='strong', help="Generation mode: 'strong' or 'mutual'.")
    parser.add_argument("--request_num", type=int, default=10, help="Base number of passenger requests (0-100).")
    parser.add_argument("--duplicate_times", type=int, default=1, help="Duplication factor for each base request (1-100).")
    parser.add_argument("--time_limit", type=float, default=10, help="Maximum timestamp for generated requests (>= 1.0).")
    parser.add_argument("--sche_times", type=int, default=1, help="Number of SCHE instructions to generate (>= 0).")
    parser.add_argument("--update_times", type=int, default=1, help="Number of UPDATE instructions to generate (0-3).")
    parser.add_argument("-o", "--output", default="input.txt", help="Output file name (default: input.txt).")

    args = parser.parse_args()

    # Basic validation
    if not (0 <= args.request_num <= 100):
        parser.error("request_num must be between 0 and 100.")
    if not (1 <= args.duplicate_times <= 100):
         parser.error("duplicate_times must be between 1 and 100.")
    if args.time_limit < MIN_START_TIME:
         parser.error(f"time_limit must be >= {MIN_START_TIME}.")
    if args.sche_times < 0:
         parser.error("sche_times must be >= 0.")
    if not (0 <= args.update_times <= MAX_UPDATE_TIMES):
         parser.error(f"update_times must be between 0 and {MAX_UPDATE_TIMES}.")
    if args.mode == 'mutual' and args.time_limit > 70.0:
         print("Warning: time_limit > 70.0 for mutual mode. Commands generated after 70.0s might be truncated.", file=sys.stderr)


    generate_input(args.mode, args.request_num, args.duplicate_times,
                   args.time_limit, args.sche_times, args.update_times,
                   args.output)