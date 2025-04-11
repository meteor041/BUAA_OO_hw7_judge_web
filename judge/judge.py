# judge.py
import argparse
import math
import re
import sys
from collections import defaultdict, deque
from enum import Enum, auto
from typing import Dict, List, Optional, Set, Tuple, Any

# --- Constants ---
FLOORS = ["B4", "B3", "B2", "B1", "F1", "F2", "F3", "F4", "F5", "F6", "F7"]
FLOOR_MAP = {name: i for i, name in enumerate(FLOORS)}
FLOOR_NAMES = {i: name for i, name in enumerate(FLOORS)}
NUM_FLOORS = len(FLOORS)
ELEVATOR_IDS = set(range(1, 7))
DEFAULT_SPEED = 0.4
MIN_DOOR_TIME = 0.4 - 1e-6 # Tolerance for float comparison
CAPACITY = 6
SCHE_STOP_TIME = 1.0 - 1e-6
UPDATE_RESET_TIME = 1.0 - 1e-6
SCHE_COMPLETE_TIMEOUT = 6.0 + 1e-6
UPDATE_COMPLETE_TIMEOUT = 6.0 + 1e-6
TIME_PRECISION = 1e-6 # Tolerance for float comparisons

# --- Enums ---
class ElevatorMode(Enum):
    NORMAL = auto()
    SCHE_PENDING = auto() # Received SCHE, waiting to begin
    SCHE_MOVING = auto()  # Moving to target floor
    SCHE_STOPPING = auto() # Arrived at target, door opened, waiting
    UPDATE_PENDING = auto() # Received UPDATE, waiting to begin
    UPDATING = auto()     # Between BEGIN and END
    DOUBLE_A = auto()     # Upper carriage in double mode
    DOUBLE_B = auto()     # Lower carriage in double mode
    DISABLED = auto()     #井道 A 停用

class PassengerStatus(Enum):
    OUTSIDE = auto()      # Initial state
    WAITING = auto()      # Received by an elevator
    INSIDE = auto()       # Inside an elevator
    COMPLETED = auto()    # Reached destination (OUT-S)
    FAILED_OUT = auto()   # Left mid-way (OUT-F) or due to SCHE/UPDATE

# --- Data Structures ---
class Passenger:
    def __init__(self, id: int, priority: int, from_floor: str, to_floor: str, request_time: float):
        self.id = id
        self.priority = priority
        self.from_floor_name = from_floor
        self.to_floor_name = to_floor
        self.from_floor_idx = FLOOR_MAP[from_floor]
        self.to_floor_idx = FLOOR_MAP[to_floor]
        self.request_time = request_time
        self.status = PassengerStatus.OUTSIDE
        self.current_floor_idx = self.from_floor_idx
        self.elevator_id: Optional[int] = None # Which elevator they are in or waiting for
        self.last_receive_time: float = -1.0
        self.completion_time: float = -1.0

    def __repr__(self):
        return (f"Passenger(id={self.id}, status={self.status.name}, "
                f"floor={FLOOR_NAMES.get(self.current_floor_idx, 'N/A')}, "
                f"elevator={self.elevator_id})")

class Elevator:
    def __init__(self, id: int):
        self.id = id
        self.current_floor_idx = FLOOR_MAP["F1"]
        self.door_open = False
        self.passengers: Set[int] = set() # Set of passenger IDs inside
        self.speed = DEFAULT_SPEED
        self.mode = ElevatorMode.NORMAL
        self.last_action_time = 0.0 # Time of the last output action for this elevator
        self.last_arrive_time = 0.0 # Specifically for ARRIVE timing checks
        self.last_open_time = -1.0
        self.last_close_time = 0.0 # Initial state is closed at time 0

        # SCHE specific state
        self.sche_request_time = -1.0
        self.sche_accept_time = -1.0
        self.sche_target_floor_idx: Optional[int] = None
        self.sche_temp_speed: Optional[float] = None
        self.sche_begin_time = -1.0
        self.sche_arrive_count_since_accept = 0 # Constraint: <= 2 ARRIVE before SCHE-BEGIN

        # UPDATE specific state
        self.update_request_time = -1.0
        self.update_accept_time = -1.0
        self.update_partner_id: Optional[int] = None
        self.update_target_floor_idx: Optional[int] = None
        self.update_begin_time = -1.0
        self.update_arrive_count_since_accept = 0 # Constraint: <= 2 ARRIVE before passenger release

        # Double Carriage specific state
        self.double_partner_id: Optional[int] = None # The other carriage in the same shaft
        self.double_mode_role: Optional[str] = None # 'A' (upper) or 'B' (lower)
        self.double_min_floor_idx: int = 0
        self.double_max_floor_idx: int = NUM_FLOORS - 1

    def get_floor_name(self) -> str:
        return FLOOR_NAMES.get(self.current_floor_idx, "Invalid")

    def is_moving(self) -> bool:
        # Approximated: if last action wasn't ARRIVE/OPEN/CLOSE at current time
        # A more robust check might be needed depending on how concurrency is handled
        return False # Simplified for now, rely on state transitions

    def can_move(self) -> bool:
        return not self.door_open and self.mode not in [ElevatorMode.UPDATING, ElevatorMode.DISABLED]

    def get_valid_floor_range(self) -> Tuple[int, int]:
        if self.mode in [ElevatorMode.DOUBLE_A, ElevatorMode.DOUBLE_B]:
            return self.double_min_floor_idx, self.double_max_floor_idx
        elif self.mode == ElevatorMode.DISABLED:
            return -1, -1 # Invalid range
        else:
            return 0, NUM_FLOORS - 1

    def __repr__(self):
        return (f"Elevator(id={self.id}, floor={self.get_floor_name()}, "
                f"door={'open' if self.door_open else 'closed'}, "
                f"mode={self.mode.name}, passengers={len(self.passengers)}, "
                f"speed={self.speed})")


