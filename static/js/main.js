document.addEventListener('DOMContentLoaded', function() {
    // 闪烁消息自动关闭
    setTimeout(function() {
        let alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            if (alert.querySelector('.close')) {
                alert.style.opacity = '0';
                setTimeout(function() {
                    alert.style.display = 'none';
                }, 500);
            }
        });
    }, 5000);

    // 关闭按钮
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('close') || e.target.parentElement.classList.contains('close')) {
            const alert = e.target.closest('.alert');
            if (alert) {
                alert.style.opacity = '0';
                setTimeout(function() {
                    alert.style.display = 'none';
                }, 500);
            }
        }
    });

    // 上传区域交互
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    
    if (uploadArea && fileInput) {
        uploadArea.addEventListener('click', function() {
            fileInput.click();
        });
        
        uploadArea.addEventListener('dragover', function(e) {
            e.preventDefault();
            uploadArea.classList.add('border-primary');
        });
        
        uploadArea.addEventListener('dragleave', function() {
            uploadArea.classList.remove('border-primary');
        });
        
        uploadArea.addEventListener('drop', function(e) {
            e.preventDefault();
            uploadArea.classList.remove('border-primary');
            
            if (e.dataTransfer.files.length) {
                fileInput.files = e.dataTransfer.files;
                document.getElementById('upload-form').submit();
            }
        });
        
        fileInput.addEventListener('change', function() {
            if (fileInput.files.length) {
                document.getElementById('upload-form').submit();
            }
        });
    }

    // 删除文件确认
    const deleteButtons = document.querySelectorAll('.delete-btn');
    deleteButtons.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            if (!confirm('确定要删除这个文件吗？此操作不可恢复。')) {
                e.preventDefault();
            }
        });
    });

    // 运行状态轮询
    const terminalOutput = document.getElementById('terminal-output');
    const runButton = document.getElementById('run-button');
    
    function updateRunningStatus() {
        if (terminalOutput) {
            fetch('/running_status')
                .then(response => response.json())
                .then(data => {
                    if (data.is_running) {
                        // 更新终端输出
                        let outputHtml = '';
                        data.output.forEach(line => {
                            outputHtml += line + '\n';
                        });
                        terminalOutput.textContent = outputHtml;
                        terminalOutput.scrollTop = terminalOutput.scrollHeight;
                        
                        // 禁用运行按钮
                        if (runButton) {
                            runButton.disabled = true;
                            runButton.textContent = '运行中...';
                        }
                        
                        // 继续轮询
                        setTimeout(updateRunningStatus, 1000);
                    } else {
                        // 如果有输出但不是运行中，则可能刚刚结束
                        if (data.output && data.output.length > 0) {
                            let outputHtml = '';
                            data.output.forEach(line => {
                                outputHtml += line + '\n';
                            });
                            terminalOutput.textContent = outputHtml;
                            terminalOutput.scrollTop = terminalOutput.scrollHeight;
                        }
                        
                        // 启用运行按钮
                        if (runButton) {
                            runButton.disabled = false;
                            runButton.textContent = '运行';
                        }
                    }
                })
                .catch(error => {
                    console.error('获取运行状态时出错:', error);
                    // 出错时也要启用按钮
                    if (runButton) {
                        runButton.disabled = false;
                        runButton.textContent = '运行';
                    }
                });
        }
    }
    
    // 如果存在终端输出元素，开始轮询
    if (terminalOutput) {
        updateRunningStatus();
    }

    // 运行参数验证
    const runForm = document.getElementById('run-form');
    if (runForm) {
        runForm.addEventListener('submit', function(e) {
            const numIterations = document.getElementById('num_iterations').value;
            const numRequests = document.getElementById('num_requests').value;
            const timeLimit = document.getElementById('time_limit').value;
            
            if (numIterations < 1) {
                e.preventDefault();
                alert('迭代次数必须大于0');
            }
            
            if (numRequests < 1) {
                e.preventDefault();
                alert('请求数量必须大于0');
            }
            
            if (timeLimit < 1) {
                e.preventDefault();
                alert('时间限制必须大于0');
            }
        });
    }
}); 