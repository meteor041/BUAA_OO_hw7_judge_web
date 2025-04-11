# score.py
import argparse
import re
import sys
from typing import Dict, Optional, Tuple

# --- Constants ---
TIME_PRECISION = 1e-6

# --- Parsing Patterns ---
# Input pattern to get passenger request time and priority
INPUT_PASSENGER_PATTERN = re.compile(r"\[(\d+\.\d+)\](\d+)-PRI-(\d+)-FROM-([A-Z0-9]+)-TO-([A-Z0-9]+)$")

# Output patterns to get completion time and action counts
OUTPUT_OUT_S_PATTERN = re.compile(r"\[(\d+\.\d+)\]OUT-S-(\d+)-([A-Z0-9]+)-(\d+)$")
OUTPUT_ACTION_PATTERN = re.compile(r"\[(\d+\.\d+)\](ARRIVE|OPEN|CLOSE)-.*") # General pattern for actions and final time

class PassengerScoreInfo:
    def __init__(self, request_time: float, priority: int):
        self.request_time = request_time
        self.priority = priority
        self.completion_time: Optional[float] = None

def calculate_score(input_filepath: str, output_filepath: str, real_time: Optional[float]):
    """Parses input and output files to calculate performance metrics."""

    passengers: Dict[int, PassengerScoreInfo] = {}
    t_final: float = 0.0
    arrive_count: int = 0
    open_count: int = 0
    close_count: int = 0

    # 1. Parse Input File for Passenger Info
    try:
        with open(input_filepath, 'r') as f:
            for line in f:
                match = INPUT_PASSENGER_PATTERN.match(line.strip())
                if match:
                    timestamp, p_id_str, prio_str, _, _ = match.groups()
                    p_id = int(p_id_str)
                    priority = int(prio_str)
                    request_time = float(timestamp)
                    if p_id in passengers:
                        # This shouldn't happen with valid gen.py, but check anyway
                        print(f"Warning: Duplicate passenger ID {p_id} found in input file.", file=sys.stderr)
                    passengers[p_id] = PassengerScoreInfo(request_time=request_time, priority=priority)
    except FileNotFoundError:
        print(f"Error: Input file not found: {input_filepath}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading input file {input_filepath}: {e}", file=sys.stderr)
        sys.exit(1)

    if not passengers:
        print("Warning: No passenger requests found in the input file.", file=sys.stderr)
        # Allow scoring to proceed, WT will be 0 or undefined

    # 2. Parse Output File for Completion Times and Action Counts
    try:
        with open(output_filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # Check for OUT-S first
                out_match = OUTPUT_OUT_S_PATTERN.match(line)
                if out_match:
                    timestamp_str, p_id_str, _, _ = out_match.groups()
                    timestamp = float(timestamp_str)
                    p_id = int(p_id_str)

                    if p_id in passengers:
                        # Record the *first* completion time for a passenger
                        if passengers[p_id].completion_time is None:
                            passengers[p_id].completion_time = timestamp
                    else:
                        # Passenger in output but not input? Judge should have caught this.
                        print(f"Warning: OUT-S for passenger {p_id} found in output, but not in input.", file=sys.stderr)

                    # Update t_final based on this action
                    t_final = max(t_final, timestamp)
                    continue # Move to next line after processing OUT-S

                # Check for general actions (ARRIVE, OPEN, CLOSE) and update t_final
                action_match = OUTPUT_ACTION_PATTERN.match(line)
                if action_match:
                    timestamp_str, action_type = action_match.groups()
                    timestamp = float(timestamp_str)
                    t_final = max(t_final, timestamp) # Update final timestamp

                    if action_type == "ARRIVE":
                        arrive_count += 1
                    elif action_type == "OPEN":
                        open_count += 1
                    elif action_type == "CLOSE":
                        close_count += 1

    except FileNotFoundError:
        print(f"Error: Output file not found: {output_filepath}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading output file {output_filepath}: {e}", file=sys.stderr)
        sys.exit(1)

    # 3. Calculate Metrics

    # T_max_score
    t_max_score = t_final
    if real_time is not None:
        t_max_score = max(t_final, real_time)

    # Weighted Average Completion Time (WT)
    total_weighted_time = 0.0
    total_priority = 0
    missing_completion = False
    for p_id, info in passengers.items():
        if info.completion_time is None:
            print(f"Error: Passenger {p_id} never completed (no OUT-S found). Cannot calculate score.", file=sys.stderr)
            missing_completion = True
            # Judge should prevent this, but handle defensively.
            # Depending on rules, might assign a penalty time or exit.
            # For now, we'll prevent WT calculation.
            break # Stop calculation if any passenger failed

        if info.priority <= 0:
             print(f"Warning: Passenger {p_id} has non-positive priority {info.priority}. Skipping for WT calculation.", file=sys.stderr)
             continue # Skip passengers with invalid priority for WT

        completion_duration = info.completion_time - info.request_time
        if completion_duration < -TIME_PRECISION:
             print(f"Warning: Passenger {p_id} completed at {info.completion_time:.1f} before request time {info.request_time:.1f}. Check output.", file=sys.stderr)
             # Proceed with calculation, but flag the issue.

        total_weighted_time += completion_duration * info.priority
        total_priority += info.priority

    wt = 0.0
    if missing_completion:
        wt = float('inf') # Indicate failure
        print("WT calculation skipped due to incomplete passengers.", file=sys.stderr)
    elif total_priority > 0:
        wt = total_weighted_time / total_priority
    elif passengers: # Passengers exist, but total_priority is 0 (e.g., all skipped)
         print("Warning: Total priority sum is zero. WT calculation resulted in 0.", file=sys.stderr)
         wt = 0.0
    # else: wt remains 0.0 if no passengers


    # System Power Consumption (W)
    power_consumption = 0.4 * arrive_count + 0.1 * open_count + 0.1 * close_count

    # 4. Output Results
    print(f"T_max_score: {t_max_score:.4f}")
    if not missing_completion:
        print(f"WT: {wt:.4f}")
    else:
        print(f"WT: INF (Incomplete passengers)")
    print(f"W: {power_consumption:.4f}")

    # Optional: Print counts for debugging
    # print(f"Debug: T_final={t_final:.4f}, Arrive={arrive_count}, Open={open_count}, Close={close_count}")


# --- Argument Parsing ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate performance score for elevator simulation.")
    parser.add_argument("input_file", help="Path to the input command file (e.g., input.txt).")
    parser.add_argument("output_file", help="Path to the elevator program's output log file (e.g., output.txt).")
    parser.add_argument("--real_time", type=float, help="(Optional) Actual execution time of the program.")

    args = parser.parse_args()

    calculate_score(args.input_file, args.output_file, args.real_time)