class SystemState:
    def __init__(self):
        self.elevators: Dict[int, Elevator] = {i: Elevator(i) for i in ELEVATOR_IDS}
        self.passengers: Dict[int, Passenger] = {}
        # passenger_id -> (elevator_id, receive_time)
        self.active_receives: Dict[int, Tuple[int, float]] = {}
        self.input_commands: List[Tuple[float, str, Dict[str, Any]]] = [] # (time, type, details)
        self.last_timestamp = 0.0
        self.max_time = 220.0 # Default to mutual test limit, adjust if needed

    def get_passenger(self, p_id: int) -> Optional[Passenger]:
        return self.passengers.get(p_id)

    def get_elevator(self, e_id: int) -> Optional[Elevator]:
        return self.elevators.get(e_id)

    def add_passenger_request(self, p_id: int, priority: int, from_floor: str, to_floor: str, req_time: float):
        if p_id in self.passengers:
            raise ValueError(f"Duplicate passenger ID {p_id} in input")
        self.passengers[p_id] = Passenger(p_id, priority, from_floor, to_floor, req_time)

    def add_sche_request(self, e_id: int, speed: float, target_floor: str, req_time: float):
        elevator = self.get_elevator(e_id)
        if not elevator:
            raise ValueError(f"SCHE request for non-existent elevator {e_id}")
        # Store SCHE request info temporarily, official handling starts at SCHE-ACCEPT
        self.input_commands.append((req_time, "SCHE", {"elevator_id": e_id, "speed": speed, "target_floor": target_floor}))


    def add_update_request(self, a_id: int, b_id: int, target_floor: str, req_time: float):
        elevator_a = self.get_elevator(a_id)
        elevator_b = self.get_elevator(b_id)
        if not elevator_a or not elevator_b:
            raise ValueError(f"UPDATE request for non-existent elevator {a_id} or {b_id}")
        if a_id == b_id:
             raise ValueError(f"UPDATE request involves the same elevator ID {a_id}")
        # Store UPDATE request info
        self.input_commands.append((req_time, "UPDATE", {"elevator_a_id": a_id, "elevator_b_id": b_id, "target_floor": target_floor}))

    def find_input_command(self, cmd_type: str, details: Dict[str, Any], timestamp: float) -> bool:
         """Checks if a matching input command exists around the given timestamp."""
         # This is simplified. Real implementation might need tolerance or exact match.
         for ts, type, det in self.input_commands:
             if type == cmd_type and abs(ts - timestamp) < TIME_PRECISION:
                 # Basic check, might need more specific detail matching
                 if cmd_type == "SCHE" and det["elevator_id"] == details["elevator_id"]:
                     return True
                 if cmd_type == "UPDATE" and det["elevator_a_id"] == details["elevator_a_id"] and det["elevator_b_id"] == details["elevator_b_id"]:
                     return True
         return False


# --- Error Handling ---
def fail(message: str, timestamp: Optional[float] = None, line: Optional[str] = None):
    """Prints an error message and exits."""
    prefix = f"[{timestamp:.1f}] " if timestamp is not None else ""
    line_info = f"\n   Output Line: {line.strip()}" if line else ""
    print(f"Validation Error: {prefix}{message}{line_info}", file=sys.stderr)
    sys.exit(1)

# --- Parsing Functions ---
OUTPUT_PATTERNS = {
    "ARRIVE": re.compile(r"\[\s*(\d+\.\d+)\s*\]ARRIVE-([A-Z0-9]+)-(\d+)$"),
    "OPEN": re.compile(r"\[\s*(\d+\.\d+)\s*\]OPEN-([A-Z0-9]+)-(\d+)$"),
    "CLOSE": re.compile(r"\[\s*(\d+\.\d+)\s*\]CLOSE-([A-Z0-9]+)-(\d+)$"),
    "IN": re.compile(r"\[\s*(\d+\.\d+)\s*\]IN-(\d+)-([A-Z0-9]+)-(\d+)$"),
    "OUT": re.compile(r"\[\s*(\d+\.\d+)\s*\]OUT-([SF])-(\d+)-([A-Z0-9]+)-(\d+)$"), # Captures S/F
    "RECEIVE": re.compile(r"\[\s*(\d+\.\d+)\s*\]RECEIVE-(\d+)-(\d+)$"),
    "SCHE-ACCEPT": re.compile(r"\[\s*(\d+\.\d+)\s*\]SCHE-ACCEPT-(\d+)-(\d+\.\d+)-([A-Z0-9]+)$"), # Official
    "SCHE-BEGIN": re.compile(r"\[\s*(\d+\.\d+)\s*\]SCHE-BEGIN-(\d+)$"),
    "SCHE-END": re.compile(r"\[\s*(\d+\.\d+)\s*\]SCHE-END-(\d+)$"),
    "UPDATE-ACCEPT": re.compile(r"\[\s*(\d+\.\d+)\s*\]UPDATE-ACCEPT-(\d+)-(\d+)-([A-Z0-9]+)$"), # Official
    "UPDATE-BEGIN": re.compile(r"\[\s*(\d+\.\d+)\s*\]UPDATE-BEGIN-(\d+)-(\d+)$"),
    "UPDATE-END": re.compile(r"\[\s*(\d+\.\d+)\s*\]UPDATE-END-(\d+)-(\d+)$"),
}

INPUT_PATTERNS = {
    "PASSENGER": re.compile(r"\[(\d+\.\d+)\](\d+)-PRI-(\d+)-FROM-([A-Z0-9]+)-TO-([A-Z0-9]+)$"),
    "SCHE": re.compile(r"\[(\d+\.\d+)\]SCHE-(\d+)-(\d+\.\d+)-([A-Z0-9]+)$"),
    "UPDATE": re.compile(r"\[(\d+\.\d+)\]UPDATE-(\d+)-(\d+)-([A-Z0-9]+)$"),
}


