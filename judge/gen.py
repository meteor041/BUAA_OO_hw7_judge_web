import random
import time
import argparse
from collections import defaultdict


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

def generate_and_distribute(k, n, gap):
    """
    随机生成k个1到n之间的浮点数（小数点后一位），分配到6个列表中，
    确保同一列表中的元素差值大于gap
    
    参数:
        k: 要生成的浮点数总数
        n: 最大值范围(1到n)
        gap: 同一列表中元素的最小差值
        
    返回:
        包含6个列表的字典
    """
    # 生成k个1到n之间的随机浮点数（保留一位小数）
    numbers = sorted(round(random.uniform(1, n), 1) for _ in range(k))
    
    # 初始化6个列表
    lists = defaultdict(list)
    
    for num in numbers:
        assigned = False
        
        # 尝试将数字分配到合适的列表中
        for list_num in range(6):
            # 检查当前列表是否为空，或者与所有现有元素的差值大于gap
            if not lists[list_num] or all(abs(num - x) > gap for x in lists[list_num]):
                lists[list_num].append(num)
                assigned = True
                break
        
        # 如果没有列表满足条件，则分配到元素最少的列表
        if not assigned:
            min_len_list = min(lists.keys(), key=lambda x: len(lists[x]))
            lists[min_len_list].append(num)
    
    return dict(lists)

def main():
    parser = argparse.ArgumentParser(description="Generate elevator simulation requests.")
    parser.add_argument("--num_requests", type=int, default=50, help="Number of requests to generate (1-100).")
    parser.add_argument("--time_limit", type=int, default=50, help="Limit of input time(1.0-50.0)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    parser.add_argument("--duplicate_times", type=int, default=1, help="Number of requests to generate.")
    parser.add_argument("--num_schedule", type=int, default=1, help="Number of schedule requests.")
    parser.add_argument("--schedule_gap", type=int, default=10, help="Minimum time gap between schedule requests")
    args = parser.parse_args()

    if not 1 <= args.num_requests <= 100:
        print("Error: Number of requests must be between 1 and 100.")
        return

    if args.seed is not None:
        random.seed(args.seed)

    floors = ["B4", "B3", "B2", "B1", "F1", "F2", "F3", "F4", "F5", "F6",  "F7"]
    sche_floors = ["B2", "B1", "F1", "F2", "F3", "F4", "F5"]
    passenger_id_counter =0
    timestamps = generate_random_floats_one_decimal(args.num_requests, min_val=1.0, max_val=args.time_limit)
    elevator_used_count = [0] * 11
    passengers_ids = list(range(0, args.num_requests * args.duplicate_times))
    random.shuffle(passengers_ids)
    def generate_request(timestamp, floors, priority, duplicate_times):
        nonlocal passenger_id_counter
        nonlocal elevator_used_count
        from_floor = random.choice(floors)
        to_floor = random.choice(floors)
        while from_floor == to_floor:
            to_floor = random.choice(floors)
        s = ''
        for _ in range(1, duplicate_times + 1):
            s += f"[{timestamp:.1f}]{passengers_ids[passenger_id_counter]}-PRI-{priority}-FROM-{from_floor}-TO-{to_floor}\n"
            passenger_id_counter += 1
        return s
    ans = defaultdict(list)
    for i in range(args.num_requests):
        priority = random.randint(1, 2)
        timestamp = timestamps[i]
        request = generate_request(timestamp, floors, priority, args.duplicate_times)
        ans[timestamp].append(request)
    schedule_timesatmps = generate_and_distribute(args.num_schedule, args.time_limit, args.schedule_gap)
    for i in range(6):
        if i not in schedule_timesatmps.keys():
            continue
        for time in schedule_timesatmps[i]:
            elevator_id = random.randint(1, 6)
            speed = random.choice([0.2, 0.3, 0.4, 0.5])
            to_floor = random.choice(sche_floors)
            request =  f"[{time:.1f}]SCHE-{elevator_id}-{speed}-{to_floor}\n"
            ans[time].append(request)
    sorted_ans = {k : ans[k] for k in sorted(ans.keys())}
    for l in sorted_ans.values():
        for s in l:
            print(s, end="")
        



if __name__ == "__main__":
    main()
