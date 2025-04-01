#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import sys
import re
from collections import defaultdict, deque

class ElevatorState:
    """电梯状态类，用于跟踪每部电梯的状态"""
    def __init__(self, elevator_id):
        self.id = elevator_id
        self.floor = "F1"  # 初始位置为F1层
        self.door_open = False  # 初始状态门关闭
        self.passengers = set()  # 电梯内的乘客ID集合
        self.speed = 0.4  # 默认速度0.4秒/层
        self.in_schedule = False  # 是否在临时调度中
        self.schedule_target = None  # 临时调度目标楼层
        self.schedule_accept_time = None  # 接收临时调度的时间
        self.schedule_begin_time = None  # 开始临时调度的时间
        self.last_arrive_time = 0  # 上次到达时间，用于验证移动速度
        self.received_passengers = set()  # 已接收但尚未进入电梯的乘客

    def __str__(self):
        return f"电梯{self.id}: 楼层={self.floor}, 门={'开' if self.door_open else '关'}, 乘客={self.passengers}, 速度={self.speed}, 临时调度={self.in_schedule}"


class PassengerState:
    """乘客状态类，用于跟踪每位乘客的状态"""
    def __init__(self, passenger_id, from_floor, to_floor, priority, request_time):
        self.id = passenger_id
        self.from_floor = from_floor
        self.to_floor = to_floor
        self.priority = priority
        self.request_time = request_time
        self.in_elevator = False  # 是否在电梯内
        self.current_floor = from_floor  # 当前所在楼层
        self.assigned_elevator = None  # 分配的电梯ID
        self.completed = False  # 是否已完成请求
        self.out_times = 0  # 出电梯次数

    def __str__(self):
        return f"乘客{self.id}: 从{self.from_floor}到{self.to_floor}, 优先级={self.priority}, 当前楼层={self.current_floor}, 分配电梯={self.assigned_elevator}, 完成={self.completed}"