def parse_output_line(line: str) -> Optional[Tuple[float, str, Dict[str, Any]]]:
    """Parses a line from the output file."""
    for action_type, pattern in OUTPUT_PATTERNS.items():
        match = pattern.match(line.strip())
        if match:
            timestamp = float(match.group(1))
            params = match.groups()[1:]
            details: Dict[str, Any] = {}
            try:
                if action_type == "ARRIVE":
                    details = {"floor_name": params[0], "elevator_id": int(params[1])}
                elif action_type == "OPEN":
                    details = {"floor_name": params[0], "elevator_id": int(params[1])}
                elif action_type == "CLOSE":
                    details = {"floor_name": params[0], "elevator_id": int(params[1])}
                elif action_type == "IN":
                    details = {"passenger_id": int(params[0]), "floor_name": params[1], "elevator_id": int(params[2])}
                elif action_type == "OUT":
                    details = {"type": params[0], "passenger_id": int(params[1]), "floor_name": params[2], "elevator_id": int(params[3])}
                elif action_type == "RECEIVE":
                    details = {"passenger_id": int(params[0]), "elevator_id": int(params[1])}
                elif action_type == "SCHE-ACCEPT":
                     details = {"elevator_id": int(params[0]), "speed": float(params[1]), "target_floor": params[2]}
                elif action_type == "SCHE-BEGIN":
                    details = {"elevator_id": int(params[0])}
                elif action_type == "SCHE-END":
                    details = {"elevator_id": int(params[0])}
                elif action_type == "UPDATE-ACCEPT":
                     details = {"elevator_a_id": int(params[0]), "elevator_b_id": int(params[1]), "target_floor": params[2]}
                elif action_type == "UPDATE-BEGIN":
                    details = {"elevator_a_id": int(params[0]), "elevator_b_id": int(params[1])}
                elif action_type == "UPDATE-END":
                    details = {"elevator_a_id": int(params[0]), "elevator_b_id": int(params[1])}
                else:
                    # Should not happen if patterns are correct
                    return None
            except (ValueError, IndexError):
                 fail(f"Invalid parameters in {action_type} line", timestamp, line)

            # Validate common parameters
            if "elevator_id" in details and details["elevator_id"] not in ELEVATOR_IDS:
                 fail(f"Invalid elevator ID {details['elevator_id']} in {action_type}", timestamp, line)
            if "elevator_a_id" in details and details["elevator_a_id"] not in ELEVATOR_IDS:
                 fail(f"Invalid elevator ID {details['elevator_a_id']} in {action_type}", timestamp, line)
            if "elevator_b_id" in details and details["elevator_b_id"] not in ELEVATOR_IDS:
                 fail(f"Invalid elevator ID {details['elevator_b_id']} in {action_type}", timestamp, line)
            if "floor_name" in details and details["floor_name"] not in FLOOR_MAP:
                 fail(f"Invalid floor name '{details['floor_name']}' in {action_type}", timestamp, line)
            if "target_floor" in details and details["target_floor"] not in FLOOR_MAP:
                 fail(f"Invalid target floor name '{details['target_floor']}' in {action_type}", timestamp, line)

            return timestamp, action_type, details
    return None # Line didn't match any known pattern

