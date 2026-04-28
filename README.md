<div align="center">

# 🎵 灵岩谱曲台 (Lingyan Studio)

**一款面向敦煌音阶创作的 AI 四声部谱曲工具**<br>
支持主旋律绘制、AI 和声生成与浏览器内四声部回放。

[![React](https://img.shields.io/badge/React-18-blue.svg?style=flat&logo=react)](https://reactjs.org/)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF.svg?style=flat&logo=vite)](https://vitejs.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6.svg?style=flat&logo=typescript)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-3-38B2AC.svg?style=flat&logo=tailwind-css)](https://tailwindcss.com/)
[![Zustand](https://img.shields.io/badge/Zustand-5-brown.svg?style=flat)](https://github.com/pmndrs/zustand)

[**🌐 访问在线预览**](http://118.195.252.229)

</div>

---

## 📖 项目简介

本项目结合敦煌音阶语汇、可视化乐谱交互与 Museformer 推理后端，提供一个可直接上手的 AI 辅助谱曲界面。

用户可以在 16 步网格上绘制主旋律，系统会自动将旋律吸附到敦煌音阶（1-2-3-♯4-5-6）与节奏位置。点击“生成和声”后，前端会向 AI 后端发送旋律数据，获取多声部和声建议，并支持在浏览器中与主旋律一同回放。

## 🗺️ 版本路线图 (Roadmap)

当前版本已经完成从前端交互原型到 AI 后端接入的第一轮闭环：

- **v1.0.0（当前版本）**：**AI 和声生成 + 浏览器四声部回放**。
  - 前端已接入真实的 Museformer 推理接口。
  - 点击“播放”会同时回放主旋律和 AI 生成声部。
  - 四个声部使用不同的浏览器合成器音色，便于快速区分。
- **v1.1.0（下一步）**：**生成质量优化**。
  - 提升多声部覆盖率、减少重复音、优化声部密度与音域分配。
  - 改进前后端 token 编码与后处理策略。
- **v2.0.0（规划中）**：**作品导出与更强音频表现**。
  - 支持导出 MIDI 或音频文件。
  - 将浏览器内简单合成器升级为更细致的乐器采样或音色引擎。

## ✨ 核心特性

- **🎹 交互式乐谱网格**：直观的 16 步时值 x 多音高网格，支持自由点击、涂抹绘制与擦除音符。
- **🎨 四声部视觉区分**：
  - 🔵 **主旋律 (Soprano)**：用户输入，高亮蓝色
  - 🟠 **女低音 (Alto)**：AI 生成，暖橙色
  - 🟢 **男高音 (Tenor)**：AI 生成，翠绿色
  - 🔴 **男低音 (Bass)**：AI 生成，深红色
- **🤖 AI 和声生成**：前端将主旋律发送到 Museformer 推理后端，返回可直接上屏的和声音符。
- **🔊 四声部浏览器回放**：主旋律与 AI 生成声部可一起播放，并使用不同合成器音色区分声部。
- **✨ 丝滑的交互动画**：引入 `framer-motion`，音符的生成、消除均带有舒适的缩放与错落延迟动画（Staggered Animation）。
- **📱 响应式设计**：完美适配桌面端，移动端支持横向滑动，随时随地记录音乐灵感。
- **📜 异域文化 UI**：采用纸质暖黄色背景搭配深棕色网格线，融合古典敦煌元素与现代 UI 质感。

## 🛠️ 技术栈

本项目采用现代前端最佳实践构建，保证了极致的开发体验与运行性能：

- **前端框架**: React 18 + TypeScript
- **构建工具**: Vite 6
- **样式方案**: Tailwind CSS + `clsx` / `tailwind-merge`
- **动画引擎**: Framer Motion
- **音频回放**: Web Audio API
- **AI 推理后端**: FastAPI + Museformer

## 🚀 快速开始

### 1. 克隆项目
```bash
git clone https://github.com/RudyJiang-cmd/Lingyan-Studio.git
cd Lingyan-Studio
```

### 2. 安装依赖
推荐使用 `npm`：
```bash
npm install
```

### 3. 本地开发运行
```bash
npm run dev
```
打开浏览器访问 `http://localhost:5173` 即可预览。

### 4. 生产环境构建
```bash
npm run build
```
构建产物将输出在 `dist` 目录中。

## ☁️ 部署指南

前端静态资源可部署在任何静态页面托管服务上，例如 **Vercel**、**Netlify**，或者云服务器上的 **Nginx**。当前版本的 AI 和声功能还需要额外部署 FastAPI + Museformer 后端服务。

### Vercel 一键部署 (推荐)
1. 在项目根目录运行 `npx vercel`
2. 按照命令行提示完成部署即可。

### Nginx 手动部署
将 `npm run build` 生成的 `dist` 目录下的所有文件复制到服务器的 `/var/www/html` 目录下，并确保 Nginx 正确配置了静态文件服务。若需要启用 AI 和声，还需保证前端请求的后端地址可访问。

---

<div align="center">
  <i>如果这个项目对你的比赛或学习有帮助，欢迎给个 ⭐️ Star！</i>
</div>