class Judge:
    """电梯模拟程序输出验证器"""
    def __init__(self):
        # 楼层列表，从低到高
        self.floors = ["B4", "B3", "B2", "B1", "F1", "F2", "F3", "F4", "F5", "F6", "F7"]
        self.floor_index = {floor: idx for idx, floor in enumerate(self.floors)}
        
        # 状态跟踪
        self.elevators = {i: ElevatorState(i) for i in range(1, 7)}  # 6部电梯
        self.passengers = {}  # 乘客状态字典
        self.last_timestamp = 0  # 上一条输出的时间戳
        
        # 输入和输出解析的正则表达式
        self.input_passenger_pattern = re.compile(r'\[(\d+\.\d+)\](\d+)-PRI-(\d+)-FROM-([BF]\d+)-TO-([BF]\d+)')
        self.input_schedule_pattern = re.compile(r'\[(\d+\.\d+)\]SCHE-(\d+)-(\d+\.\d+)-([BF]\d+)')
        
        self.output_sche_accept_pattern = re.compile(r'\[\s*(\d+\.\d+)\]SCHE-ACCEPT-(\d+)-(\d+\.\d+)-([BF]\d+)')
        self.output_sche_begin_pattern = re.compile(r'\[\s*(\d+\.\d+)\]SCHE-BEGIN-(\d+)')
        self.output_sche_end_pattern = re.compile(r'\[\s*(\d+\.\d+)\]SCHE-END-(\d+)')
        self.output_arrive_pattern = re.compile(r'\[\s*(\d+\.\d+)\]ARRIVE-([BF]\d+)-(\d+)')
        self.output_open_pattern = re.compile(r'\[\s*(\d+\.\d+)\]OPEN-([BF]\d+)-(\d+)')
        self.output_close_pattern = re.compile(r'\[\s*(\d+\.\d+)\]CLOSE-([BF]\d+)-(\d+)')
        self.output_receive_pattern = re.compile(r'\[\s*(\d+\.\d+)\]RECEIVE-(\d+)-(\d+)')
        self.output_in_pattern = re.compile(r'\[\s*(\d+\.\d+)\]IN-(\d+)-([BF]\d+)-(\d+)')
        self.output_out_pattern = re.compile(r'\[\s*(\d+\.\d+)\]OUT-([SF])-(\d+)-([BF]\d+)-(\d+)')
        
        # 统计信息
        self.passenger_count = 0
        self.schedule_count = 0

    def parse_input(self, input_file):
        """解析输入文件"""
        with open(input_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # 解析乘客请求
                passenger_match = self.input_passenger_pattern.match(line)
                if passenger_match:
                    timestamp, passenger_id, priority, from_floor, to_floor = passenger_match.groups()
                    timestamp = float(timestamp)
                    passenger_id = int(passenger_id)
                    priority = int(priority)
                    
                    # 验证乘客请求的有效性
                    if from_floor == to_floor:
                        return False, f"乘客请求无效: 起点层({from_floor})与终点层({to_floor})相同"
                    
                    # 创建乘客状态对象
                    self.passengers[passenger_id] = PassengerState(
                        passenger_id, from_floor, to_floor, priority, timestamp
                    )
                    self.passenger_count += 1
                    continue
                
                # 解析临时调度请求
                schedule_match = self.input_schedule_pattern.match(line)
                if schedule_match:
                    timestamp, elevator_id, speed, target_floor = schedule_match.groups()
                    timestamp = float(timestamp)
                    elevator_id = int(elevator_id)
                    speed = float(speed)
                    
                    # 验证临时调度请求的有效性
                    if elevator_id < 1 or elevator_id > 6:
                        return False, f"临时调度请求无效: 电梯ID({elevator_id})超出范围[1-6]"
                    
                    if speed not in [0.2, 0.3, 0.4, 0.5]:
                        return False, f"临时调度请求无效: 临时运行速度({speed})不在允许范围内[0.2, 0.3, 0.4, 0.5]"
                    
                    if target_floor not in ["B2", "B1", "F1", "F2", "F3", "F4", "F5"]:
                        return False, f"临时调度请求无效: 目标楼层({target_floor})不在允许范围内[B2, B1, F1, F2, F3, F4, F5]"
                    
                    self.schedule_count += 1
                    continue
        
        # 验证乘客请求数量
        if self.passenger_count < 1 or self.passenger_count > 100:
            return False, f"乘客请求数量({self.passenger_count})不在允许范围内[1-100]"
        
        return True, "输入解析成功"

    def validate_output(self, input_file, output_file):
        """验证输出文件是否符合规范"""
        # 首先解析输入文件
        success, message = self.parse_input(input_file)
        if not success:
            return False, message
        
        # 然后验证输出文件
        with open(output_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                # 验证时间戳非递减
                timestamp_match = re.match(r'\[\s*(\d+\.\d+)\]', line)
                if not timestamp_match:
                    return False, f"第{line_num}行: 无法解析时间戳 - {line}"
                
                timestamp = float(timestamp_match.group(1))
                if timestamp < self.last_timestamp:
                    return False, f"第{line_num}行: 时间戳({timestamp})小于上一条输出的时间戳({self.last_timestamp})"
                self.last_timestamp = timestamp
                
                # 解析并验证各种输出
                result, message = self.validate_line(line, line_num)
                if not result:
                    return False, message
        
        # 验证所有乘客请求是否完成
        for passenger_id, passenger in self.passengers.items():
            if not passenger.completed:
                return False, f"乘客{passenger_id}的请求未完成"
        
        # 验证所有电梯是否处于关门状态
        for elevator_id, elevator in self.elevators.items():
            if elevator.door_open:
                return False, f"程序终止时电梯{elevator_id}的门未关闭"
            if elevator.passengers:
                return False, f"程序终止时电梯{elevator_id}内仍有乘客: {elevator.passengers}"
            if elevator.in_schedule:
                return False, f"程序终止时电梯{elevator_id}仍在临时调度中"
        
        return True, "验证通过"

    def validate_line(self, line, line_num):
        """验证单行输出"""
        # SCHE-ACCEPT: 接收临时调度请求
        match = self.output_sche_accept_pattern.match(line)
        if match:
            timestamp, elevator_id, speed, target_floor = match.groups()
            timestamp = float(timestamp)
            elevator_id = int(elevator_id)
            speed = float(speed)
            
            # 验证电梯ID
            if elevator_id < 1 or elevator_id > 6:
                return False, f"第{line_num}行: 电梯ID({elevator_id})超出范围[1-6]"
            
            # 记录临时调度信息
            elevator = self.elevators[elevator_id]
            elevator.schedule_accept_time = timestamp
            elevator.schedule_target = target_floor
            elevator.speed = speed
            
            return True, ""
        
        # SCHE-BEGIN: 开始临时调度
        match = self.output_sche_begin_pattern.match(line)
        if match:
            timestamp, elevator_id = match.groups()
            timestamp = float(timestamp)
            elevator_id = int(elevator_id)
            
            # 验证电梯ID
            if elevator_id < 1 or elevator_id > 6:
                return False, f"第{line_num}行: 电梯ID({elevator_id})超出范围[1-6]"
            
            elevator = self.elevators[elevator_id]
            
            # 验证是否已接收临时调度请求
            if elevator.schedule_accept_time is None:
                return False, f"第{line_num}行: 电梯{elevator_id}未接收临时调度请求就开始临时调度"
            
            # 验证响应时间
            if timestamp - elevator.schedule_accept_time > 6:
                return False, f"第{line_num}行: 电梯{elevator_id}的临时调度响应时间({timestamp - elevator.schedule_accept_time}s)超过6s"
            
            # 验证电梯门是否关闭
            if elevator.door_open:
                return False, f"第{line_num}行: 电梯{elevator_id}开始临时调度时门未关闭"
            
            # 更新电梯状态
            elevator.in_schedule = True
            elevator.schedule_begin_time = timestamp
            
            # 取消该电梯之前的所有RECEIVE
            for passenger in self.passengers.values():
                if passenger.assigned_elevator == elevator_id and not passenger.in_elevator:
                    passenger.assigned_elevator = None
            
            elevator.received_passengers.clear()
            
            return True, ""
        
        # SCHE-END: 结束临时调度
        match = self.output_sche_end_pattern.match(line)
        if match:
            timestamp, elevator_id = match.groups()
            timestamp = float(timestamp)
            elevator_id = int(elevator_id)
            
            # 验证电梯ID
            if elevator_id < 1 or elevator_id > 6:
                return False, f"第{line_num}行: 电梯ID({elevator_id})超出范围[1-6]"
            
            elevator = self.elevators[elevator_id]
            
            # 验证是否在临时调度中
            if not elevator.in_schedule:
                return False, f"第{line_num}行: 电梯{elevator_id}未开始临时调度就结束临时调度"
            
            # 验证是否已到达目标楼层
            if elevator.floor != elevator.schedule_target:
                return False, f"第{line_num}行: 电梯{elevator_id}未到达目标楼层({elevator.schedule_target})就结束临时调度，当前楼层为{elevator.floor}"
            
            # 验证电梯门是否关闭
            if elevator.door_open:
                return False, f"第{line_num}行: 电梯{elevator_id}结束临时调度时门未关闭"
            
            # 验证电梯内是否有乘客
            if elevator.passengers:
                return False, f"第{line_num}行: 电梯{elevator_id}结束临时调度时电梯内仍有乘客: {elevator.passengers}"
            
            # 更新电梯状态
            elevator.in_schedule = False
            elevator.schedule_target = None
            elevator.schedule_accept_time = None
            elevator.schedule_begin_time = None
            elevator.speed = 0.4  # 恢复默认速度
            
            return True, ""
        
        # ARRIVE: 电梯到达某一层
        match = self.output_arrive_pattern.match(line)
        if match:
            timestamp, floor, elevator_id = match.groups()
            timestamp = float(timestamp)
            elevator_id = int(elevator_id)
            
            # 验证电梯ID和楼层
            if elevator_id < 1 or elevator_id > 6:
                return False, f"第{line_num}行: 电梯ID({elevator_id})超出范围[1-6]"
            
            if floor not in self.floors:
                return False, f"第{line_num}行: 楼层({floor})不在允许范围内[B4-F7]"
            
            elevator = self.elevators[elevator_id]
            
            # 验证电梯门是否关闭
            if elevator.door_open:
                return False, f"第{line_num}行: 电梯{elevator_id}移动时门未关闭"
            
            # 验证移动是否合法（非空电梯或有RECEIVE的乘客）
            if not elevator.in_schedule and not elevator.passengers and not elevator.received_passengers:
                return False, f"第{line_num}行: 电梯{elevator_id}为空且未RECEIVE到任何乘客，移动不合法"
            
            # 验证移动是否跨层
            current_floor_idx = self.floor_index[elevator.floor]
            target_floor_idx = self.floor_index[floor]
            if abs(current_floor_idx - target_floor_idx) != 1:
                return False, f"第{line_num}行: 电梯{elevator_id}从{elevator.floor}到{floor}跨层移动"
            
            # 验证移动速度
            expected_time = elevator.speed
            if timestamp - elevator.last_arrive_time + 0.0001 < expected_time:
                return False, f"第{line_num}行: 电梯{elevator_id}移动速度过快，实际用时{timestamp - elevator.last_arrive_time}s，期望至少{expected_time}s"
            
            # 更新电梯状态
            elevator.floor = floor
            elevator.last_arrive_time = timestamp
            
            return True, ""
        
        # OPEN: 电梯开门
        match = self.output_open_pattern.match(line)
        if match:
            timestamp, floor, elevator_id = match.groups()
            timestamp = float(timestamp)
            elevator_id = int(elevator_id)
            
            # 验证电梯ID和楼层
            if elevator_id < 1 or elevator_id > 6:
                return False, f"第{line_num}行: 电梯ID({elevator_id})超出范围[1-6]"
            
            if floor not in self.floors:
                return False, f"第{line_num}行: 楼层({floor})不在允许范围内[B4-F7]"
            
            elevator = self.elevators[elevator_id]
            
            # 验证电梯是否在该楼层
            if elevator.floor != floor:
                return False, f"第{line_num}行: 电梯{elevator_id}不在{floor}层，无法开门"
            
            # 验证电梯门是否已经开启
            if elevator.door_open:
                return False, f"第{line_num}行: 电梯{elevator_id}的门已经开启，不能重复开门"
            
            # 更新电梯状态
            elevator.door_open = True
            
            return True, ""
        
        # CLOSE: 电梯关门
        match = self.output_close_pattern.match(line)
        if match:
            timestamp, floor, elevator_id = match.groups()
            timestamp = float(timestamp)
            elevator_id = int(elevator_id)
            
            # 验证电梯ID和楼层
            if elevator_id < 1 or elevator_id > 6:
                return False, f"第{line_num}行: 电梯ID({elevator_id})超出范围[1-6]"
            
            if floor not in self.floors:
                return False, f"第{line_num}行: 楼层({floor})不在允许范围内[B4-F7]"
            
            elevator = self.elevators[elevator_id]
            
            # 验证电梯是否在该楼层
            if elevator.floor != floor:
                return False, f"第{line_num}行: 电梯{elevator_id}不在{floor}层，无法关门"
            
            # 验证电梯门是否已经开启
            if not elevator.door_open:
                return False, f"第{line_num}行: 电梯{elevator_id}的门已经关闭，不能重复关门"
            
            # 更新电梯状态
            elevator.door_open = False
            
            return True, ""
        
        # RECEIVE: 电梯接收分配
        match = self.output_receive_pattern.match(line)
        if match:
            timestamp, passenger_id, elevator_id = match.groups()
            timestamp = float(timestamp)
            passenger_id = int(passenger_id)
            elevator_id = int(elevator_id)
            
            # 验证电梯ID和乘客ID
            if elevator_id < 1 or elevator_id > 6:
                return False, f"第{line_num}行: 电梯ID({elevator_id})超出范围[1-6]"
            
            if passenger_id not in self.passengers:
                return False, f"第{line_num}行: 乘客ID({passenger_id})不存在"
            
            passenger = self.passengers[passenger_id]
            elevator = self.elevators[elevator_id]
            
            # 验证乘客是否在电梯外
            if passenger.in_elevator:
                return False, f"第{line_num}行: 乘客{passenger_id}已在电梯内，不能被RECEIVE"
            
            # 验证乘客是否已被分配给其他电梯
            if passenger.assigned_elevator is not None:
                return False, f"第{line_num}行: 乘客{passenger_id}已被分配给电梯{passenger.assigned_elevator}，不能重复分配"
            
            # 验证乘客请求是否已完成
            if passenger.completed:
                return False, f"第{line_num}行: 乘客{passenger_id}的请求已完成，不能被RECEIVE"
            
            # 更新乘客和电梯状态
            passenger.assigned_elevator = elevator_id
            elevator.received_passengers.add(passenger_id)
            
            return True, ""
        
        # IN: 乘客进入电梯
        match = self.output_in_pattern.match(line)
        if match:
            timestamp, passenger_id, floor, elevator_id = match.groups()
            timestamp = float(timestamp)
            passenger_id = int(passenger_id)
            elevator_id = int(elevator_id)
            
            # 验证电梯ID、乘客ID和楼层
            if elevator_id < 1 or elevator_id > 6:
                return False, f"第{line_num}行: 电梯ID({elevator_id})超出范围[1-6]"
            
            if passenger_id not in self.passengers:
                return False, f"第{line_num}行: 乘客ID({passenger_id})不存在"
            
            if floor not in self.floors:
                return False, f"第{line_num}行: 楼层({floor})不在允许范围内[B4-F7]"
            
            passenger = self.passengers[passenger_id]
            elevator = self.elevators[elevator_id]
            
            # 验证电梯是否在该楼层
            if elevator.floor != floor:
                return False, f"第{line_num}行: 电梯{elevator_id}不在{floor}层，乘客{passenger_id}无法进入"
            
            # 验证电梯门是否开启
            if not elevator.door_open:
                return False, f"第{line_num}行: 电梯{elevator_id}的门未开启，乘客{passenger_id}无法进入"
            
            # 验证乘客是否在电梯外
            if passenger.in_elevator:
                return False, f"第{line_num}行: 乘客{passenger_id}已在电梯内，不能重复进入"
            
            # 验证乘客是否在该楼层
            if passenger.current_floor != floor:
                return False, f"第{line_num}行: 乘客{passenger_id}不在{floor}层，无法进入电梯"
            
            # 验证乘客是否被分配给该电梯
            if passenger.assigned_elevator != elevator_id:
                return False, f"第{line_num}行: 乘客{passenger_id}未被分配给电梯{elevator_id}，无法进入"
            
            # 验证电梯是否在临时调度中
            if elevator.in_schedule:
                return False, f"第{line_num}行: 电梯{elevator_id}在临时调度中，乘客{passenger_id}无法进入"
            
            # 验证电梯容量
            if len(elevator.passengers) >= 6:
                return False, f"第{line_num}行: 电梯{elevator_id}已满载(6人)，乘客{passenger_id}无法进入"
            
            # 更新乘客和电梯状态
            passenger.in_elevator = True
            elevator.passengers.add(passenger_id)
            elevator.received_passengers.discard(passenger_id)
            
            return True, ""
        
        # OUT: 乘客离开电梯
        match = self.output_out_pattern.match(line)
        if match:
            timestamp, status, passenger_id, floor, elevator_id = match.groups()
            timestamp = float(timestamp)
            passenger_id = int(passenger_id)
            elevator_id = int(elevator_id)
            
            # 验证电梯ID、乘客ID和楼层
            if elevator_id < 1 or elevator_id > 6:
                return False, f"第{line_num}行: 电梯ID({elevator_id})超出范围[1-6]"
            
            if passenger_id not in self.passengers:
                return False, f"第{line_num}行: 乘客ID({passenger_id})不存在"
            
            if floor not in self.floors:
                return False, f"第{line_num}行: 楼层({floor})不在允许范围内[B4-F7]"
            
            passenger = self.passengers[passenger_id]
            elevator = self.elevators[elevator_id]
            
            # 验证电梯是否在该楼层
            if elevator.floor != floor:
                return False, f"第{line_num}行: 电梯{elevator_id}不在{floor}层，乘客{passenger_id}无法离开"
            
            # 验证电梯门是否开启
            if not elevator.door_open:
                return False, f"第{line_num}行: 电梯{elevator_id}的门未开启，乘客{passenger_id}无法离开"
            
            # 验证乘客是否在电梯内
            if not passenger.in_elevator:
                return False, f"第{line_num}行: 乘客{passenger_id}不在电梯内，无法离开"
            
            # 验证乘客是否在该电梯内
            if passenger_id not in elevator.passengers:
                return False, f"第{line_num}行: 乘客{passenger_id}不在电梯{elevator_id}内，无法离开"
            
            # 验证电梯是否在临时调度中且未到达目标楼层
            if elevator.in_schedule and elevator.schedule_target != floor:
                return False, f"第{line_num}行: 电梯{elevator_id}在临时调度中，乘客{passenger_id}无法离开"
            
            # 验证状态标志
            if status == 'S':
                # 成功到达目标楼层
                if floor != passenger.to_floor:
                    return False, f"第{line_num}行: 乘客{passenger_id}的目标楼层为{passenger.to_floor}，但在{floor}层标记为成功离开"
                passenger.completed = True
            elif status == 'F':
                # 中途下电梯
                passenger.out_times += 1
            else:
                return False, f"第{line_num}行: 无效的OUT状态标志({status})，应为S或F"
            
            # 更新乘客和电梯状态
            passenger.in_elevator = False
            passenger.current_floor = floor
            passenger.assigned_elevator = None  # 取消分配
            elevator.passengers.remove(passenger_id)
            
            return True, ""
        
        # 未识别的输出格式
        return False, f"第{line_num}行: 无法识别的输出格式 - {line}"

def main():
    parser = argparse.ArgumentParser(description="Validate elevator simulation output.")
    parser.add_argument("--input_file", default="input.txt", help="Path to the input file (generated by gen.py).")
    parser.add_argument("--output_file", default="output.txt",
                        help="Path to the output file (from the elevator simulation).")

    args = parser.parse_args()
    
    input_file = parser.input_file
    output_file = parser.output_file
    
    judge = Judge()
    result, message = judge.validate_output(input_file, output_file)
    
    if result:
        print("Accepted: 输出验证通过")
        sys.exit(0)
    else:
        print(f"Error: {message}")
        sys.exit(1)

if __name__ == "__main__":
    main()
