import re
import argparse

class ValidationError(Exception):
    pass

class ElevatorValidator:
    def __init__(self, input_file, output_file):
        self.input_file = input_file
        self.output_file = output_file
        self.input_requests = []
        self.output_events = []
        self.floors = ["B4", "B3", "B2", "B1", "F1", "F2", "F3", "F4", "F5", "F6", "F7"]
        self.elevator_ids = list(range(1, 7))

    def load_data(self):
        try:
            with open(self.input_file, 'r') as f_in, open(self.output_file, 'r') as f_out:
                self.input_requests = [line.strip() for line in f_in.readlines()]
                self.output_events = [line.strip() for line in f_out.readlines()]
        except FileNotFoundError as e:
            raise ValidationError(f"File not found: {e}")

    def validate_input_format(self):
        input_pattern = re.compile(r"\[(\d+\.\d)\](\d+)-PRI-(\d+)-FROM-(B[1-4]|F[1-7])-TO-(B[1-4]|F[1-7])-BY-(\d)")
        for line in self.input_requests:
            if not input_pattern.match(line):
                raise ValidationError(f"Invalid input format: {line}")

    def validate_output_format(self):
        output_pattern = re.compile(r"\[( )*(\d+\.(\d){4})\](ARRIVE|OPEN|CLOSE|IN|OUT)-(.+)")
        for line in self.output_events:
            if not output_pattern.match(line):
                raise ValidationError(f"Invalid output format: {line}")

    def validate_timestamps(self):
        timestamps = []
        for line in self.output_events:
            match = re.match(r"\[(\d+\.\d)\]", line)
            if match:
                timestamps.append(float(match.group(1)))

        for i in range(1, len(timestamps)):
            if timestamps[i] < timestamps[i-1]:
                raise ValidationError(f"Timestamp is not monotonically increasing: {timestamps[i]} < {timestamps[i-1]}")

    def validate_floor_and_elevator_ids(self):
        for line in self.output_events:
            parts = line.split('-')
            event_type = parts[0].split(']')[1]

            if event_type in ["ARRIVE", "OPEN", "CLOSE"]:
                floor = parts[1]
                elevator_id = parts[2]
                if floor not in self.floors:
                    raise ValidationError(f"Invalid floor: {floor}")
                if not elevator_id.isdigit() or int(elevator_id) not in self.elevator_ids:
                    raise ValidationError(f"Invalid elevator ID: {elevator_id}")
            elif event_type in ["IN", "OUT"]:
                floor = parts[2]
                elevator_id = parts[3]
                if floor not in self.floors:
                    raise ValidationError(f"Invalid floor: {floor}")
                if not elevator_id.isdigit() or int(elevator_id) not in self.elevator_ids:
                    raise ValidationError(f"Invalid elevator ID: {elevator_id}")

    def validate_elevator_movement(self):
        elevator_positions = {}  # Store the last position and timestamp of each elevator
        for line in self.output_events:
            parts = line.split('-')
            event_type = parts[0].split(']')[1]
            timestamp = float(parts[0].split('[')[1].split(']')[0])

            if event_type == "CLOSE":
                elevator_id = int(parts[2])
                if elevator_id not in elevator_positions:
                    elevator_positions[elevator_id] = {"floor": "F1", "timestamp": 0.0}  # Initial position
                elevator_positions[elevator_id]["timestamp"] = timestamp
            elif event_type == "ARRIVE":
                floor = parts[1]
                elevator_id = int(parts[2])

                if elevator_id not in elevator_positions:
                    elevator_positions[elevator_id] = {"floor": "F1", "timestamp": 0.0}  # Initial position

                last_floor = elevator_positions[elevator_id]["floor"]
                last_timestamp = elevator_positions[elevator_id]["timestamp"]

                floor_index = self.floors.index(floor)
                last_floor_index = self.floors.index(last_floor)

                if abs(floor_index - last_floor_index) != 1:
                    raise ValidationError(f"Elevator moved more than one floor at a time: {last_floor} -> {floor}")

                time_diff = timestamp - last_timestamp
                if time_diff - 0.4 < -0.001:  # Allow for small floating-point errors
                    raise ValidationError(f"Invalid elevator movement time: {time_diff:.3f}s, expected >0.4s")

                elevator_positions[elevator_id]["floor"] = floor
                elevator_positions[elevator_id]["timestamp"] = timestamp

    def validate_door_operation(self):
        elevator_door_status = {}  # Store the last door status (OPEN or CLOSE) and timestamp of each elevator
        for line in self.output_events:
            parts = line.split('-')
            event_type = parts[0].split(']')[1]
            timestamp = float(parts[0].split('[')[1].split(']')[0])
            
            if event_type == "OPEN":
                floor = parts[1]
                elevator_id = int(parts[2])

                if elevator_id not in elevator_door_status:
                    elevator_door_status[elevator_id] = {"status": "CLOSE", "timestamp": 0.0}

                last_status = elevator_door_status[elevator_id]["status"]
                last_timestamp = elevator_door_status[elevator_id]["timestamp"]

                if last_status == "OPEN":
                    raise ValidationError(f"Door opened before closing: Elevator {elevator_id}")

                elevator_door_status[elevator_id]["status"] = "OPEN"
                elevator_door_status[elevator_id]["timestamp"] = timestamp

            elif event_type == "CLOSE":
                floor = parts[1]
                elevator_id = int(parts[2])

                if elevator_id not in elevator_door_status:
                    raise ValidationError(f"Door closed before opening: Elevator {elevator_id}")

                last_status = elevator_door_status[elevator_id]["status"]
                last_timestamp = elevator_door_status[elevator_id]["timestamp"]

                if last_status == "CLOSE":
                    raise ValidationError(f"Door closed before opening: Elevator {elevator_id}")

                time_diff = timestamp - last_timestamp
                if time_diff - 0.4 < -0.001:
                    raise ValidationError(f"Door operation time less than 0.4s: {time_diff:.1f}s")

                elevator_door_status[elevator_id]["status"] = "CLOSE"
                elevator_door_status[elevator_id]["timestamp"] = timestamp

    def validate_passenger_in_out(self):
        elevator_passengers = {}  # Store the passengers in each elevator
        passenger_requests = {}  # Store the requests of each passenger
        
        # Parse input requests to store passenger information
        input_pattern = re.compile(r"\[(\d+\.\d)\](\d+)-PRI-(\d+)-FROM-(B[1-4]|F[1-7])-TO-(B[1-4]|F[1-7])-BY-(\d)")
        for line in self.input_requests:
            match = input_pattern.match(line)
            if match:
                timestamp, passenger_id, priority, from_floor, to_floor, elevator_id = match.groups()
                passenger_requests[passenger_id] = {
                    "from_floor": from_floor,
                    "to_floor": to_floor,
                    "elevator_id": int(elevator_id),
                }

        for line in self.output_events:
            parts = line.split('-')
            event_type = parts[0].split(']')[1]
            timestamp = float(parts[0].split('[')[1].split(']')[0])

            if event_type == "IN":
                passenger_id = parts[1]
                floor = parts[2]
                elevator_id = int(parts[3])

                if elevator_id not in elevator_passengers:
                    elevator_passengers[elevator_id] = []

                if passenger_id in elevator_passengers[elevator_id]:
                    raise ValidationError(f"Passenger already in elevator: {passenger_id} in Elevator {elevator_id}")

                if passenger_requests[passenger_id]["from_floor"] != floor:
                     raise ValidationError(f"Passenger entered on wrong floor: {passenger_id} on Floor {floor}, expected {passenger_requests[passenger_id]['from_floor']}")

                if passenger_requests[passenger_id]["elevator_id"] != elevator_id:
                    raise ValidationError(f"Passenger entered wrong elevator: {passenger_id} in Elevator {elevator_id}, expected {passenger_requests[passenger_id]['elevator_id']}")
                
                elevator_passengers[elevator_id].append(passenger_id)

            elif event_type == "OUT":
                passenger_id = parts[1]
                floor = parts[2]
                elevator_id = int(parts[3])

                if elevator_id not in elevator_passengers:
                    raise ValidationError(f"Passenger exited from empty elevator: {passenger_id} from Elevator {elevator_id}")

                if passenger_id not in elevator_passengers[elevator_id]:
                    raise ValidationError(f"Passenger not in elevator during exit: {passenger_id} from Elevator {elevator_id}")

                if passenger_requests[passenger_id]["to_floor"] != floor:
                    raise ValidationError(f"Passenger exited on wrong floor: {passenger_id} on Floor {floor}, expected {passenger_requests[passenger_id]['to_floor']}")

                elevator_passengers[elevator_id].remove(passenger_id)

    def validate_elevator_capacity(self):
        elevator_passengers = {}  # Store the passengers in each elevator

        for line in self.output_events:
            parts = line.split('-')
            event_type = parts[0].split(']')[1]
            timestamp = float(parts[0].split('[')[1].split(']')[0])

            if event_type == "IN":
                passenger_id = parts[1]
                elevator_id = int(parts[3])

                if elevator_id not in elevator_passengers:
                    elevator_passengers[elevator_id] = []

                elevator_passengers[elevator_id].append(passenger_id)

                if len(elevator_passengers[elevator_id]) > 6:
                    raise ValidationError(f"Elevator capacity exceeded: Elevator {elevator_id} has {len(elevator_passengers[elevator_id])} passengers")

            elif event_type == "OUT":
                passenger_id = parts[1]
                elevator_id = int(parts[3])

                if elevator_id not in elevator_passengers:
                    raise ValidationError(f"Passenger exited from empty elevator: {passenger_id} from Elevator {elevator_id}")

                if passenger_id not in elevator_passengers[elevator_id]:
                    raise ValidationError(f"Passenger not in elevator during exit: {passenger_id} from Elevator {elevator_id}")

                elevator_passengers[elevator_id].remove(passenger_id)

    def validate_initial_state(self):
        # Although the output doesn't explicitly show the initial state,
        # we need to ensure the first action is compatible with the initial state:
        # All elevators are at F1, doors closed, and no passengers inside.
        if not self.output_events:
            return  # No events to validate

        first_event = self.output_events[0]
        parts = first_event.split('-')
        event_type = parts[0].split(']')[1]

        if event_type == "OPEN":
            floor = parts[1]
            elevator_id = int(parts[2])
            if floor != "F1":
                raise ValidationError(f"First action OPEN is on wrong floor: Elevator {elevator_id} on Floor {floor}, expected F1")
        elif event_type == "ARRIVE":
            floor = parts[1]
            elevator_id = int(parts[2])
            if floor != "F2" and floor != "B1":
                raise ValidationError(f"First action ARRIVE is on wrong floor: Elevator {elevator_id} on Floor {floor}, expected F2/B1")
        elif event_type == "IN":
            raise ValidationError(f"First action cannot be IN")
        elif event_type == "OUT":
            raise ValidationError(f"First action cannot be OUT")
        elif event_type == "CLOSE":
            floor = parts[1]
            elevator_id = int(parts[2])
            if floor != "F1":
                raise ValidationError(f"First action CLOSE is on wrong floor: Elevator {elevator_id} on Floor {floor}, expected F1")

    def validate_final_state(self):
        # - All passenger requests must be completed (OUT on their target floor)
        # - No passengers left in any elevator
        # - All elevators must be in CLOSE state

        passenger_requests = {}
        for line in self.input_requests:
            match = re.match(r"\[(\d+\.\d)\](P\d+)-PRI-(\d+)-FROM-(B[1-4]|F[1-7])-TO-(B[1-4]|F[1-7])-BY-(\d)", line)
            if match:
                timestamp, passenger_id, priority, from_floor, to_floor, elevator_id = match.groups()
                passenger_requests[passenger_id] = {
                    "from_floor": from_floor,
                    "to_floor": to_floor,
                    "elevator_id": int(elevator_id),
                    "completed": False,
                }

        elevator_passengers = {}
        for i in range(1, 7):
            elevator_passengers[i] = []

        for line in self.output_events:
            parts = line.split('-')
            event_type = parts[0].split(']')[1]

            if event_type == "IN":
                passenger_id = parts[1]
                elevator_id = int(parts[3])
                elevator_passengers[elevator_id].append(passenger_id)
            elif event_type == "OUT":
                passenger_id = parts[1]
                floor = parts[2]
                elevator_id = int(parts[3])
                elevator_passengers[elevator_id].remove(passenger_id)
                if passenger_requests.get(passenger_id):
                    if passenger_requests[passenger_id]["to_floor"] == floor:
                        passenger_requests[passenger_id]["completed"] = True

        # Check if all requests are completed
        for passenger_id, request in passenger_requests.items():
            if not request["completed"]:
                raise ValidationError(f"Passenger request not completed: {passenger_id}")

        # Check if any passengers are left in elevators
        for elevator_id, passengers in elevator_passengers.items():
            if passengers:
                raise ValidationError(f"Passengers left in elevator {elevator_id}: {passengers}")

        # Check if the last action is CLOSE
        if self.output_events:
            last_event = self.output_events[-1]
            parts = last_event.split('-')
            event_type = parts[0].split(']')[1]
            if event_type != "CLOSE":
                raise ValidationError("Last action must be CLOSE")

    def validate(self):
        try:
            self.load_data()
            self.validate_input_format()
            self.validate_output_format()
            self.validate_timestamps()
            self.validate_floor_and_elevator_ids()
            self.validate_elevator_movement()
            self.validate_door_operation()
            self.validate_passenger_in_out()
            self.validate_elevator_capacity()
            self.validate_initial_state()
            self.validate_final_state()
            print("Accepted")

        except ValidationError as e:
            print(f"Validation Error: {e}")
            exit(1)
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            exit(1)


def main():
    parser = argparse.ArgumentParser(description="Validate elevator simulation output.")
    parser.add_argument("--input_file", default="/root/OO_unit2/input.txt", help="Path to the input file (generated by gen.py).")
    parser.add_argument("--output_file", default="/root/OO_unit2/output.txt", help="Path to the output file (from the elevator simulation).")

    args = parser.parse_args()

    validator = ElevatorValidator(args.input_file, args.output_file)
    validator.validate()


if __name__ == "__main__":
    main()
