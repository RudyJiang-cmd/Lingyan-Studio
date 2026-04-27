<div align="center">

# 🎵 交互式 AI 和声生成器 (Interactive Harmony Generator)

**基于 React 打造的 Google Bach Doodle 复刻项目**<br>
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

本项目专为**“互联网+”等创新创业比赛**打造，是一个高度交互的音乐生成前端界面。它复刻了经典的 **Google Bach Doodle** 交互逻辑，提供了一个精美的钢琴卷帘/五线谱网格 UI。

用户可以在网格上自由绘制主旋律（女高音声部），点击“生成和声”后，系统会模拟 AI 音乐生成模型（如 Coconet），自动为你补全其他三个声部（女低音、男高音、男低音），并配合丝滑的视觉动画呈现。

*💡 本项目目前主要聚焦于高可用的前端壳子与视觉交互逻辑，为后续无缝接入真实的 AI 音乐推理大模型做准备。*

## ✨ 核心特性

- **🎹 交互式乐谱网格**：直观的 16 步时值 x 多音高网格，支持自由点击绘制与擦除音符。
- **🎨 四声部视觉区分**：
  - 🔵 **主旋律 (Soprano)**：用户输入，高亮蓝色
  - 🟠 **女低音 (Alto)**：AI 生成，暖橙色
  - 🟢 **男高音 (Tenor)**：AI 生成，翠绿色
  - 🔴 **男低音 (Bass)**：AI 生成，深红色
- **✨ 丝滑的交互动画**：引入 `framer-motion`，音符的生成、消除均带有舒适的缩放与错落延迟动画（Staggered Animation），拒绝生硬突兀。
- **📱 响应式设计**：完美适配桌面端，移动端支持横向滑动，随时随地记录音乐灵感。
- **📜 复古现代结合 UI**：采用纸质暖黄色背景搭配深棕色网格线，致敬古典乐谱质感。

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
