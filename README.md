# 鸟类识别工具

基于 Tauri + React + TypeScript 的桌面端，配合 Python FastAPI + Ollama 本地模型后端使用。

## 当前架构

- 桌面端：目录扫描、图片列表、识别结果卡片、人工修正、元数据写入、Markdown 导出
- Python 后端：调用本机 Ollama 视觉模型识别鸟种，并调用本机翻译模型生成中文结果

## 当前识别流程

1. 使用本机 Ollama `llava:7b` 对图片进行鸟类识别
2. 返回英文鸟种候选列表和识别理由
3. 使用本机 Ollama `deepseek-r1:14b` 把结果翻译成中文

当前后端会返回：

- 中文鸟种名
- 英文原名
- 物种置信度
- 候选鸟种列表

性别暂时默认返回 `未知`，前端仍支持手动编辑后写入。

## 目录

- [src](/C:/1-study/identify-tool/src)：Tauri/React 前端
- [src-tauri](/C:/1-study/identify-tool/src-tauri)：桌面壳与元数据写入
- [backend](/C:/1-study/identify-tool/backend)：Python FastAPI 识别后端

## 启动顺序

### 1. 启动 Python 识别后端

先安装 Python 3.11+，然后：

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8008 --reload
```

如果你已经准备好了 `backend\.venv`，也可以在项目根目录一键启动：

```powershell
.\start-backend.ps1 -Reload
```

默认地址是 `http://127.0.0.1:8008`，也可以指定端口：

```powershell
.\start-backend.ps1 -BindHost 127.0.0.1 -Port 8010 -Reload
```

### 2. 准备 Ollama 本地模型

你本机需要已经启动 Ollama，并拉取：

```text
llava:7b
deepseek-r1:14b
```

默认调用：

```text
http://localhost:11434
```

如需修改 Ollama 地址，可设置环境变量：

```powershell
$env:OLLAMA_BASE_URL="http://localhost:11434"
```

### 3. 启动桌面端

```bash
pnpm install
pnpm run tauri dev
```

## 识别接口默认地址

前端默认调用：

```text
http://127.0.0.1:8008
```

如果你要改地址，可以设置环境变量：

```text
VITE_RECOGNITION_API_URL
```

## 关键文件

- [src/App.tsx](/C:/1-study/identify-tool/src/App.tsx)
- [src/lib/recognitionApi.ts](/C:/1-study/identify-tool/src/lib/recognitionApi.ts)
- [src-tauri/src/metadata.rs](/C:/1-study/identify-tool/src-tauri/src/metadata.rs)
- [backend/app/main.py](/C:/1-study/identify-tool/backend/app/main.py)
- [backend/app/service.py](/C:/1-study/identify-tool/backend/app/service.py)
- [backend/app/species_glossary.py](/C:/1-study/identify-tool/backend/app/species_glossary.py)
- [start-backend.ps1](/C:/1-study/identify-tool/start-backend.ps1)

## 已验证

当前环境已验证前端构建通过：

```bash
pnpm build
cargo check
```

后端代码这次未在当前环境里实际连通你的本机 Ollama 服务验证，但接口调用逻辑已经切换到 `http://localhost:11434`。
