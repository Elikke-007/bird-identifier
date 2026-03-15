# Python Bird Recognition Backend

这是提供给桌面端调用的本地 Ollama 鸟类识别服务：

1. 使用 `llava:7b` 对整张图片进行视觉识别
2. 返回英文鸟种候选列表
3. 使用 `deepseek-r1:14b` 把识别结果翻译成中文

## 接口

- `GET /health`
- `POST /identify`

请求体：

```json
{
  "imagePath": "C:/path/to/image.jpg",
  "topK": 5
}
```

## 安装

建议使用 Python 3.11 或 3.12。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 启动

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload
```

## Ollama 依赖

需要本机已经启动 Ollama，并且已拉取：

- `llava:7b`
- `deepseek-r1:14b`

默认地址：

```text
http://localhost:11434
```

如果你的 Ollama 地址不同，可以设置环境变量：

```powershell
$env:OLLAMA_BASE_URL="http://localhost:11434"
```

## 说明

- 当前识别接口直接使用多模态模型做整图识别，不再依赖 YOLO 或 Hugging Face 分类模型
- 性别暂未接入专用模型，接口默认返回 `未知`
- 中文名翻译优先走 `deepseek-r1:14b`，模型未返回时会回退到本地词典

