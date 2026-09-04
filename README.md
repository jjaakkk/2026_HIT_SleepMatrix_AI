# 2026_HIT_SleepMatrix_AI

智能床垫实时数据可视化系统 —— 哈工大 2026 秋季《专业方向实践》课程项目（可视化展示组）。

以「智能床垫实时感知 → 压力分布分析 → 人体状态展示 → 支撑效果反馈」为主线，
基于 44×24 压力矩阵数据（新版数据，勿与旧版 40×26 混淆）构建的大屏实时监测界面。

## 技术栈

Vite + Vue 3 + TypeScript + Canvas（热力图自绘）+ ECharts（曲线，后续引入）。

## 数据事实基线（已实测核验，详见 docs/）

- 一帧 = 44 行 × 24 列 = 1056 个压力值；行 0 = 头端，列 12 = 中线
- txt 每帧 44 行，**帧间以空行分隔**；动态文件的间隔行是 0/1/2 睡姿标签（官方：忽视）
- 睡姿：0 仰卧 / 1 俯卧 / 2 左侧卧 / 3 右侧卧；action 1-6 仰卧、7-9 俯卧、10-15 左侧卧、16-21 右侧卧
- **镜像增强帧**：仰卧/俯卧镜像追加在自身文件后半；侧卧为跨动作镜像（10↔16 … 15↔21）；
  data.json 每个键 2 份记录 = 原始帧 + 镜像帧。回放默认只取原始帧
- region = 24 token（12 x + 12 y，x=列 y=行）；小腿部仅前 3 人标注，其余 na
- spine = 5 点（x1..x5 y1..y5），仅前 3 人标注
- 空载背景单点可达 42、均值约 4-5：接触类指标先扣空载均值帧
- 气囊无真实数据：条带布局按布置图编号（40/41/42、64/65/66、12/13）示意 + 模拟状态 + 预留接口

## 开发

```bash
npm install
npm run dev      # 开发服务器
npm run test     # 单元测试（Node 内置 runner，直接对真实数据断言）
npm run demo     # Phase 1 数据读取自检（打印关键数字）
npm run export:demo # 生成浏览器演示集 public/data/demo.json
npm run build    # 类型检查 + 构建
npm run capture  # 无头浏览器截图验证（需先启动 dev/preview 服务）
```

测试默认从仓库上一级 `../睡姿 区域划分data/睡姿 区域划分data` 读取数据集，
可用环境变量 `SLEEP_DATA_ROOT` 覆盖。

## 开发路线

Phase 1 数据读取 ✅ → Phase 2 静态热力图 ✅ → Phase 3 帧动画 ✅ → Phase 4 实时指标与曲线 ✅ →
Phase 5 区域分析 ✅ → Phase 6 完整大屏 UI ✅ → Phase 7 气囊模块 ✅ → Phase 8 最终 Demo ✅

## 答辩演示剧本（URL hash 直链）

| 步骤 | 演示内容 | 直链 hash |
|---|---|---|
| 1 | SAI 仰卧：区域框+脊柱线+指标+排行 | `#type=static&person=SAI&action=1&frame=10` |
| 2 | 切左侧卧：区域偏移、峰值升高（488） | `#type=static&person=SAI&action=10&frame=8` |
| 3 | 原始网格模式：证明数据真实 | `#type=static&person=SAI&action=1&frame=10&mode=grid` |
| 4 | 空载帧：离床·无人状态检测 | `#type=static&person=SAI&action=0&frame=5` |
| 5 | 动态过程回放：睡姿连续切换 | `#type=dynamic&frame=0&autoplay=1` |
| 6 | 动态+睡姿事件条（标签仅供参考） | `#type=dynamic&frame=55&dynlabels=1` |
| 7 | 气囊剧本：腰部支撑增强→腰部联动 | 点击"腰部支撑增强"按钮 |
| 8 | 点击任意传感器点/区域：曲线联动 | 鼠标操作 |
