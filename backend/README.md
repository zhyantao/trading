# 量化交易系统
Python + Flask 后端

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行

```bash
cd backend
python app.py
```

## API 端点

- `GET /api/health` - 健康检查
- `GET /api/params` - 获取参数
- `POST /api/params` - 设置参数
- `POST /api/analyze` - 分析股票
- `GET /api/trades` - 获取交易记录
- `POST /api/trades` - 添加交易记录
- `GET /api/symbols` - 获取股票列表
