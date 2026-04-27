<div align="center">

# 🎵 灵岩谱曲台 (Lingyan Composing Platform)

**一款充满异域色彩的智能音乐创作工具**<br>
为您提供一个优雅的、可视化的四声部和声创作体验。

[![React](https://img.shields.io/badge/React-18-blue.svg?style=flat&logo=react)](https://reactjs.org/)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF.svg?style=flat&logo=vite)](https://vitejs.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6.svg?style=flat&logo=typescript)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-3-38B2AC.svg?style=flat&logo=tailwind-css)](https://tailwindcss.com/)
[![Zustand](https://img.shields.io/badge/Zustand-5-brown.svg?style=flat)](https://github.com/pmndrs/zustand)

[**🌐 访问在线预览**](http://118.195.252.229)

</div>

---

## 📖 项目简介

本项目专为**“互联网+”等创新创业比赛**打造，旨在结合敦煌文化与现代 AI 技术，构建一个充满异域风情、高度交互的智能音乐生成界面。

在这里，用户只需在如丝绸般铺开的网格上自由点触、绘制主旋律（女高音声部）。点击“生成和声”后，系统将通过底层的 AI 音乐大模型智能分析旋律走向，自动为你织就其他三个声部（女低音、男高音、男低音）的绝美和声，并配合丝滑的视觉动画完美呈现。

## 🗺️ 版本路线图 (Roadmap)

本项目采用敏捷开发模式，将逐步完成从前端交互到 AI 核心接入的演进：

- **v0.1.0-alpha（当前版本）**：**前端交互壳子与视觉展示**。
  - 完成了乐谱网格、动画引擎、音轨交互逻辑的搭建。
  - *注：为了方便界面测试与演示交互闭环，当前点击“生成和声”所展示的多声部音符为前端模拟数据，作为占位与流程跑通使用。*
- **v1.0.0-beta（研发中）**：**AI 音乐大模型接入**。
  - 剥离前端模拟数据，全面接入真实的 AI 音乐推理大模型 API。
  - 实现基于用户输入主旋律的实时、智能多声部作曲能力。
- **v2.0.0（规划中）**：**音频引擎接入与作品导出**。
  - 接入 Web Audio API 或 Tone.js，为四个声部提供真实的乐器采样回放。
  - 支持将生成的和声导出为 MIDI 或音频文件。

## ✨ 核心特性

- **🎹 交互式乐谱网格**：直观的 16 步时值 x 多音高网格，支持自由点击绘制与擦除音符。
- **🎨 四声部视觉区分**：
  - 🔵 **主旋律 (Soprano)**：用户输入，高亮蓝色
  - 🟠 **女低音 (Alto)**：AI 生成，暖橙色
  - 🟢 **男高音 (Tenor)**：AI 生成，翠绿色
  - 🔴 **男低音 (Bass)**：AI 生成，深红色
- **✨ 丝滑的交互动画**：引入 `framer-motion`，音符的生成、消除均带有舒适的缩放与错落延迟动画（Staggered Animation），拒绝生硬突兀。
- **📱 响应式设计**：完美适配桌面端，移动端支持横向滑动，随时随地记录音乐灵感。
- **📜 异域文化 UI**：采用纸质暖黄色背景搭配深棕色网格线，融合古典敦煌元素与现代 UI 质感。

## 🛠️ 技术栈

本项目采用现代前端最佳实践构建，保证了极致的开发体验与运行性能：

- **核心框架**: React 18 + TypeScript
- **构建工具**: Vite 6 (极速 HMR 与打包)
- **状态管理**: Zustand (轻量、简洁的全局状态流转)
- **样式方案**: Tailwind CSS (原子化 CSS，快速构建定制化 UI) + `clsx` / `tailwind-merge`
- **动画引擎**: Framer Motion
- **图标库**: Lucide React

## 🚀 快速开始

### 1. 克隆项目
```bash
git clone https://github.com/RudyJiang-cmd/internet-plus-website.git
cd internet-plus-website
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

本项目可以直接部署在任何静态页面托管服务上，例如 **Vercel**、**Netlify**，或者您自己的云服务器（如腾讯云/阿里云）加 **Nginx**。

### Vercel 一键部署 (推荐)
1. 在项目根目录运行 `npx vercel`
2. 按照命令行提示完成部署即可。

### Nginx 手动部署
将 `npm run build` 生成的 `dist` 目录下的所有文件，复制到服务器的 `/var/www/html` 目录下，并确保 Nginx 正确配置了静态文件代理。

---

<div align="center">
  <i>如果这个项目对你的比赛或学习有帮助，欢迎给个 ⭐️ Star！</i>
</div>
