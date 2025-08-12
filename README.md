# 园区招商项目研判 · Streamlit 在线版

> 填表 → 计算评分与结论 → 一键导出 Word/PDF 报告。

## 本地运行
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 快速上线（两种任选其一）

### 方案A：Streamlit Community Cloud（免服务器）
1. 新建 GitHub 仓库，把本目录所有文件提交上去。
2. 登录 https://streamlit.io/cloud → 新建 App → 选择你的仓库/分支，App file 选 `app.py` → Deploy。
3. 打开的链接就是你的在线地址。

> 如需简单访问控制，可在 `app.py` 顶部加入以下“访问码”段落（仅示例，非强安全）：
```python
import streamlit as st
ACCESS_CODE = st.secrets.get("ACCESS_CODE", "")
code = st.sidebar.text_input("访问码", type="password")
if ACCESS_CODE and code != ACCESS_CODE:
    st.stop()
```
并在 Streamlit Cloud 的 **Secrets** 里设置：
```
ACCESS_CODE = "your_code_here"
```

### 方案B：Hugging Face Spaces（也很快）
1. 登录 https://huggingface.co/spaces → Create new Space → 选择 **Streamlit**。
2. 上传本目录所有文件（或直接连接你的 GitHub 仓库）。
3. 等待自动构建完成，空间地址即为你的在线地址。

## 可选：Docker 部署（你自己的云主机）
新建 `Dockerfile`：
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py .
EXPOSE 8501
CMD ["streamlit","run","app.py","--server.address=0.0.0.0","--server.port=8501"]
```
构建&运行：
```bash
docker build -t park-eval .
docker run -d --name park-eval -p 8501:8501 park-eval
```

## 注意事项
- 本应用不会自动保存你输入的数据；如需留痕/审计，请接入数据库或导出后自行归档。
- 评分规则与阈值在左侧边栏可快速调整；文本话术可在 `app.py` 中修改。
