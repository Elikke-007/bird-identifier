# Python Bird Recognition Backend

这是提供给桌面端调用的两阶段鸟类识别服务：

1. 使用 `YOLO11x` 检测图片里鸟的位置
2. 对主目标裁剪图使用 `chriamue/bird-species-classifier` 做物种分类
3. 使用词典映射 + 英译中模型把鸟种结果转换为中文

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

## 模型

- 检测模型：`yolo11x.pt`
- 分类模型：`chriamue/bird-species-classifier`
- 翻译模型：`Helsinki-NLP/opus-mt-en-zh`

## 说明

- 首次启动会下载模型文件，耗时会比较长
- 当前默认只对面积最大的鸟目标做分类
- 性别暂未接入专用模型，接口默认返回 `未知`
- 鸟种中文名采用“词典优先、翻译模型兜底”的策略
