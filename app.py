import os
import subprocess
import time
import csv
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, send_file
from collections import defaultdict
from werkzeug.utils import secure_filename
import threading
import glob

app = Flask(__name__)
app.secret_key = 'elevator_judge_secret_key'

# 配置
UPLOAD_FOLDER = 'program'
LOG_FOLDER = 'log'
ALLOWED_EXTENSIONS = {'jar'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB 上传大小限制

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# 确保目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

import logging

# 配置日志
logging.basicConfig(level=logging.DEBUG,  # 设置日志级别为 DEBUG，会输出所有级别的日志
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app.logger.setLevel(logging.DEBUG) # 确保 Flask app 的 logger 也设置为 DEBUG

# 当前运行状态
running_status = {
    'is_running': False,
    'output': [],
    'start_time': None
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/jar_manager')
def jar_manager():
    page = request.args.get('page', 1, type=int)
    per_page = 10  # 每页显示的文件数量
    
    # 获取JAR文件列表
    jar_files = []
    for filename in os.listdir(UPLOAD_FOLDER):
        if filename.endswith('.jar'):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file_size = os.path.getsize(filepath)
            file_date = datetime.fromtimestamp(os.path.getmtime(filepath))
            jar_files.append({
                'name': filename,
                'size': file_size,
                'size_formatted': format_size(file_size),
                'date': file_date.strftime('%Y-%m-%d %H:%M:%S')
            })
    
    # 按上传时间倒序排序
    jar_files.sort(key=lambda x: x['date'], reverse=True)
    
    # 分页
    total_pages = (len(jar_files) + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    jar_files_paged = jar_files[start_idx:end_idx]
    
    return render_template(
        'jar_manager.html', 
        jar_files=jar_files_paged, 
        page=page, 
        total_pages=total_pages,
        is_running=running_status['is_running']
    )

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('没有选择文件', 'error')
        return redirect(url_for('jar_manager'))
    
    file = request.files['file']
    if file.filename == '':
        flash('没有选择文件', 'error')
        return redirect(url_for('jar_manager'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # 检查文件是否已存在
        if os.path.exists(file_path):
            flash(f'文件 {filename} 已存在', 'error')
            return redirect(url_for('jar_manager'))
        
        # 保存文件
        file.save(file_path)
        flash(f'文件 {filename} 上传成功', 'success')
        return redirect(url_for('jar_manager'))
    else:
        flash('不支持的文件类型，只允许上传JAR文件', 'error')
        return redirect(url_for('jar_manager'))

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        flash(f'文件 {filename} 已删除', 'success')
    else:
        flash(f'文件 {filename} 不存在', 'error')
    return redirect(url_for('jar_manager'))

@app.route('/run_program', methods=['GET', 'POST'])
def run_program():
    if request.method == 'POST':
        # 检查是否有程序正在运行
        if running_status['is_running']:
            flash('已有程序在运行，请等待完成', 'error')
            return redirect(url_for('run_program'))
        
        # 检查是否有JAR文件
        jar_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('.jar')]
        if not jar_files:
            flash('没有可用的JAR文件，请先上传', 'error')
            return redirect(url_for('jar_manager'))
        
        # 获取参数
        num_iterations = request.form.get('num_iterations', 1, type=int)
        num_requests = request.form.get('num_requests', 50, type=int)
        time_limit = request.form.get('time_limit', 10, type=int)
        duplicate_times = request.form.get('duplicate_times', 10, type=int)
        num_schedule = request.form.get('num_schedule', 10, type=int)
        
        # 验证参数
        if num_iterations < 1:
            flash('迭代次数必须大于0', 'error')
            return redirect(url_for('run_program'))
        
        # 启动线程运行程序
        threading.Thread(target=run_script, args=(num_iterations, num_requests, time_limit, duplicate_times, num_schedule)).start()
        
        flash('程序已开始运行，请等待结果', 'success')
        return redirect(url_for('run_program'))
    
    return render_template('run_program.html', 
                          is_running=running_status['is_running'],
                          output=running_status['output'],
                          start_time=running_status['start_time'])

@app.route('/run_custom_input', methods=['POST'])
def run_custom_input():
    if running_status['is_running']:
        flash('已有程序在运行，请等待完成', 'error')
        return redirect(url_for('run_program'))
    
    # Get custom input from form
    custom_input = request.form.get('custom_input', '')
    
    # 将所有换行符统一为\n
    custom_input = custom_input.replace('\r\n', '\n').replace('\r', '\n')
    
    # Save to stdin.txt
    with open('stdin.txt', 'w') as f:
        f.write(custom_input)
    
    # Start thread to run the script with custom input
    threading.Thread(target=run_custom_script).start()
    
    flash('程序已开始运行，请等待结果', 'success')
    return redirect(url_for('run_program'))

def run_custom_script():
    # Update running status
    running_status['is_running'] = True
    running_status['output'] = []
    running_status['start_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # Run with custom input (USER_INPUT=1)
        cmd = "./run.sh 1 0 0 0 0 1"
        
        # Run command and get output in real-time
        process = subprocess.Popen(
            cmd, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read output
        for line in process.stdout:
            line = line.strip()
            running_status['output'].append(line)
        
        # Wait for process to finish
        process.wait()
        
        if process.returncode != 0:
            running_status['output'].append(f"程序退出，返回代码：{process.returncode}")
    except Exception as e:
        running_status['output'].append(f"发生错误：{str(e)}")
    finally:
        running_status['is_running'] = False

def run_script(num_iterations, num_requests, time_limit, duplicate_times, num_schedule):
    # 更新运行状态
    running_status['is_running'] = True
    running_status['output'] = []
    running_status['start_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        # 构建命令
        cmd = f"./run.sh {num_iterations} {num_requests} {time_limit} {duplicate_times} {num_schedule}"
        
        # 运行命令并实时获取输出
        process = subprocess.Popen(
            cmd, 
            shell=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # 读取输出
        for line in process.stdout:
            line = line.strip()
            running_status['output'].append(line)
        
        # 等待进程结束
        process.wait()
        
        if process.returncode != 0:
            running_status['output'].append(f"程序退出，返回代码：{process.returncode}")
    except Exception as e:
        running_status['output'].append(f"发生错误：{str(e)}")
    finally:
        running_status['is_running'] = False

@app.route('/logs')
def logs():
    path = request.args.get('path', '')
    
    # 安全检查：确保路径在LOG_FOLDER内
    abs_base_path = os.path.abspath(LOG_FOLDER)
    abs_path = os.path.abspath(os.path.join(LOG_FOLDER, path))
    
    if not abs_path.startswith(abs_base_path):
        flash('非法路径访问', 'error')
        return redirect(url_for('logs'))
    
    # 相对路径（用于导航）
    rel_path = os.path.normpath(path)
    if rel_path == '.':
        rel_path = ''
    
    # 面包屑导航
    breadcrumbs = []
    if rel_path:
        parts = rel_path.split(os.sep)
        for i, part in enumerate(parts):
            path_so_far = os.sep.join(parts[:i+1])
            breadcrumbs.append({'name': part, 'path': path_so_far})
    
    # 获取当前目录内容
    current_path = os.path.join(LOG_FOLDER, rel_path)
    items = []
    
    if os.path.isdir(current_path):
        # 处理目录
        for item in sorted(os.listdir(current_path)):
            item_path = os.path.join(current_path, item)
            item_rel_path = os.path.join(rel_path, item) if rel_path else item
            
            is_dir = os.path.isdir(item_path)
            size = os.path.getsize(item_path) if not is_dir else 0
            mod_time = datetime.fromtimestamp(os.path.getmtime(item_path))
            
            items.append({
                'name': item,
                'path': item_rel_path,
                'is_dir': is_dir,
                'size': format_size(size),
                'modified': mod_time.strftime('%Y-%m-%d %H:%M:%S')
            })
    else:
        # 处理文件
        flash('请求的路径不是目录', 'error')
        return redirect(url_for('logs'))
    
    return render_template('logs.html',
                           os=os,
                          items=items, 
                          current_path=rel_path,
                          breadcrumbs=breadcrumbs)

@app.route('/download_log')
def download_log():
    path = request.args.get('path', '')
    
    # 安全检查
    abs_base_path = os.path.abspath(LOG_FOLDER)
    abs_path = os.path.abspath(os.path.join(LOG_FOLDER, path))
    
    if not abs_path.startswith(abs_base_path):
        flash('非法路径访问', 'error')
        return redirect(url_for('logs'))
    
    if not os.path.isfile(abs_path):
        flash('文件不存在', 'error')
        return redirect(url_for('logs'))
    
    # 检查文件扩展名
    allowed_extensions = ('txt', 'log', 'csv')
    if not path.endswith(allowed_extensions):
        flash('不允许下载此类型的文件', 'error')
        return redirect(url_for('logs', path=os.path.dirname(path)))
    
    # 发送文件
    return send_file(abs_path, as_attachment=True)

@app.route('/running_status')
def get_running_status():
    return jsonify({
        'is_running': running_status['is_running'],
        'output': running_status['output'],
        'start_time': running_status['start_time']
    })

def format_size(size):
    # 格式化文件大小显示
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

@app.route('/chart')
def chart():
    """渲染性能分析图表页面"""
    return render_template('chart.html')

@app.route('/chart_data')
def chart_data():
    """提供图表数据的API"""
    result_file = os.path.join(LOG_FOLDER, 'results.csv')
    
    # result_file = os.path.abspath(os.path.join(LOG_FOLDER, 'results.csv'))
    app.logger.debug(f"result_file: {result_file}")
    # 检查文件是否存在
    if not os.path.exists(result_file):
        return jsonify({'error': 'No data available'})
    
    try:
        # 读取CSV文件
        with open(result_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        # 如果文件为空或只有标题行
        if len(rows) <= 1:
            return jsonify({'error': 'No data available'})
        
        # 解析数据
        # 第一行是标题: 测试案例,系统运行时间(Tmax),平均完成时间(WT),系统耗电量(W),ARRIVE操作次数,OPEN操作次数,CLOSE操作次数,完成乘客数
        headers = rows[0]
        data = rows[1:]  # 跳过标题行
        
        # 按测试时间分组
        time_pattern = r'-(\d{2}-\d{2}-\d{2}-\d{2}-\d{2})$'
        test_runs = defaultdict(list)
        
        for row in data:
            if not row[0]:  # 忽略空测试案例
                continue
                
            # 提取测试对象和测试时间
            test_case = row[0]
            time_match = re.search(time_pattern, test_case)
            
            if time_match:
                test_time = time_match.group(1)  # 提取时间部分
                test_object = test_case.replace('-' + test_time, '')  # 提取测试对象部分
                
                # 将数据添加到对应的测试时间组
                test_runs[test_time].append({
                    'test_object': test_object,
                    'tmax': float(row[1]) if row[1] else 0,
                    'wt': float(row[2]) if row[2] else 0,
                    'w': float(row[3]) if row[3] else 0,
                    'arrive': int(row[4]) if row[4] else 0,
                    'open': int(row[5]) if row[5] else 0,
                    'close': int(row[6]) if row[6] else 0,
                    'completed_passengers': row[7] if row[7] else '0/0'
                })
        
        # 按时间倒序排序并取最近15次运行
        sorted_times = sorted(test_runs.keys(), reverse=False)
        if len(sorted_times) < 15:
            recent_times = sorted_times
        else:
            recent_times = sorted_times[-15:]
        
        # 准备返回数据
        result = {
            'runs': [],  # 测试运行时间
            'testObjects': [],  # 测试对象名称
            'tmax': [],  # 系统运行时间数据
            'wt': [],  # 平均完成时间数据
            'w': [],  # 系统耗电量数据
            'completedPassengers': []  # 完成乘客数据
        }
        
        # 获取所有测试对象
        all_test_objects = set()
        for time in recent_times:
            for run in test_runs[time]:
                all_test_objects.add(run['test_object'])
        
        # 将测试对象转换为列表并排序
        test_objects_list = sorted(list(all_test_objects))
        result['testObjects'] = test_objects_list
        
        # 为每个测试对象初始化数据数组
        for _ in test_objects_list:
            result['tmax'].append([])
            result['wt'].append([])
            result['w'].append([])
            result['completedPassengers'].append([])
        
        # 填充数据
        for time in recent_times:
            result['runs'].append(time)  # 添加测试时间
            
            # 为每个测试对象查找对应的数据
            for obj_idx, test_object in enumerate(test_objects_list):
                found = False
                
                for run in test_runs[time]:
                    if run['test_object'] == test_object:
                        result['tmax'][obj_idx].append(run['tmax'])
                        result['wt'][obj_idx].append(run['wt'])
                        result['w'][obj_idx].append(run['w'])
                        result['completedPassengers'][obj_idx].append(run['completed_passengers'])
                        found = True
                        break
                
                # 如果没有找到该测试对象的数据，填充null
                if not found:
                    result['tmax'][obj_idx].append(None)
                    result['wt'][obj_idx].append(None)
                    result['w'][obj_idx].append(None)
                    result['completedPassengers'][obj_idx].append('0/0')
        
        return jsonify(result)
    
    except Exception as e:
        print(f"Error processing chart data: {str(e)}")
        return jsonify({'error': f'Error processing data: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8082)
