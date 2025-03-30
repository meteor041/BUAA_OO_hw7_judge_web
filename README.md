# 电梯模拟评判系统 (Elevator Simulation Judge)

## 项目概述

该项目实现了一个电梯模拟评判系统，主要包含以下功能：

- **请求生成（gen.py）**：
  - 用于生成包含随机时间、乘客编号、优先级、起始楼层、目标楼层以及电梯编号的请求数据，生成的请求满足严格的格式要求，供电梯模拟系统使用。

- **输出验证（judge.py）**：
  - 读取由电梯模拟程序输出的事件数据，使用正则表达式和逻辑判断对事件格式、时间戳、楼层移动、电梯门操作、乘客上/下电梯等规则进行校验，确保模拟过程符合预期。

- **性能评分（score.py）**：
  - 解析输入请求和模拟输出，计算最终完成时间（Trun）、平均等待时间（WT）以及加权事件数（W），用于对电梯调度模拟进行性能评估。

- **Web界面**：
  - 提供一个简约美观的Web界面，用于JAR包管理、运行评测以及查看日志，方便用户使用。

## 文件说明

- **gen.py**：
  - 通过命令行参数（如 --num_requests, --time_limit, --seed）生成随机的电梯请求，每条请求格式为
    `[timestamp]passenger_id-PRI-priority-FROM-from_floor-TO-to_floor-BY-elevator_id`。

- **judge.py**：
  - 校验电梯模拟输出文件的合法性，主要验证内容包括：
    - 输入请求和输出事件的格式是否符合规定；
    - 输出事件的时间戳是否单调递增；
    - 电梯运动是否合法（每次仅移动一层，时间间隔足够）；
    - 电梯门的开/关顺序及操作时间；
    - 乘客的进出、电梯容量以及最终状态等。

- **score.py**：
  - 基于请求和事件数据计算性能指标：
    - **Trun**：输出事件中最大时间戳，代表模拟结束时刻；
    - **WT**：乘客从请求到抵达的平均等待时间；
    - **W**：基于不同类型事件计数的加权总和（例如，ARRIVE 权重 0.4，OPEN 和 CLOSE 各 0.1）。
    
- **app.py**：
  - Web应用主文件，基于Flask实现，提供JAR包管理、运行评测以及日志查看等功能。

- **run.sh**：
  - 用于运行JAR包的脚本，会调用gen.py生成输入，然后运行JAR包，并使用judge.py和score.py对结果进行评判。

## 使用方法

### 方法一：命令行使用

#### 1. 生成请求文件

运行 gen.py 来生成请求数据。例如：

```bash
python gen.py --num_requests 50 --time_limit 50 --seed 42 > input.txt
```

这会生成 50 条电梯请求，并将结果保存到 input.txt 文件中。

#### 2. 运行电梯模拟

基于生成的 input.txt，您需要运行电梯调度模拟程序（本项目不提供具体的调度算法实现），生成输出事件文件 output.txt。

#### 3. 校验输出文件

使用 judge.py 对 output.txt 进行校验，以确保模拟结果符合所有规定：

```bash
python judge.py --input_file input.txt --output_file output.txt
```

如果所有验证都通过，程序将输出 "Accepted"；否则，会显示对应的错误信息。

#### 4. 计算性能评分

运行 score.py 来计算性能指标：

```bash
python score.py
```

默认情况下，score.py 会读取 input.txt 和 output.txt 文件，并输出 Trun（模拟总运行时长）、WT（平均等待时间）以及 W（加权事件数）的计算结果。

### 方法二：Web界面使用

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 运行Web应用

```bash
python app.py
```

服务器启动后，访问 http://localhost:8080 即可打开Web界面。

#### 3. 使用流程

1. 在【JAR管理】页面上传您的电梯程序JAR包
2. 在【运行评测】页面配置参数（迭代次数、请求数量、时间限制）并运行程序
3. 在【日志查看】页面查看和分析运行结果

## 环境依赖

- Python 3.x
- Flask 2.0.1及相关依赖（见requirements.txt）
- Java运行环境（用于执行JAR包）

## 注意事项

- 请求文件中的楼层名称必须为：B4, B3, B2, B1, F1, F2, F3, F4, F5, F6, F7。
- 每部电梯的编号范围为 1 至 6。
- 输出事件的时间戳需为浮点数格式且单调递增，确保模拟过程的连续性。
- Web界面仅在支持JavaScript的现代浏览器中正常工作。
- 项目中的run.sh脚本需要执行权限：`chmod +x run.sh`

## 项目结构

```
.
├── app.py               # Flask应用主文件
├── gen.py               # 请求生成模块
├── judge.py             # 输出验证模块
├── score.py             # 性能评分模块
├── run.sh               # 运行JAR包的脚本
├── requirements.txt     # Python依赖列表
├── README.md            # 项目说明文件
├── static/              # 静态资源目录
│   ├── css/             # CSS样式文件
│   └── js/              # JavaScript脚本文件
├── templates/           # HTML模板目录
├── program/             # JAR包上传目录
├── log/                 # 日志存储目录
└── judge/               # 评测相关文件存放目录
```
