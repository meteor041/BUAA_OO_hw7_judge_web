#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
from collections import defaultdict

class Score:
    """电梯模拟程序性能评估"""
    def __init__(self):
        # 正则表达式模式
        self.input_passenger_pattern = re.compile(r'\[(\d+\.\d+)\](\d+)-PRI-(\d+)-FROM-([BF]\d+)-TO-([BF]\d+)')
        
        self.output_arrive_pattern = re.compile(r'\[\s*(\d+\.\d+)\]ARRIVE-([BF]\d+)-(\d+)')
        self.output_open_pattern = re.compile(r'\[\s*(\d+\.\d+)\]OPEN-([BF]\d+)-(\d+)')
        self.output_close_pattern = re.compile(r'\[\s*(\d+\.\d+)\]CLOSE-([BF]\d+)-(\d+)')
        self.output_out_pattern = re.compile(r'\[\s*(\d+\.\d+)\]OUT-([SF])-(\d+)-([BF]\d+)-(\d+)')
        
        # 统计数据
        self.passenger_requests = {}  # 乘客请求信息: {passenger_id: (request_time, priority, from_floor, to_floor)}
        self.passenger_completions = {}  # 乘客完成信息: {passenger_id: completion_time}
        
        self.arrive_count = 0  # ARRIVE操作计数
        self.open_count = 0    # OPEN操作计数
        self.close_count = 0   # CLOSE操作计数
        
        self.final_timestamp = 0.0  # 最后一条输出的时间戳
    
    def parse_input(self, input_file):
        """解析输入文件，提取乘客请求信息"""
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
                    
                    # 存储乘客请求信息
                    self.passenger_requests[passenger_id] = (timestamp, priority, from_floor, to_floor)
    
    def parse_output(self, output_file):
        """解析输出文件，计算性能指标"""
        with open(output_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                # 提取时间戳
                timestamp_match = re.match(r'\[\s*(\d+\.\d+)\]', line)
                if timestamp_match:
                    timestamp = float(timestamp_match.group(1))
                    self.final_timestamp = max(self.final_timestamp, timestamp)
                
                # 统计ARRIVE操作
                if self.output_arrive_pattern.match(line):
                    self.arrive_count += 1
                    continue
                
                # 统计OPEN操作
                if self.output_open_pattern.match(line):
                    self.open_count += 1
                    continue
                
                # 统计CLOSE操作
                if self.output_close_pattern.match(line):
                    self.close_count += 1
                    continue
                
                # 记录乘客完成时间
                out_match = self.output_out_pattern.match(line)
                if out_match:
                    timestamp, status, passenger_id, floor, elevator_id = out_match.groups()
                    timestamp = float(timestamp)
                    passenger_id = int(passenger_id)
                    
                    # 只记录成功完成的乘客
                    if status == 'S':
                        self.passenger_completions[passenger_id] = timestamp
    
    def calculate_average_completion_time(self):
        """计算平均完成时间(WT)"""
        total_weighted_time = 0.0
        total_weight = 0.0
        
        for passenger_id, completion_time in self.passenger_completions.items():
            if passenger_id in self.passenger_requests:
                request_time, priority, _, _ = self.passenger_requests[passenger_id]
                completion_duration = completion_time - request_time
                
                # 使用优先级作为权重
                total_weighted_time += completion_duration * priority
                total_weight += priority
        
        # 避免除以零
        if total_weight == 0:
            return 0.0
        
        return total_weighted_time / total_weight
    
    def calculate_power_consumption(self):
        """计算系统耗电量(W)"""
        # 根据规则计算总耗电量
        # ARRIVE: 0.4单位
        # OPEN: 0.1单位
        # CLOSE: 0.1单位
        return 0.4 * self.arrive_count + 0.1 * self.open_count + 0.1 * self.close_count
    
    def evaluate(self, input_file, output_file, real_time=None):
        """评估电梯模拟程序的性能"""
        # 解析输入和输出文件
        self.parse_input(input_file)
        self.parse_output(output_file)
        
        # 计算系统运行时间(Tmax)
        if real_time is None:
            real_time = self.final_timestamp  # 如果未提供实际运行时间，使用最后一条输出的时间戳
        
        system_time = max(real_time, self.final_timestamp)
        
        # 计算平均完成时间(WT)
        average_completion_time = self.calculate_average_completion_time()
        
        # 计算系统耗电量(W)
        power_consumption = self.calculate_power_consumption()
        
        # 返回评估结果
        return {
            "system_time": system_time,
            "average_completion_time": average_completion_time,
            "power_consumption": power_consumption,
            "arrive_count": self.arrive_count,
            "open_count": self.open_count,
            "close_count": self.close_count,
            "completed_passengers": len(self.passenger_completions),
            "total_passengers": len(self.passenger_requests)
        }

def main():
    if len(sys.argv) < 3:
        print("Usage: python score.py <input_file> <output_file> [real_time]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # 可选的实际运行时间参数
    real_time = None
    if len(sys.argv) > 3:
        try:
            real_time = float(sys.argv[3])
        except ValueError:
            print(f"Error: Invalid real_time value: {sys.argv[3]}")
            sys.exit(1)
    
    score = Score()
    result = score.evaluate(input_file, output_file, real_time)
    
    # 输出评估结果
    print("电梯模拟程序性能评估结果:")
    print(f"系统运行时间(Tmax): {result['system_time']:.2f}秒")
    print(f"平均完成时间(WT): {result['average_completion_time']:.2f}秒")
    print(f"系统耗电量(W): {result['power_consumption']:.2f}单位")
    print("\n详细统计:")
    print(f"ARRIVE操作次数: {result['arrive_count']}")
    print(f"OPEN操作次数: {result['open_count']}")
    print(f"CLOSE操作次数: {result['close_count']}")
    print(f"完成的乘客请求: {result['completed_passengers']}/{result['total_passengers']}")

if __name__ == "__main__":
    main()
