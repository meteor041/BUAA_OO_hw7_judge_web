#!/bin/bash
#set -e

# 参数验证
if [[ -z "$1" ]]; then
  echo "Usage: $0 <num_iterations> [<num_requests> <time_limit>]"
  exit 1
fi
timestamp=$(date "+%m-%d-%H-%M-%S")
NUM_ITERATIONS=$1
NUM_REQUESTS=${2:-50}  # 默认值
TIME_LIMIT=${3:-10}    # 默认值
USER_INPUT=${4:0}
DUPLICATE_TIMES=$((RANDOM % 7 + 1))
MAX_CONCURRENT=16      #  服务器内存有限，降低并发数量
PROGRAM_DIR="program"  #  jar 包所在的目录

# 检查程序目录是否存在
if [ ! -d "$PROGRAM_DIR" ]; then
  echo "Error: Program directory '$PROGRAM_DIR' not found."
  exit 1
fi

# 用于存储所有 result.txt 文件的数组
declare -a result_files

for i in $(seq 1 $NUM_ITERATIONS); do
    echo "  Running iteration $i"

    
	if [[ $USER_INPUT -eq 0 ]]; then
		# 生成输入文件，并将其保存到变量
    		if [[ $# -eq 1 ]]; then
      			input_content=$(python3 judge/gen.py)
    		else
      			input_content=$(python3 judge/gen.py --num_request=$NUM_REQUESTS --time_limit=$TIME_LIMIT --duplicate_times=$DUPLICATE_TIMES)
    		fi
    		echo "$input_content" > stdin.txt
	else
		input_content=`cat stdin.txt`
	fi
	
 
    # 遍历 jar 文件
    for jar_file in "$PROGRAM_DIR"/*.jar; do
        if [ ! -f "$jar_file" ]; then
           continue  # 如果不是文件就跳过
        fi
         jar_filename=$(basename "$jar_file")
        echo "Processing jar file: $jar_filename"
        jar_filename_noext="${jar_filename%.*}"  # 去掉 .jar 后缀


        log_dir="log/$jar_filename_noext/$timestamp"
        mkdir -p "$log_dir"
        touch "$log_dir/result.txt"

        current_concurrent=0
        result=true

        #将input 写入到文件
        echo "$input_content" > $log_dir/input$i.txt
        # 执行 Java 程序  (后台运行) &
        # -Xms 和 -Xmx 控制堆内存
        # -XX:MetaspaceSize 和 -XX:MaxMetaspaceSize 控制元空间 (Metaspace) 大小
        # timeout 用于限制总的运行时间
        #使用./datainput_student_linux_x86_64 作为输入
	(
   	    cmd=(
  timeout 60s bash -c '
    ./datainput_student_linux_x86_64 |
    java -Xms512m -Xmx768m -XX:MetaspaceSize=64m -XX:MaxMetaspaceSize=128m -jar "$1" \
    > "$2/output$3.txt" 2>> "$2/result.txt"
  ' _ "$jar_file" "$log_dir" "$i"
)
"${cmd[@]}" &
java_pid=$!
            
            # 等待 Java 进程完成或超时
            if wait $java_pid; then
                echo "$log_dir: Java程序正常完成(迭代 $i)"
            else
                exit_code=$?
                if [ $exit_code -eq 124 ]; then
                    echo "$log_dir: Warning: Java程序超时被终止 (迭代 $i)"
                else
                    echo "$log_dir:Error:  Java程序异常退出，代码 $exit_code (迭代 $i)"
                fi
		result=false
            fi
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
        python3 judge/judge.py --input_file="$log_dir/input$i.txt" --output_file="$log_dir/output$i.txt" | tee -a "$log_dir/result.txt" "log/$jar_filename_noext/allResult.txt"
        return_code=$?
        if [ $return_code -ne 0 ]; then
          echo "  Error: Python judge script failed with return code: $return_code"
          result=false
        fi

        python3 judge/score.py --input_file="$log_dir/input$i.txt" --output_file="$log_dir/output$i.txt" >> "$log_dir/result.txt"
        echo "  ----------------------------------------" >> "$log_dir/result.txt"
        echo "$log_dir : $result"
	) &
	 # 将 result.txt 文件添加到数组
	if [[ $i -eq 1 ]]; then
        	result_files+=("$log_dir/result.txt")
	fi
    done

    wait # 等待所有后台进程完成

    echo "Finished processing"

done

echo "All jar files processed."

# 使用 compare.py 比较所有 result.txt 文件
if [[ ${#result_files[@]} -gt 0 ]]; then
  echo "Comparing result files..."
  python3 judge/compare.py "${result_files[@]}"
else
  echo "No result files found for comparison."
fi

exit 0 
