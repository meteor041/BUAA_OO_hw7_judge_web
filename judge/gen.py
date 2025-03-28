import random
import time
import argparse

def generate_request(passenger_id, timestamp, floors, elevator_ids, priority):
    from_floor = random.choice(floors)
    to_floor = random.choice(floors)
    while from_floor == to_floor:
        to_floor = random.choice(floors)

    elevator_id = random.choice(elevator_ids)

    return f"[{timestamp:.1f}]{passenger_id}-PRI-{priority}-FROM-{from_floor}-TO-{to_floor}-BY-{elevator_id}"

def generate_random_floats_one_decimal(num: int, min_val: float = 0.0, max_val: float = 1.0):
    """
    生成一个包含指定数量随机浮点数的列表, 每个浮点数精确到小数点后一位。

    Args:
        num: 需要生成的随机浮点数的数量。
        min_val: 随机浮点数的最小值 (包含)。默认为 0.0。
        max_val: 随机浮点数的最大值 (包含)。默认为 1.0。

    Returns:
        一个包含 num 个随机浮点数的列表, 每个数都精确到一位小数。

    Raises:
        ValueError: 如果 num 为负数或 min_val > max_val。
    """
    if num < 1:
        raise ValueError("生成的数量 'num' 不能小于 1")
    if min_val > max_val:
        raise ValueError(f"最小值 'min_val' ({min_val}) 不能大于最大值 'max_val' ({max_val})")

    random_list = list()
    for _ in range(num):
        # 1. 生成一个在 min_val 和 max_val 之间的原始随机浮点数
        raw_float = random.uniform(min_val, max_val)

        # 2. 通过乘以10, 四舍五入到整数, 再除以10.0 来确保一位小数精度
        #    直接使用 round(raw_float, 1) 可能因浮点数表示问题产生微小误差 (如 0.300000000004)
        #    这种方法通常能更好地控制精度值。
        precise_float = round(raw_float * 10) / 10.0

        random_list.append(precise_float)

    return sorted(random_list)

def main():
    parser = argparse.ArgumentParser(description="Generate elevator simulation requests.")
    parser.add_argument("--num_requests", type=int, default=50, help="Number of requests to generate (1-100).")
    parser.add_argument("--time_limit", type=int, default=50, help="Limit of input time(1.0-50.0)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")

    args = parser.parse_args()

    if not 1 <= args.num_requests <= 100:
        print("Error: Number of requests must be between 1 and 100.")
        return

    if args.seed is not None:
        random.seed(args.seed)

    floors = ["B4", "B3", "B2", "B1", "F1", "F2", "F3", "F4", "F5", "F6", "F7"]
    elevator_ids = list(range(1, 7))
    passenger_id_counter = 1
    timestamps = generate_random_floats_one_decimal(args.num_requests, min_val=1.0, max_val=args.time_limit)
    for i in range(args.num_requests):
        passenger_id = f"{passenger_id_counter}"
        priority = random.randint(1, 100)
        timestamp = timestamps[i]
        request = generate_request(passenger_id, timestamp, floors, elevator_ids, priority)
        print(request)

        passenger_id_counter += 1


if __name__ == "__main__":
    main()
