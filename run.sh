#!/bin/bash
set -e

# 参数验证
if [[ -z "$1" ]]; then
  echo "Usage: $0 <num_iterations> [<num_requests> <time_limit>]"
  exit 1
fi

NUM_ITERATIONS=$1
NUM_REQUESTS=${2:-50}  # 默认值
TIME_LIMIT=${3:-10}    # 默认值
MAX_CONCURRENT=16      #  服务器内存有限，降低并发数量
PROGRAM_DIR="program"  #  jar 包所在的目录

# 检查程序目录是否存在
if [ ! -d "$PROGRAM_DIR" ]; then
  echo "Error: Program directory '$PROGRAM_DIR' not found."
  exit 1
fi

for i in $(seq 1 $NUM_ITERATIONS); do
    echo "  Running iteration $i"

 	
    # 生成输入文件
    if [[ $# -eq 1 ]]; then
      python3 judge/gen.py > stdin.txt
    else
      python3 judge/gen.py --num_request=$NUM_REQUESTS --time_limit=$TIME_LIMIT >  stdin.txt
    fi

 
# 遍历 jar 文件
for jar_file in "$PROGRAM_DIR"/*.jar; do
  if [ ! -f "$jar_file" ]; then
 	   continue  # 如果不是文件就跳过
  fi
	 jar_filename=$(basename "$jar_file")
echo "Processing jar file: $jar_filename"
  jar_filename_noext="${jar_filename%.*}"  # 去掉 .jar 后缀
	
  timestamp=$(date "+%m-%d-%H-%M-%S")
  log_dir="log/$jar_filename_noext/$timestamp"
#  log_dir=$(readlink -f "log_dir")
  mkdir -p "$log_dir"
  touch "$log_dir/result.txt"

  current_concurrent=0
  result=true

  
    cat stdin.txt > $log_dir/input$i.txt 
    # 执行 Java 程序  (后台运行) &
    # -Xms 和 -Xmx 控制堆内存
    # -XX:MetaspaceSize 和 -XX:MaxMetaspaceSize 控制元空间 (Metaspace) 大小
    # timeout 用于限制总的运行时间
    #使用./datainput_student_linux_x86_64 作为输入
    timeout 100s ./datainput_student_linux_x86_64 | java -Xms512m -Xmx768m -XX:MetaspaceSize=64m -XX:MaxMetaspaceSize=128m  -jar "$jar_file" > "$log_dir/output$i.txt" 2>> "$log_dir/result.txt" &

    # 控制并发进程数
    current_concurrent=$((current_concurrent + 1))
    if [[ $current_concurrent -ge $MAX_CONCURRENT ]]; then
      wait  # 等待所有后台进程完成
      current_concurrent=0
    fi
	PID=$!  # 获取上一个后台命令的进程 ID
	wait $PID  # 等待 PID 对应的进程结束
	echo -n "iteration $i : " >> "$log_dir/result.txt"
    # 分析结果和计算得分
    python3 judge/judge.py --input_file="$log_dir/input$i.txt" --output_file="$log_dir/output$i.txt" >> "$log_dir/result.txt"
    return_code=$?
    if [ $return_code -ne 0 ]; then
      echo "  Error: Python judge script failed with return code: $return_code"
      result=false
    fi

    python3 judge/score.py --input_file="$log_dir/input$i.txt" --output_file="$log_dir/output$i.txt" >> "$log_dir/result.txt"
    echo "  ----------------------------------------" >> "$log_dir/result.txt"

  done

  wait # 等待所有后台进程完成

  echo "$log_dir : $result"
  echo "Finished processing $jar_filename"

done

echo "All jar files processed."
exit 0 