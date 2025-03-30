
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(docs_url=None, redoc_url=None)  # 禁用文档接口

# 简单的维护页面HTML
MAINTENANCE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>服务器维护中</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f5f5f5;
            color: #333;
            text-align: center;
            padding: 50px;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #e74c3c;
        }
        .icon {
            font-size: 50px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon"></div>
        <h1>服务器维护中</h1>
        <p>我们正在对服务器进行维护，以提供更好的服务。</p>
        <p>请稍后再访问，感谢您的理解与支持。</p>
        <p><small>预计恢复时间: [2025-3-30 19:00:00]</small></p>
    </div>
</body>
</html>
"""

# 拦截所有请求返回维护页面
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def maintenance_page():
    return HTMLResponse(content=MAINTENANCE_HTML, status_code=503)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