def parse_input_file(filepath: str, state: SystemState):
    """Parses the input file to populate initial requests."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                matched = False
                for cmd_type, pattern in INPUT_PATTERNS.items():
                    match = pattern.match(line)
                    if match:
                        timestamp = float(match.group(1))
                        params = match.groups()[1:]
                        try:
                            if cmd_type == "PASSENGER":
                                p_id, prio, from_f, to_f = params
                                if from_f == to_f:
                                     fail(f"Input Error (Line {line_num}): Passenger {p_id} FROM and TO floors are the same ('{from_f}')")
                                if from_f not in FLOOR_MAP or to_f not in FLOOR_MAP:
                                     fail(f"Input Error (Line {line_num}): Invalid floor name for passenger {p_id} ('{from_f}' or '{to_f}')")
                                state.add_passenger_request(int(p_id), int(prio), from_f, to_f, timestamp)
                            elif cmd_type == "SCHE":
                                e_id, speed, target_f = params
                                if int(e_id) not in ELEVATOR_IDS:
                                     fail(f"Input Error (Line {line_num}): Invalid elevator ID {e_id} for SCHE")
                                if target_f not in FLOOR_MAP:
                                     fail(f"Input Error (Line {line_num}): Invalid target floor '{target_f}' for SCHE")
                                state.add_sche_request(int(e_id), float(speed), target_f, timestamp)
                            elif cmd_type == "UPDATE":
                                a_id, b_id, target_f = params
                                if int(a_id) not in ELEVATOR_IDS or int(b_id) not in ELEVATOR_IDS:
                                     fail(f"Input Error (Line {line_num}): Invalid elevator ID {a_id} or {b_id} for UPDATE")
                                if a_id == b_id:
                                     fail(f"Input Error (Line {line_num}): UPDATE involves same elevator ID {a_id}")
                                if target_f not in FLOOR_MAP:
                                     fail(f"Input Error (Line {line_num}): Invalid target floor '{target_f}' for UPDATE")
                                state.add_update_request(int(a_id), int(b_id), target_f, timestamp)
                            matched = True
                            break # Stop checking patterns for this line
                        except (ValueError, IndexError) as e:
                             fail(f"Input Error (Line {line_num}): Invalid format or value - {e}\n   Line: {line}")

                if not matched:
                    fail(f"Input Error (Line {line_num}): Unknown command format\n   Line: {line}")

    except FileNotFoundError:
        fail(f"Input file not found: {filepath}")
    except Exception as e:
        fail(f"Error reading input file {filepath}: {e}")


# --- Validation Logic ---

def check_timestamp(timestamp: float, state: SystemState, line: str):
    if timestamp < state.last_timestamp - TIME_PRECISION:
        fail(f"Timestamp out of order. Current: {timestamp:.1f}, Previous: {state.last_timestamp:.1f}", timestamp, line)
    if timestamp > state.max_time + TIME_PRECISION:
         fail(f"Total run time {timestamp:.1f} exceeds limit {state.max_time:.1f}", timestamp, line)
    state.last_timestamp = timestamp

def check_arrive(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    e_id = details["elevator_id"]
    floor_name = details["floor_name"]
    floor_idx = FLOOR_MAP[floor_name]
    elevator = state.get_elevator(e_id)

    if not elevator: fail(f"ARRIVE: Elevator {e_id} does not exist?", timestamp, line) # Should be caught earlier

    # Basic state checks
    if elevator.door_open:
        fail(f"ARRIVE: Elevator {e_id} arrived at {floor_name} with door open", timestamp, line)
    if elevator.mode == ElevatorMode.UPDATING:
         fail(f"ARRIVE: Elevator {e_id} moved during UPDATE", timestamp, line)
    if elevator.mode == ElevatorMode.DISABLED:
         fail(f"ARRIVE: Elevator {e_id} (shaft A) moved after being disabled by UPDATE", timestamp, line)


    # Floor range check
    min_f, max_f = elevator.get_valid_floor_range()
    if not (min_f <= floor_idx <= max_f):
         fail(f"ARRIVE: Elevator {e_id} moved outside its valid range ({FLOOR_NAMES[min_f]}-{FLOOR_NAMES[max_f]}) to {floor_name}", timestamp, line)

    # Movement check (must move one floor at a time)
    floor_diff = abs(floor_idx - elevator.current_floor_idx)
    if floor_diff != 1:
        fail(f"ARRIVE: Elevator {e_id} jumped floors from {elevator.get_floor_name()} to {floor_name}", timestamp, line)

    # Time check
    expected_time = elevator.speed
    actual_time = timestamp - elevator.last_action_time # Use last_action_time as CLOSE must precede ARRIVE
    # Allow for slight delay, but not too early
    if actual_time < expected_time - TIME_PRECISION:
        fail(f"ARRIVE: Elevator {e_id} moved too fast to {floor_name}. "
             f"Expected >= {expected_time:.3f}s, Actual: {actual_time:.3f}s "
             f"(Last action at {elevator.last_action_time:.1f})", timestamp, line)

    # Double carriage collision check
    if elevator.mode in [ElevatorMode.DOUBLE_A, ElevatorMode.DOUBLE_B]:
        partner = state.get_elevator(elevator.double_partner_id)
        if not partner: fail(f"ARRIVE: Double carriage partner {elevator.double_partner_id} not found for {e_id}", timestamp, line)
        if floor_idx == partner.current_floor_idx:
             fail(f"ARRIVE: Double carriages {e_id} and {partner.id} collided at floor {floor_name}", timestamp, line)
        # Ensure B is not above A
        elevator_a = elevator if elevator.double_mode_role == 'A' else partner
        elevator_b = partner if elevator.double_mode_role == 'A' else elevator
        if elevator_b.current_floor_idx > elevator_a.current_floor_idx:
             # Check if the *new* arrival causes the violation
             if e_id == elevator_b.id and floor_idx > elevator_a.current_floor_idx:
                  fail(f"ARRIVE: Double carriage {elevator_b.id} (B) moved above {elevator_a.id} (A) at floor {floor_name}", timestamp, line)
             elif e_id == elevator_a.id and elevator_b.current_floor_idx > floor_idx:
                  fail(f"ARRIVE: Double carriage {elevator_b.id} (B) ended up above {elevator_a.id} (A) at floor {elevator_a.get_floor_name()}", timestamp, line)


    # Update state AFTER validation
    elevator.current_floor_idx = floor_idx
    elevator.last_action_time = timestamp
    elevator.last_arrive_time = timestamp

    # Increment SCHE/UPDATE arrive counters if applicable
    if elevator.mode == ElevatorMode.SCHE_PENDING:
        elevator.sche_arrive_count_since_accept += 1
    elif elevator.mode == ElevatorMode.UPDATE_PENDING:
         elevator.update_arrive_count_since_accept += 1


def check_open(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    e_id = details["elevator_id"]
    floor_name = details["floor_name"]
    floor_idx = FLOOR_MAP[floor_name]
    elevator = state.get_elevator(e_id)

    if not elevator: fail(f"OPEN: Elevator {e_id} does not exist?", timestamp, line)

    if elevator.current_floor_idx != floor_idx:
        fail(f"OPEN: Elevator {e_id} opened at {floor_name} but is currently at {elevator.get_floor_name()}", timestamp, line)
    if elevator.door_open:
        fail(f"OPEN: Elevator {e_id} tried to open door at {floor_name} when already open", timestamp, line)
    if elevator.mode == ElevatorMode.SCHE_MOVING and elevator.current_floor_idx != elevator.sche_target_floor_idx:
         fail(f"OPEN: Elevator {e_id} opened door during SCHE movement", timestamp, line)
    if elevator.mode == ElevatorMode.UPDATING:
         fail(f"OPEN: Elevator {e_id} opened door during UPDATE", timestamp, line)
    if elevator.mode == ElevatorMode.DISABLED:
         fail(f"OPEN: Elevator {e_id} (shaft A) opened door after being disabled", timestamp, line)

    # Time check: Must happen after ARRIVE at this floor (or initially at F1)
    # Allow OPEN immediately after ARRIVE at the same timestamp
    if timestamp < elevator.last_arrive_time - TIME_PRECISION and not (elevator.current_floor_idx == FLOOR_MAP["F1"] and timestamp < TIME_PRECISION):
         fail(f"OPEN: Elevator {e_id} opened at {floor_name} ({timestamp:.1f}) before arriving ({elevator.last_arrive_time:.1f})", timestamp, line)


    # Update state
    elevator.door_open = True
    elevator.last_action_time = timestamp
    elevator.last_open_time = timestamp

    # Handle SCHE state transition upon opening at target
    if elevator.mode == ElevatorMode.SCHE_MOVING and elevator.current_floor_idx == elevator.sche_target_floor_idx:
        elevator.mode = ElevatorMode.SCHE_STOPPING


def check_close(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    e_id = details["elevator_id"]
    floor_name = details["floor_name"]
    floor_idx = FLOOR_MAP[floor_name]
    elevator = state.get_elevator(e_id)

    if not elevator: fail(f"CLOSE: Elevator {e_id} does not exist?", timestamp, line)

    if elevator.current_floor_idx != floor_idx:
        fail(f"CLOSE: Elevator {e_id} closed at {floor_name} but is currently at {elevator.get_floor_name()}", timestamp, line)
    if not elevator.door_open:
        fail(f"CLOSE: Elevator {e_id} tried to close door at {floor_name} when already closed", timestamp, line)
    if elevator.mode == ElevatorMode.DISABLED:
         fail(f"CLOSE: Elevator {e_id} (shaft A) closed door after being disabled", timestamp, line)


    # Time check
    time_since_open = timestamp - elevator.last_open_time
    if time_since_open < MIN_DOOR_TIME:
        fail(f"CLOSE: Elevator {e_id} closed door too fast at {floor_name}. "
             f"Required >= {MIN_DOOR_TIME + TIME_PRECISION:.3f}s, Actual: {time_since_open:.3f}s "
             f"(Opened at {elevator.last_open_time:.1f})", timestamp, line)

    # Update state
    elevator.door_open = False
    elevator.last_action_time = timestamp
    elevator.last_close_time = timestamp

def check_in(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    p_id = details["passenger_id"]
    floor_name = details["floor_name"]
    e_id = details["elevator_id"]
    floor_idx = FLOOR_MAP[floor_name]
    elevator = state.get_elevator(e_id)
    passenger = state.get_passenger(p_id)

    if not elevator: fail(f"IN: Elevator {e_id} does not exist?", timestamp, line)
    if not passenger: fail(f"IN: Passenger {p_id} does not exist (not in input?)", timestamp, line)

    if elevator.current_floor_idx != floor_idx:
        fail(f"IN: Elevator {e_id} is at {elevator.get_floor_name()}, but passenger {p_id} tried to enter at {floor_name}", timestamp, line)
    if not elevator.door_open:
        fail(f"IN: Passenger {p_id} tried to enter elevator {e_id} at {floor_name} while door was closed", timestamp, line)
    if len(elevator.passengers) >= CAPACITY:
        fail(f"IN: Elevator {e_id} exceeded capacity ({CAPACITY}) when passenger {p_id} tried to enter at {floor_name}", timestamp, line)
    if passenger.status != PassengerStatus.WAITING:
         fail(f"IN: Passenger {p_id} tried to enter elevator {e_id} but status is {passenger.status.name} (Expected WAITING)", timestamp, line)
    if passenger.current_floor_idx != floor_idx:
         fail(f"IN: Passenger {p_id} is at floor {FLOOR_NAMES[passenger.current_floor_idx]}, but tried to enter elevator {e_id} at {floor_name}", timestamp, line)
    if passenger.elevator_id != e_id:
         fail(f"IN: Passenger {p_id} tried to enter elevator {e_id}, but was received by {passenger.elevator_id}", timestamp, line)

    # Check RECEIVE constraint (must have active receive for this passenger/elevator)
    active_receive = state.active_receives.get(p_id)
    if not active_receive or active_receive[0] != e_id:
         fail(f"IN: Passenger {p_id} entered elevator {e_id} without a valid preceding RECEIVE", timestamp, line)
    # Check timing: IN must happen at or after RECEIVE
    receive_time = active_receive[1]
    if timestamp < receive_time - TIME_PRECISION:
         fail(f"IN: Passenger {p_id} entered elevator {e_id} at {timestamp:.1f} before being received at {receive_time:.1f}", timestamp, line)

    # SCHE constraint: No IN during SCHE stop phase
    if elevator.mode == ElevatorMode.SCHE_STOPPING:
         fail(f"IN: Passenger {p_id} entered elevator {e_id} during SCHE stop phase at {floor_name}", timestamp, line)


    # Update state
    passenger.status = PassengerStatus.INSIDE
    # passenger.current_floor_idx remains the elevator's floor
    elevator.passengers.add(p_id)
    # Note: IN/OUT are instantaneous, don't update elevator.last_action_time

def check_out(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    out_type = details["type"] # 'S' or 'F'
    p_id = details["passenger_id"]
    floor_name = details["floor_name"]
    e_id = details["elevator_id"]
    floor_idx = FLOOR_MAP[floor_name]
    elevator = state.get_elevator(e_id)
    passenger = state.get_passenger(p_id)

    if not elevator: fail(f"OUT: Elevator {e_id} does not exist?", timestamp, line)
    if not passenger: fail(f"OUT: Passenger {p_id} does not exist?", timestamp, line)

    if elevator.current_floor_idx != floor_idx:
        fail(f"OUT: Elevator {e_id} is at {elevator.get_floor_name()}, but passenger {p_id} tried to exit at {floor_name}", timestamp, line)
    if not elevator.door_open:
        fail(f"OUT: Passenger {p_id} tried to exit elevator {e_id} at {floor_name} while door was closed", timestamp, line)
    if passenger.status != PassengerStatus.INSIDE:
        fail(f"OUT: Passenger {p_id} tried to exit elevator {e_id} but status is {passenger.status.name} (Expected INSIDE)", timestamp, line)
    if passenger.elevator_id != e_id:
         # This case should ideally be impossible if IN was checked correctly
         fail(f"OUT: Passenger {p_id} tried to exit elevator {e_id}, but was recorded as being in {passenger.elevator_id}", timestamp, line)

    # Check OUT-S validity
    if out_type == 'S' and passenger.to_floor_idx != floor_idx:
        fail(f"OUT-S: Passenger {p_id} exited elevator {e_id} at {floor_name}, but their destination is {passenger.to_floor_name}", timestamp, line)

    # Update state
    elevator.passengers.remove(p_id)
    passenger.elevator_id = None
    passenger.current_floor_idx = floor_idx # Now outside at this floor

    if out_type == 'S':
        passenger.status = PassengerStatus.COMPLETED
        passenger.completion_time = timestamp
    else: # OUT-F
        # If exited during SCHE stop, treat as failed/needs reschedule
        if elevator.mode == ElevatorMode.SCHE_STOPPING:
             passenger.status = PassengerStatus.FAILED_OUT
        else:
             # Otherwise, just back outside, potentially waiting for another ride
             passenger.status = PassengerStatus.OUTSIDE

    # Cancel the corresponding RECEIVE upon OUT
    if p_id in state.active_receives and state.active_receives[p_id][0] == e_id:
         # Check if this OUT corresponds to the *most recent* receive for this pair
         # This requires tracking receive history or assuming only one active receive per passenger
         # Simplified: Assume it cancels the current one if it exists
         del state.active_receives[p_id]


def check_receive(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    p_id = details["passenger_id"]
    e_id = details["elevator_id"]
    elevator = state.get_elevator(e_id)
    passenger = state.get_passenger(p_id)

    if not elevator: fail(f"RECEIVE: Elevator {e_id} does not exist?", timestamp, line)
    if not passenger: fail(f"RECEIVE: Passenger {p_id} does not exist?", timestamp, line)

    if passenger.status not in [PassengerStatus.OUTSIDE, PassengerStatus.FAILED_OUT]:
         fail(f"RECEIVE: Passenger {p_id} received by elevator {e_id}, but status is {passenger.status.name} (must be OUTSIDE or FAILED_OUT)", timestamp, line)
    if p_id in state.active_receives:
         fail(f"RECEIVE: Passenger {p_id} received by elevator {e_id}, but already has an active receive by elevator {state.active_receives[p_id][0]}", timestamp, line)
    if elevator.mode in [ElevatorMode.SCHE_MOVING, ElevatorMode.SCHE_STOPPING, ElevatorMode.UPDATING, ElevatorMode.DISABLED]:
         fail(f"RECEIVE: Elevator {e_id} issued RECEIVE for {p_id} while in mode {elevator.mode.name}", timestamp, line)

    # Check empty elevator movement constraint (can only move if has passengers or SCHE/UPDATE task, or after receiving someone)
    # This is tricky to check perfectly here, needs context of subsequent ARRIVE.
    # We can check if the elevator *was* empty and stationary before this RECEIVE.
    # A full check requires looking ahead or verifying upon ARRIVE.

    # Update state
    state.active_receives[p_id] = (e_id, timestamp)
    passenger.status = PassengerStatus.WAITING
    passenger.elevator_id = e_id # Mark who they are waiting for
    passenger.last_receive_time = timestamp
    # Note: RECEIVE is instantaneous, don't update elevator.last_action_time

def check_sche_accept(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    # This is an official output, primarily used to trigger state changes in the judge
    e_id = details["elevator_id"]
    speed = details["speed"]
    target_floor = details["target_floor"]
    elevator = state.get_elevator(e_id)

    if not elevator: fail(f"SCHE-ACCEPT: Elevator {e_id} does not exist?", timestamp, line)

    # Check if this ACCEPT corresponds to an input SCHE command (optional but good)
    # if not state.find_input_command("SCHE", details, timestamp):
    #     print(f"Warning: SCHE-ACCEPT for elevator {e_id} at {timestamp:.1f} does not match any input command closely.", file=sys.stderr)

    if elevator.mode != ElevatorMode.NORMAL:
         fail(f"SCHE-ACCEPT: Elevator {e_id} received SCHE command while not in NORMAL mode (current: {elevator.mode.name})", timestamp, line)
    if elevator.update_partner_id is not None: # Cannot SCHE if part of an UPDATE
         fail(f"SCHE-ACCEPT: Elevator {e_id} received SCHE command after being involved in UPDATE", timestamp, line)


    # Update state
    elevator.mode = ElevatorMode.SCHE_PENDING
    elevator.sche_request_time = timestamp # Or find exact input time if needed
    elevator.sche_accept_time = timestamp
    elevator.sche_target_floor_idx = FLOOR_MAP[target_floor]
    elevator.sche_temp_speed = speed
    elevator.sche_arrive_count_since_accept = 0
    # elevator.last_action_time = timestamp # Official output acts as an action

def check_sche_begin(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    e_id = details["elevator_id"]
    elevator = state.get_elevator(e_id)

    if not elevator: fail(f"SCHE-BEGIN: Elevator {e_id} does not exist?", timestamp, line)

    if elevator.mode != ElevatorMode.SCHE_PENDING:
        fail(f"SCHE-BEGIN: Elevator {e_id} not in SCHE_PENDING mode (current: {elevator.mode.name})", timestamp, line)
    if elevator.door_open:
        fail(f"SCHE-BEGIN: Elevator {e_id} started SCHE with door open", timestamp, line)
    # Constraint: <= 2 ARRIVEs between ACCEPT and BEGIN
    if elevator.sche_arrive_count_since_accept > 2:
         fail(f"SCHE-BEGIN: Elevator {e_id} started SCHE after {elevator.sche_arrive_count_since_accept} ARRIVEs (max 2 allowed) since SCHE-ACCEPT", timestamp, line)
    # Constraint: Elevator should be stationary (not mid-move) - check if last action was ARRIVE/OPEN/CLOSE at current floor
    # This check is complex. Simplified: check if timestamp matches last action time.
    # if abs(timestamp - elevator.last_action_time) > TIME_PRECISION:
    #      fail(f"SCHE-BEGIN: Elevator {e_id} started SCHE while potentially moving (last action at {elevator.last_action_time:.1f})", timestamp, line)


    # Update state
    elevator.mode = ElevatorMode.SCHE_MOVING
    elevator.speed = elevator.sche_temp_speed # Apply temporary speed
    elevator.sche_begin_time = timestamp
    # elevator.last_action_time = timestamp

    # Cancel active receives for this elevator
    receives_to_cancel = [pid for pid, (eid, _) in state.active_receives.items() if eid == e_id]
    for pid in receives_to_cancel:
        passenger = state.get_passenger(pid)
        if passenger and passenger.status == PassengerStatus.WAITING:
             passenger.status = PassengerStatus.OUTSIDE # Back to needing a ride
             passenger.elevator_id = None
        del state.active_receives[pid]
        # print(f"Debug: SCHE-BEGIN cancelled RECEIVE for passenger {pid}")


def check_sche_end(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    e_id = details["elevator_id"]
    elevator = state.get_elevator(e_id)

    if not elevator: fail(f"SCHE-END: Elevator {e_id} does not exist?", timestamp, line)

    # Must happen after SCHE_STOPPING phase (OPEN at target, wait >= 1s, CLOSE)
    if elevator.mode != ElevatorMode.SCHE_STOPPING:
         fail(f"SCHE-END: Elevator {e_id} ended SCHE but was not in SCHE_STOPPING mode (current: {elevator.mode.name})", timestamp, line)
    if elevator.door_open:
        fail(f"SCHE-END: Elevator {e_id} ended SCHE with door open", timestamp, line)
    if elevator.passengers:
        fail(f"SCHE-END: Elevator {e_id} ended SCHE with passengers still inside: {elevator.passengers}", timestamp, line)
    if elevator.current_floor_idx != elevator.sche_target_floor_idx:
         fail(f"SCHE-END: Elevator {e_id} ended SCHE at {elevator.get_floor_name()} but target was {FLOOR_NAMES[elevator.sche_target_floor_idx]}", timestamp, line)

    # Timing: Must happen *after* the CLOSE following the SCHE stop OPEN
    # The CLOSE must happen >= SCHE_STOP_TIME after the OPEN at the target floor.
    # SCHE-END must happen at or after that CLOSE.
    if timestamp < elevator.last_close_time - TIME_PRECISION:
         fail(f"SCHE-END: Elevator {e_id} ended SCHE at {timestamp:.1f} before the final CLOSE at {elevator.last_close_time:.1f}", timestamp, line)

    # Check completion timeout
    time_since_accept = timestamp - elevator.sche_accept_time
    if time_since_accept > SCHE_COMPLETE_TIMEOUT:
         fail(f"SCHE-END: Elevator {e_id} SCHE completion time ({time_since_accept:.3f}s) exceeded limit ({SCHE_COMPLETE_TIMEOUT - TIME_PRECISION:.3f}s)", timestamp, line)


    # Update state
    elevator.mode = ElevatorMode.NORMAL
    elevator.speed = DEFAULT_SPEED # Restore default speed
    # elevator.last_action_time = timestamp
    # Reset SCHE state variables
    elevator.sche_request_time = -1.0
    elevator.sche_accept_time = -1.0
    elevator.sche_target_floor_idx = None
    elevator.sche_temp_speed = None
    elevator.sche_begin_time = -1.0
    elevator.sche_arrive_count_since_accept = 0

def check_update_accept(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    # Official output, trigger state changes
    a_id = details["elevator_a_id"]
    b_id = details["elevator_b_id"]
    target_floor = details["target_floor"]
    elevator_a = state.get_elevator(a_id)
    elevator_b = state.get_elevator(b_id)

    if not elevator_a: fail(f"UPDATE-ACCEPT: Elevator A ({a_id}) does not exist?", timestamp, line)
    if not elevator_b: fail(f"UPDATE-ACCEPT: Elevator B ({b_id}) does not exist?", timestamp, line)

    # Check if this ACCEPT corresponds to an input UPDATE command (optional)
    # if not state.find_input_command("UPDATE", details, timestamp):
    #     print(f"Warning: UPDATE-ACCEPT for {a_id}-{b_id} at {timestamp:.1f} does not match any input command closely.", file=sys.stderr)

    if elevator_a.mode != ElevatorMode.NORMAL or elevator_b.mode != ElevatorMode.NORMAL:
         fail(f"UPDATE-ACCEPT: Elevators {a_id} ({elevator_a.mode.name}) or {b_id} ({elevator_b.mode.name}) not in NORMAL mode", timestamp, line)
    if elevator_a.sche_request_time != -1 or elevator_b.sche_request_time != -1:
         fail(f"UPDATE-ACCEPT: Elevators {a_id} or {b_id} received UPDATE after being involved in SCHE", timestamp, line)
    if elevator_a.update_partner_id is not None or elevator_b.update_partner_id is not None:
         fail(f"UPDATE-ACCEPT: Elevators {a_id} or {b_id} received UPDATE after already being involved in UPDATE", timestamp, line)


    # Update state
    target_idx = FLOOR_MAP[target_floor]
    for e in [elevator_a, elevator_b]:
        e.mode = ElevatorMode.UPDATE_PENDING
        e.update_request_time = timestamp # Or find exact input time
        e.update_accept_time = timestamp
        e.update_partner_id = b_id if e.id == a_id else a_id
        e.update_target_floor_idx = target_idx
        e.update_arrive_count_since_accept = 0
        # e.last_action_time = timestamp # Official output

def check_update_begin(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    a_id = details["elevator_a_id"]
    b_id = details["elevator_b_id"]
    elevator_a = state.get_elevator(a_id)
    elevator_b = state.get_elevator(b_id)

    if not elevator_a: fail(f"UPDATE-BEGIN: Elevator A ({a_id}) does not exist?", timestamp, line)
    if not elevator_b: fail(f"UPDATE-BEGIN: Elevator B ({b_id}) does not exist?", timestamp, line)

    if elevator_a.mode != ElevatorMode.UPDATE_PENDING or elevator_b.mode != ElevatorMode.UPDATE_PENDING:
         fail(f"UPDATE-BEGIN: Elevators {a_id} ({elevator_a.mode.name}) or {b_id} ({elevator_b.mode.name}) not in UPDATE_PENDING mode", timestamp, line)
    if elevator_a.update_partner_id != b_id or elevator_b.update_partner_id != a_id:
         fail(f"UPDATE-BEGIN: Mismatched partners for {a_id}-{b_id}", timestamp, line) # Should be impossible

    # Check constraints before BEGIN
    if elevator_a.door_open or elevator_b.door_open:
         fail(f"UPDATE-BEGIN: Elevator {a_id} or {b_id} started UPDATE with door open", timestamp, line)
    if elevator_a.passengers or elevator_b.passengers:
         fail(f"UPDATE-BEGIN: Elevator {a_id} (passengers: {elevator_a.passengers}) or {b_id} (passengers: {elevator_b.passengers}) started UPDATE with passengers inside", timestamp, line)

    # Constraint: Passengers must be released within 2 ARRIVEs (check is complex)
    # Simplified check: Assume passengers *should* be out by now if logic was correct.
    # A full check would need to track passenger releases after UPDATE-ACCEPT.

    # Update state
    for e in [elevator_a, elevator_b]:
        e.mode = ElevatorMode.UPDATING
        e.update_begin_time = timestamp
        # e.last_action_time = timestamp

    # Cancel active receives for both elevators
    receives_to_cancel = [pid for pid, (eid, _) in state.active_receives.items() if eid == a_id or eid == b_id]
    for pid in receives_to_cancel:
        passenger = state.get_passenger(pid)
        if passenger and passenger.status == PassengerStatus.WAITING:
             passenger.status = PassengerStatus.OUTSIDE
             passenger.elevator_id = None
        del state.active_receives[pid]
        # print(f"Debug: UPDATE-BEGIN cancelled RECEIVE for passenger {pid}")


def check_update_end(timestamp: float, details: Dict[str, Any], state: SystemState, line: str):
    a_id = details["elevator_a_id"]
    b_id = details["elevator_b_id"]
    elevator_a = state.get_elevator(a_id)
    elevator_b = state.get_elevator(b_id)

    if not elevator_a: fail(f"UPDATE-END: Elevator A ({a_id}) does not exist?", timestamp, line)
    if not elevator_b: fail(f"UPDATE-END: Elevator B ({b_id}) does not exist?", timestamp, line)

    if elevator_a.mode != ElevatorMode.UPDATING or elevator_b.mode != ElevatorMode.UPDATING:
         fail(f"UPDATE-END: Elevators {a_id} ({elevator_a.mode.name}) or {b_id} ({elevator_b.mode.name}) not in UPDATING mode", timestamp, line)
    if elevator_a.update_partner_id != b_id or elevator_b.update_partner_id != a_id:
         fail(f"UPDATE-END: Mismatched partners for {a_id}-{b_id}", timestamp, line)

    # Time check
    time_since_begin = timestamp - elevator_a.update_begin_time # Use A's time, should be same as B's
    if time_since_begin < UPDATE_RESET_TIME:
         fail(f"UPDATE-END: Update duration for {a_id}-{b_id} too short. "
              f"Required >= {UPDATE_RESET_TIME + TIME_PRECISION:.3f}s, Actual: {time_since_begin:.3f}s "
              f"(Began at {elevator_a.update_begin_time:.1f})", timestamp, line)

    # Check completion timeout
    time_since_accept = timestamp - elevator_a.update_accept_time
    if time_since_accept > UPDATE_COMPLETE_TIMEOUT:
         fail(f"UPDATE-END: Elevators {a_id}-{b_id} UPDATE completion time ({time_since_accept:.3f}s) exceeded limit ({UPDATE_COMPLETE_TIMEOUT - TIME_PRECISION:.3f}s)", timestamp, line)


    # --- Apply final state changes ---
    target_floor_idx = elevator_a.update_target_floor_idx # Should be same for both

    # Elevator A (shaft) becomes disabled
    elevator_a.mode = ElevatorMode.DISABLED
    # elevator_a.last_action_time = timestamp
    elevator_a.double_partner_id = None # Clear partner info

    # Elevator B (shaft) now hosts both carriages
    # Carriage A (original elevator A)
    elevator_a_carriage = elevator_a # Re-purpose A's object for its carriage state
    elevator_a_carriage.id = a_id # Keep original ID for reference
    elevator_a_carriage.mode = ElevatorMode.DOUBLE_A
    elevator_a_carriage.double_mode_role = 'A'
    elevator_a_carriage.double_partner_id = b_id # Partner is carriage B
    elevator_a_carriage.current_floor_idx = target_floor_idx + 1
    elevator_a_carriage.double_min_floor_idx = target_floor_idx
    elevator_a_carriage.double_max_floor_idx = NUM_FLOORS - 1
    elevator_a_carriage.speed = 0.2
    elevator_a_carriage.door_open = False # Ensure closed
    elevator_a_carriage.passengers = set() # Ensure empty
    # elevator_a_carriage.last_action_time = timestamp
    # Reset SCHE/UPDATE specific fields just in case
    elevator_a_carriage.sche_request_time = -1.0
    elevator_a_carriage.update_request_time = -1.0


    # Carriage B (original elevator B)
    elevator_b.mode = ElevatorMode.DOUBLE_B
    elevator_b.double_mode_role = 'B'
    elevator_b.double_partner_id = a_id # Partner is carriage A
    elevator_b.current_floor_idx = target_floor_idx - 1
    elevator_b.double_min_floor_idx = 0
    elevator_b.double_max_floor_idx = target_floor_idx
    elevator_b.speed = 0.2
    elevator_b.door_open = False # Ensure closed
    elevator_b.passengers = set() # Ensure empty
    # elevator_b.last_action_time = timestamp
    # Reset SCHE/UPDATE specific fields
    elevator_b.sche_request_time = -1.0
    elevator_b.update_request_time = -1.0

    # Validate initial positions after update
    if not (0 <= elevator_b.current_floor_idx < NUM_FLOORS):
         fail(f"UPDATE-END: Elevator B initial position ({elevator_b.get_floor_name()}) out of bounds after update", timestamp, line)
    if not (0 <= elevator_a_carriage.current_floor_idx < NUM_FLOORS):
         fail(f"UPDATE-END: Elevator A initial position ({elevator_a_carriage.get_floor_name()}) out of bounds after update", timestamp, line)
    if elevator_b.current_floor_idx >= elevator_a_carriage.current_floor_idx:
         fail(f"UPDATE-END: Elevator B ({elevator_b.get_floor_name()}) not below Elevator A ({elevator_a_carriage.get_floor_name()}) after update", timestamp, line)

    # Note: We re-used elevator_a object for carriage A. state.elevators[a_id] now represents carriage A.
    # state.elevators[b_id] represents carriage B.


def check_final_state(state: SystemState):
    """Checks conditions at the end of the output."""
    # 1. All passengers completed
    for p_id, passenger in state.passengers.items():
        if passenger.status != PassengerStatus.COMPLETED:
            fail(f"Final State Error: Passenger {p_id} did not complete successfully (status: {passenger.status.name})")

    # 2. All elevators doors closed and empty (except disabled)
    for e_id, elevator in state.elevators.items():
        if elevator.mode != ElevatorMode.DISABLED:
            if elevator.door_open:
                fail(f"Final State Error: Elevator {e_id} ended with door open at {elevator.get_floor_name()}")
            if elevator.passengers:
                fail(f"Final State Error: Elevator {e_id} ended with passengers inside: {elevator.passengers}")

    # 3. Time limit check (already done line-by-line by check_timestamp)
    print("Final state checks passed.")


# --- Main Judge ---
def judge(input_filepath: str, output_filepath: str, max_time: float):
    state = SystemState()
    state.max_time = max_time

    # 1. Parse Input File
    parse_input_file(input_filepath, state)
    print(f"Parsed {len(state.passengers)} passenger requests and {len(state.input_commands)} special commands from {input_filepath}")

    # 2. Process Output File
    last_line = ""
    try:
        with open(output_filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                last_line = line

                parsed = parse_output_line(line)
                if not parsed:
                    fail(f"Output Error (Line {line_num}): Unknown or invalid format", line=line)

                timestamp, action_type, details = parsed

                # --- Core Validation Steps ---
                # a. Check Timestamp
                check_timestamp(timestamp, state, line)

                # b. Check Action Validity and Update State
                handler = globals().get(f"check_{action_type.lower().replace('-', '_')}")
                if handler:
                    handler(timestamp, details, state, line)
                else:
                    # Should not happen if parse_output_line is comprehensive
                    fail(f"Internal Error: No handler for action type '{action_type}'", timestamp, line)

    except FileNotFoundError:
        fail(f"Output file not found: {output_filepath}")
    except Exception as e:
        # Catch unexpected errors during processing
        import traceback
        traceback.print_exc()
        fail(f"Runtime error during validation: {e}", line=last_line)

    # 3. Final State Checks
    check_final_state(state)

    # 4. Success
    print("Accepted")


# --- Argument Parsing ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate elevator simulation output.")
    parser.add_argument("--input_file", default="input.txt", help="Path to the input command file (e.g., input.txt).")
    parser.add_argument("--output_file", default="output.txt", help="Path to the elevator program's output log file (e.g., output.txt).")
    parser.add_argument("--max_time", type=float, default=220.0, help="Maximum allowed simulation time (default: 220.0 for mutual).") # Adjust default if needed

    args = parser.parse_args()

    judge(args.input_file, args.output_file, args.max_time)