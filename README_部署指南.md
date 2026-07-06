# 早盘助手 — GitHub Actions 部署指南

## 准备清单（你现在要做的）

- [ ] 注册 GitHub 账号：https://github.com（用 QQ 邮箱即可）
- [ ] 确认今天 15:00 收盘后，网页 https://au7f2dhyaiv4.meoo.zone 数据正常

---

## 第 1 步：注册 GitHub

1. 打开 https://github.com
2. 点击右上角 **Sign up**
3. 输入邮箱（QQ邮箱即可）、密码、用户名（英文，比如 `nana-zaopan`）
4. 验证邮箱，完成注册

---

## 第 2 步：创建仓库

1. 登录 GitHub 后，点击右上角 **+** → **New repository**
2. Repository name 填：`zaopan-helper`
3. 选 **Public**（公开）
4. 勾选 **Add a README file**
5. 点击 **Create repository**

---

## 第 3 步：上传代码

### 方法A（最简单，直接在网页上传）：

1. 进入你刚建的仓库
2. 点击 **Add file** → **Upload files**
3. 把下面这 3 个文件/文件夹拖进去：
   - `早盘抓取.py`
   - `.github/`（整个文件夹，里面有 `workflows/main.yml`）
4. 在底部 "Commit changes" 那里，随便写一句描述，比如"首次上传"
5. 点击 **Commit changes**

### 方法B（使用 Git Bash）：

```bash
cd d:\7.5复盘助手\github-deploy
git init
git add .
git commit -m "早盘助手首次提交"
git branch -M main
git remote add origin https://github.com/你的用户名/zaopan-helper.git
git push -u origin main
```

---

## 第 4 步：开启 Actions

1. 进入仓库，点顶部 **Actions** 标签
2. 如果提示 "Workflows aren't being run"，点击 **I understand...** 确认
3. 左侧找到 **早盘助手** workflow，检查状态

---

## 第 5 步：手动测试

1. 进入 Actions → 早盘助手
2. 点击右侧 **Run workflow** → **Run workflow**
3. 等 1-2 分钟，看运行结果是否绿色 ✅

---

## 完成！

以后每天 9:25、11:30、15:00（北京时间），GitHub 的云服务器会自动运行脚本，抓取数据写入 Supabase。

你的电脑关机也没关系。

---

## 文件说明

| 文件 | 作用 |
|------|------|
| `早盘抓取.py` | 云端版抓取脚本（不写 Excel，只写 Supabase） |
| `.github/workflows/main.yml` | GitHub Actions 配置（定时触发 + 环境安装） |
| `requirements.txt` | 依赖列表（目前只需要 `requests`） |
